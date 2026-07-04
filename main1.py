from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, EmailStr
from typing import Optional
from contextlib import asynccontextmanager

from ai_travel_planner1 import langgraph_chatbot
from src.database.async_database import async_database
from src.cache.redis_cluster import redis_cluster
from src.auth.async_authentication import AsyncAuthenticationService
from src.cache.session_manager import session_manager
from src.loggers import Logger

logger = Logger(__name__).get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await redis_cluster.connect()
    logger.info("Redis cluster connected successfully")

    # Create database tables
    await async_database.create_tables()
    logger.info("Database tables created")

    yield

    # Shutdown
    logger.info("Application shutdown")

app = FastAPI(title="Travel AI Assistant", debug=True, lifespan=lifespan)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Pydantic Models
class UserRegister(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: str
    name: Optional[str]

class AuthResponse(BaseModel):
    success: bool
    message: str
    session_token: Optional[str] = None
    user: Optional[UserResponse] = None

# Session Helper Functions
def get_session_token(request: Request) -> Optional[str]:
    """Extract session token from request"""
    # Check cookies first
    if "session_token" in request.cookies:
        return request.cookies["session_token"]

    # Check Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header.replace("Bearer ", "")

    # Check X-Session-Token header
    x_session_token = request.headers.get("X-Session-Token")
    if x_session_token:
        return x_session_token

    # Check query parameter
    session_token = request.query_params.get("session_token")
    if session_token:
        return session_token

    return None

async def get_current_user_from_request(request: Request):
    """Get current user from request using async database"""
    session_token = get_session_token(request)
    if not session_token:
        return None

    async with async_database.get_session() as db:
        auth_service = AsyncAuthenticationService(db)
        user = await auth_service.get_current_user(session_token)
        if user:
            logger.info(f"User found: {user['email']} (ID: {user['id']})")
        return user

# Routes
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    user = await get_current_user_from_request(request)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("index.html", {"request": request, "user": user})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/auth/register", response_model=AuthResponse)
async def register(user_data: UserRegister):
    async with async_database.get_session() as db:
        auth_service = AsyncAuthenticationService(db)
        result = await auth_service.register_user(
            email=user_data.email,
            password=user_data.password,
            name=user_data.name
        )

        if result["success"]:
            user_data_dict = {
                "email": user_data.email,
                "name": user_data.name
            }
            session_token = await session_manager.create_session(
                result["user_id"],
                user_data_dict
            )

            if session_token:
                return AuthResponse(
                    success=True,
                    message="Registration successful",
                    session_token=session_token,
                    user=UserResponse(
                        id=result["user_id"],
                        email=user_data.email,
                        name=user_data.name
                    )
                )

        return AuthResponse(
            success=False,
            message=result.get("error", "Registration failed")
        )

@app.post("/auth/login", response_model=AuthResponse)
async def login(credentials: UserLogin):
    async with async_database.get_session() as db:
        auth_service = AsyncAuthenticationService(db)
        result = await auth_service.login_user(
            email=credentials.email,
            password=credentials.password
        )

        if result["success"]:
            user = await auth_service.get_current_user(result["session_token"])
            return AuthResponse(
                success=True,
                message="Login successful",
                session_token=result["session_token"],
                user=UserResponse(**user) if user else None
            )

        return AuthResponse(
            success=False,
            message=result.get("error", "Login failed")
        )

@app.post("/auth/logout")
async def logout(session_token: str):
    # Get user before deleting session
    async with async_database.get_session() as db:
        auth_service = AsyncAuthenticationService(db)
        user = await auth_service.get_current_user(session_token)

        if user:
            await session_manager.clear_user_conversation_state(
                user_id=str(user['id']),
                session_id=session_token
            )
            logger.info(f"Cleared conversation state for user: {user['email']}")

    # Invalidate session
    success = await session_manager.delete_session(session_token)
    return {
        "success": success,
        "message": "Logged out successfully" if success else "Logout failed"
    }

@app.get("/auth/me", response_model=UserResponse)
async def get_current_user(session_token: str):
    async with async_database.get_session() as db:
        auth_service = AsyncAuthenticationService(db)
        user = await auth_service.get_current_user(session_token)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session"
            )

        return UserResponse(**user)

@app.post('/data')
async def get_data(request: Request):
    """Handles POST requests to process user data - REQUIRES AUTHENTICATION"""
    user = await get_current_user_from_request(request)
    if not user:
        return JSONResponse({"error": "Authentication required"}, status_code=401)

    data = await request.json()
    user_input = data.get('data')

    # Get session token for state management
    session_token = get_session_token(request)

    # Pass user context to chatbot
    out = await langgraph_chatbot(
        user_message=user_input,
        user_id=str(user['id']),
        session_id=session_token
    )

    logger.info(f"AI message for user {user['email']}: {out}")

    return JSONResponse({
        "response": True,
        "message": out,
        "user_authenticated": True,
        "user_name": user.get("name")
    })

@app.get("/health")
async def health_check():
    """Basic health check for load balancers"""
    redis_healthy = await redis_cluster.is_connected()

    # Check database connectivity
    try:
        async with async_database.get_session() as db:
            await db.execute("SELECT 1")
        db_healthy = True
    except:
        db_healthy = False

    if redis_healthy and db_healthy:
        return {"status": "healthy", "redis": "connected", "database": "connected"}
    else:
        raise HTTPException(503, detail={
            "status": "unhealthy",
            "redis": "connected" if redis_healthy else "disconnected",
            "database": "connected" if db_healthy else "disconnected"
        })

if __name__ == '__main__':
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=5000, reload=True)
