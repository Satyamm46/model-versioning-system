from fastapi import APIRouter

from backend.models.schemas import PromoteRequest, StatusUpdate
from backend.services import model_service as svc

router = APIRouter(prefix="/api/versions", tags=["versions"])


@router.get("/{version_id}")
def get_version(version_id: int):
    return svc.get_version(version_id)


@router.post("/{version_id}/promote")
def promote(version_id: int, body: PromoteRequest):
    return svc.promote(version_id, body.performed_by)


@router.patch("/{version_id}/status")
def update_status(version_id: int, body: StatusUpdate):
    return svc.set_status(version_id, body.status)
