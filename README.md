# AI Travel Assistant - LangGraph

An AI-powered travel assistant built with LangGraph, LangChain, and multiple LLM providers. The application provides intelligent travel planning through a conversational interface, leveraging agents to search flights, hotels, weather information, and create personalized travel itineraries.

## 🌟 Features

- **Conversational Travel Planning**: Natural language interface for travel queries
- **Multi-Provider LLM Support**: Groq, Google Gemini, OpenAI, DeepSeek
- **Flight Search**: Search and compare flight options
- **Hotel Search**: Find accommodation options based on preferences
- **Weather Information**: Real-time weather data for destinations
- **Web Search**: Tavily-powered search for travel information
- **Session Management**: Redis-backed conversation state persistence
- **Rate Limiting**: Sliding window rate limiter for API protection
- **Circuit Breaker**: Resilient external API calls with retry logic
- **Checkpointing**: LangGraph MemorySaver for conversation state
- **Async Support**: Full async/await architecture for high performance
- **Production-Ready**: Docker Compose deployment with scaling support

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Client Layer                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │   Flask     │  │   FastAPI   │  │   FastAPI (Async)       │ │
│  │   (Simple)  │  │  (Standard) │  │   (Scalable)            │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      LangGraph Core                              │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                  Travel Planner Graph                        ││
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐  ││
│  │  │  Router  │→│  Chat    │→│  Travel  │→│   Flight/     │  ││
│  │  │  Node    │ │  Node    │ │  Node    │ │   Hotel Node  │  ││
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────────┘  ││
│  └─────────────────────────────────────────────────────────────┘│
│                              │                                   │
│  ┌───────────────────────────▼───────────────────────────────┐ │
│  │                      Tools Layer                            │ │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌─────────┐ │ │
│  │  │  Weather  │ │  Flight    │ │  Hotel     │ │  Tavily │ │ │
│  │  │  Tool     │ │  Search    │ │  Search    │ │  Search │ │ │
│  │  └────────────┘ └────────────┘ └────────────┘ └─────────┘ │ │
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Infrastructure                              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │     Redis       │  │   PostgreSQL    │  │   Celery        │  │
│  │  (Cache/Session)│  │   (Database)    │  │   (Workers)     │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## 📁 Project Structure

```
AI-Travel_Assistant-Langgraph/
├── app.py                    # Flask application (simple deployment)
├── main.py                   # FastAPI application (standard)
├── main1.py                  # FastAPI async application (scalable)
├── ai_travel_planner.py      # Core LangGraph chatbot interface
├── ai_travel_planner1.py     # Async LangGraph chatbot interface
├── docker-compose.yml       # Basic Docker Compose setup
├── docker-compose.scalable.yml  # Scalable production setup
├── requirements.txt         # Python dependencies
├── pyproject.toml           # Project configuration
├── templates/               # HTML templates
│   ├── index.html           # Main chat interface
│   ├── login.html           # Login page
│   └── register.html        # Registration page
├── static/                  # Static assets
│   ├── css/                 # Stylesheets
│   └── js/                  # JavaScript
├── src/                     # Source code
│   ├── auth/                # Authentication services
│   ├── cache/               # Redis & session management
│   ├── config/              # Configuration & settings
│   ├── database/            # Database connections
│   ├── exceptions/          # Custom exceptions
│   ├── langgraph_core/      # LangGraph components
│   │   ├── graphs/          # Graph definitions
│   │   ├── nodes/           # Node implementations
│   │   ├── tools/           # Tool definitions
│   │   ├── state/           # State schemas
│   │   ├── LLMs/            # LLM loaders
│   │   └── schemas/         # Data schemas
│   ├── loggers/             # Logging configuration
│   ├── tasks/               # Celery tasks
│   └── utils/               # Utility functions
└── tests/                   # Test files
```

## 🛠️ Tech Stack

| Component | Technology |
|-----------|------------|
| **Framework** | FastAPI, Flask |
| **AI/ML** | LangGraph, LangChain |
| **LLM Providers** | Groq, Google Gemini, OpenAI, DeepSeek |
| **Search Tools** | Tavily, Wikipedia, ArXiv |
| **Database** | PostgreSQL |
| **Cache/Session** | Redis |
| **Task Queue** | Celery |
| **Containerization** | Docker, Docker Compose |
| **Frontend** | HTML, JavaScript, Flowbite CSS |

