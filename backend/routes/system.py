from fastapi import APIRouter

from backend.app.config import APP_NAME
from backend.services import model_service as svc

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health():
    return {"status": "UP", "application": APP_NAME}


@router.get("/dashboard")
def dashboard():
    return svc.dashboard()


@router.get("/deployments")
def all_deployments():
    return svc.list_deployments()
