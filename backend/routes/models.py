from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile

from backend.models.schemas import ModelCreate, RollbackRequest
from backend.services import model_service as svc

router = APIRouter(prefix="/api/models", tags=["models"])


@router.post("", status_code=201)
def create_model(body: ModelCreate):
    return svc.create_model(body.model_dump())


@router.get("")
def list_models():
    return svc.list_models()


@router.get("/{model_id}")
def get_model(model_id: int):
    return svc.get_model(model_id)


@router.delete("/{model_id}")
def delete_model(model_id: int):
    svc.delete_model(model_id)
    return {"message": "Model deleted"}


@router.post("/{model_id}/versions", status_code=201)
def upload_version(model_id: int,
                   file: UploadFile = File(...),
                   accuracy: Optional[float] = Form(None),
                   created_by: str = Form("anonymous"),
                   change_notes: str = Form("")):
    return svc.create_version(model_id, file, accuracy,
                              created_by.strip()[:50] or "anonymous", change_notes.strip()[:500])


@router.get("/{model_id}/versions")
def list_versions(model_id: int):
    return svc.list_versions(model_id)


@router.get("/{model_id}/deployments")
def model_deployments(model_id: int):
    return svc.list_deployments(model_id)


@router.get("/{model_id}/rollbacks")
def model_rollbacks(model_id: int):
    return svc.list_rollbacks(model_id)


@router.post("/{model_id}/rollback")
def rollback(model_id: int, body: RollbackRequest):
    return svc.rollback(model_id, body.performed_by, body.reason, body.to_version)


@router.get("/{model_id}/compare")
def compare(model_id: int, a: int, b: int):
    return svc.compare_versions(model_id, a, b)
