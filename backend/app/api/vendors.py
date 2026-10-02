from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Segment, Vendor
from app.services.first_fit_engine import ConfigError, validate_config
router = APIRouter(prefix="/vendors", tags=["vendors"])


def _dump(r: Vendor) -> dict:
    return {"id": r.id, "market_day_id": r.market_day_id, "name": r.name,
            "stall_width_m": r.stall_width_m, "priority": r.priority,
            "needs_power": bool(r.needs_power)}


@router.get("")
def list_vendors(db: Session = Depends(get_db)):
    return [_dump(r) for r in
            db.scalars(select(Vendor).order_by(Vendor.priority, Vendor.id)).all()]


class VendorPatch(BaseModel):
    name: str | None = None
    stall_width_m: float | None = None
    priority: int | None = None
    needs_power: bool | None = None


@router.patch("/{vendor_id}")
def patch_vendor(vendor_id: int, body: VendorPatch, db: Session = Depends(get_db)):
    ven = db.get(Vendor, vendor_id)
    if not ven:
        raise HTTPException(404, "摊主不存在")
    seg = db.scalars(select(Segment).where(Segment.market_day_id == ven.market_day_id)
                     .order_by(Segment.id)).first()
    if seg:
        width = body.stall_width_m if body.stall_width_m is not None else ven.stall_width_m
        priority = body.priority if body.priority is not None else ven.priority
        try:
            validate_config(seg.width_m, [{"id": ven.id, "name": ven.name,
                                           "stall_width_m": width, "priority": priority}], [])
        except ConfigError as exc:
            raise HTTPException(400, f"配置非法：{exc}")
    if body.name is not None:
        ven.name = body.name
    if body.stall_width_m is not None:
        ven.stall_width_m = body.stall_width_m
    if body.priority is not None:
        ven.priority = body.priority
    if body.needs_power is not None:
        ven.needs_power = body.needs_power
    db.commit()
    db.refresh(ven)
    return _dump(ven)