## 🚀 Installation

### Prerequisites

- Python 3.11+
- Conda or virtual environment
- Docker & Docker Compose (for deployment)
- API keys for LLM providers

### Setup with Conda

```bash
# Create and activate conda environment
conda create -p ./AI-Travel python=3.12
conda activate ./AI-Travel

# Install dependencies
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in the project root:

```env
# LLM API Keys
GROQ_API_KEY=your_groq_api_key
GOOGLE_API_KEY=your_google_api_key
OPENAI_API_KEY=your_openai_api_key
DEEPSEEK_API_KEY=your_deepseek_api_key

# Search API Keys
TAVILY_API_KEY=your_tavily_api_key
SERPAPI_API_KEY=your_ serpapi_api_key
OPENWEATHERMAP_API_KEY=your_openweathermap_api_key

# Database
DATABASE_URL=postgresql://user:password@localhost:5432/travel_db
ASYNC_DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/travel_db

# Redis
REDIS_URL=redis://localhost:6379/0
REDIS_PASSWORD=your_redis_password

# Security
SECRET_KEY=your_secret_key_min_32_chars

# Rate Limiting
RATE_LIMIT_RPM=60
```

## 📖 Usage

### Running the Application

**Flask (Simple)**
```bash
python app.py
```

**FastAPI (Standard)**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**FastAPI (Async/Scalable)**
```bash
uvicorn main1:app --host 0.0.0.0 --port 8000 --workers 4
```

### Docker Deployment

**Basic Setup**
```bash
docker-compose up -d
```

**Scalable Production Setup**
```bash
docker-compose -f docker-compose.scalable.yml up -d
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Main chat interface |
| GET | `/login` | Login page |
| GET | `/register` | Registration page |
| POST | `/data` | Process chat message (Flask) |
| POST | `/api/chat` | Process chat message (FastAPI) |
| POST | `/api/auth/register` | User registration |
| POST | `/api/auth/login` | User login |
| POST | `/api/auth/logout` | User logout |

## 🔧 Configuration

### LLM Configuration

Edit `src/config/llm_configs.yml` to customize model settings:

```yaml
groq:
  model: "llama-3.1-70b-versatile"
  temperature: 0.7
  max_tokens: 2048

gemini:
  model: "gemini-pro"
  temperature: 0.7
  max_tokens: 2048
```

### Rate Limiting

Configure rate limits in `src/config/settings.py` or via environment variables:

```env
RATE_LIMIT_RPM=60        # Requests per minute
RATE_LIMIT_RPH=1000      # Requests per hour
```

## 🔒 Security Features

- **JWT Authentication**: Secure token-based authentication
- **Password Hashing**: Secure password storage
- **Rate Limiting**: Sliding window algorithm
- **CORS Protection**: Configurable CORS middleware
- **Security Headers**: X-Content-Type-Options, X-Frame-Options
- **Input Validation**: Pydantic models for request validation

## 📊 Monitoring

The project includes Prometheus metrics integration. Access metrics at:
```
http://localhost:9090/metrics
```

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_langgraph_core.py -v
```

## 📝 Example Conversations

**Planning a Trip**
```
User: I want to plan a trip to Paris for 5 days starting from March 15
Assistant: That sounds wonderful! I'd be happy to help you plan your Paris trip.
          Let me gather some information:
          - How many people will be traveling?
          - What's your budget for accommodation?
          - Do you need flight recommendations?
```

**Checking Weather**
```
User: What's the weather like in Tokyo next week?
Assistant: Let me check the weather for you...
```

## 🐳 Docker Services

| Service | Port | Description |
|---------|------|-------------|
| app | 8000 | FastAPI application |
| postgres | 5432 | PostgreSQL database |
| redis | 6379 | Redis cache |
| celery-worker | - | Background task workers |
| celery-beat | - | Periodic task scheduler |

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 👤 Author

**Nabeel Ahmed**
- Email: mominnabeelahmed123@gmail.com

## 🙏 Acknowledgments

- LangChain & LangGraph teams for the excellent framework
- Groq for fast LLM inference
- All contributors and supporters
