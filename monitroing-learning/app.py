from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI()


@app.get("/")
def read_root():
    return {"message": "Hello World"}


@app.get("/slow")
def slow_rout():
    import time
    time.sleep(5)
    return {"message": "Hello World little slow"}


Instrumentator().instrument(app).expose(app)
