"""Entry point.  Run from the project root:  uvicorn backend.main:app --reload"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.config import APP_NAME, BASE_DIR
from backend.app.logger import log
from backend.database.db import init_db
from backend.routes import models, system, versions
from backend.services.model_service import ServiceError


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    log.info("Application started")
    yield


app = FastAPI(title=APP_NAME, lifespan=lifespan)


@app.exception_handler(ServiceError)
async def service_error_handler(_request: Request, exc: ServiceError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.message})


app.include_router(system.router)
app.include_router(models.router)
app.include_router(versions.router)
app.mount("/", StaticFiles(directory=BASE_DIR / "frontend", html=True), name="frontend")
