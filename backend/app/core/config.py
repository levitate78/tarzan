from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DB, require_role, write_audit_log
from app.core.rbac import Role
from app.models import ConnectorConfig, ReviewThreshold
from app.schemas import (
    ConnectorConfigCreate,
    ConnectorConfigResponse,
    ReviewThresholdResponse,
    ReviewThresholdUpdate,
)

router = APIRouter(prefix="/config", tags=["Config"])


# ── Connectors ─────────────────────────────────────────────────────────────────

@router.get("/connectors", response_model=list[ConnectorConfigResponse],
            dependencies=[require_role(Role.admin)])
async def list_connectors(db: DB, _: CurrentUser) -> list[ConnectorConfigResponse]:
    result = await db.execute(select(ConnectorConfig))
    return [ConnectorConfigResponse.model_validate(c) for c in result.scalars().all()]


@router.post("/connectors", response_model=ConnectorConfigResponse,
             status_code=status.HTTP_201_CREATED, dependencies=[require_role(Role.admin)])
async def create_connector(
    body: ConnectorConfigCreate, db: DB, current_user: CurrentUser
) -> ConnectorConfigResponse:
    config = ConnectorConfig(
        connector_type=body.connector_type.value,
        base_url=body.base_url,
        token=body.token,
        project_keys=body.project_keys or [],
        project_ids=body.project_ids or [],
        poll_interval_seconds=body.poll_interval_seconds,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    await write_audit_log(
        db, current_user.id, "create_connector", "connector_config", config.id,
        f"type={body.connector_type.value}"
    )
    await db.commit()
    return ConnectorConfigResponse.model_validate(config)


@router.put("/connectors/{config_id}", response_model=ConnectorConfigResponse,
            dependencies=[require_role(Role.admin)])
async def update_connector(
    config_id: str, body: ConnectorConfigCreate, db: DB, current_user: CurrentUser
) -> ConnectorConfigResponse:
    result = await db.execute(select(ConnectorConfig).where(ConnectorConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector config not found")

    config.connector_type = body.connector_type.value
    config.base_url = body.base_url
    config.token = body.token
    config.project_keys = body.project_keys
    config.project_ids = body.project_ids
    config.poll_interval_seconds = body.poll_interval_seconds

    await db.commit()
    await write_audit_log(db, current_user.id, "update_connector", "connector_config", config_id)
    await db.commit()
    return ConnectorConfigResponse.model_validate(config)


@router.delete("/connectors/{config_id}", status_code=status.HTTP_204_NO_CONTENT,
               dependencies=[require_role(Role.admin)])
async def delete_connector(config_id: str, db: DB, current_user: CurrentUser) -> None:
    result = await db.execute(select(ConnectorConfig).where(ConnectorConfig.id == config_id))
    config = result.scalar_one_or_none()
    if not config:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector config not found")
    await db.delete(config)
    await db.commit()
    await write_audit_log(db, current_user.id, "delete_connector", "connector_config", config_id)
    await db.commit()


# ── Review Threshold ───────────────────────────────────────────────────────────

@router.get("/review-threshold", response_model=ReviewThresholdResponse)
async def get_threshold(db: DB, _: CurrentUser) -> ReviewThresholdResponse:
    result = await db.execute(select(ReviewThreshold).where(ReviewThreshold.id == 1))
    rt = result.scalar_one_or_none()
    threshold = rt.threshold_hours if rt else 24.0
    return ReviewThresholdResponse(threshold_hours=threshold)


@router.put("/review-threshold", response_model=ReviewThresholdResponse,
            dependencies=[require_role(Role.lead)])
async def set_threshold(
    body: ReviewThresholdUpdate, db: DB, current_user: CurrentUser
) -> ReviewThresholdResponse:
    result = await db.execute(select(ReviewThreshold).where(ReviewThreshold.id == 1))
    rt = result.scalar_one_or_none()
    if rt:
        rt.threshold_hours = body.threshold_hours
    else:
        rt = ReviewThreshold(id=1, threshold_hours=body.threshold_hours)
        db.add(rt)
    await db.commit()
    await write_audit_log(
        db, current_user.id, "update_review_threshold", details=f"{body.threshold_hours}h"
    )
    await db.commit()
    return ReviewThresholdResponse(threshold_hours=body.threshold_hours)


# ── Manual sync ────────────────────────────────────────────────────────────────

@router.post("/sync", status_code=status.HTTP_202_ACCEPTED,
             dependencies=[require_role(Role.admin)])
async def trigger_sync(_: CurrentUser) -> dict:
    """
    Signal the worker to perform an immediate full sync.
    In production this would publish to a Redis pub/sub channel or task queue.
    """
    import redis.asyncio as aioredis
    from app.config import get_settings
    try:
        r = aioredis.from_url(get_settings().REDIS_URL)
        await r.publish("tarzan:sync", "full")
        await r.aclose()
    except Exception:
        pass  # Worker will sync on its next scheduled interval regardless
    return {"message": "Sync triggered"}