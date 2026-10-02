from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Pillar, Segment, Vendor, PowerOutlet
from app.services.first_fit_engine import ConfigError, validate_config
router = APIRouter(prefix="/segments", tags=["segments"])


def _dump(r: Segment) -> dict:
    return {"id": r.id, "market_day_id": r.market_day_id, "name": r.name,
            "width_m": r.width_m, "clearance_m": r.clearance_m or 0.0}


@router.get("")
def list_segments(db: Session = Depends(get_db)):
    return [_dump(r) for r in db.scalars(select(Segment).order_by(Segment.id)).all()]


class SegmentPatch(BaseModel):
    name: str | None = None
    width_m: float | None = None
    clearance_m: float | None = None


@router.patch("/{segment_id}")
def patch_segment(segment_id: int, body: SegmentPatch, db: Session = Depends(get_db)):
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    width = body.width_m if body.width_m is not None else seg.width_m
    clearance = body.clearance_m if body.clearance_m is not None else (seg.clearance_m or 0.0)
    pillars = [{"position_m": p.position_m, "thickness_m": p.thickness_m}
               for p in db.scalars(select(Pillar).where(Pillar.segment_id == segment_id)).all()]
    outlets = [{"position_m": o.position_m, "coverage_radius_m": o.coverage_radius_m}
               for o in db.scalars(select(PowerOutlet).where(PowerOutlet.segment_id == segment_id)).all()]
    vendors = [{"id": v.id, "name": v.name, "stall_width_m": v.stall_width_m, "priority": v.priority}
               for v in db.scalars(select(Vendor).where(Vendor.market_day_id == seg.market_day_id)).all()]
    # 非法配置当场拒绝：不写库，主图仍是改前配置
    try:
        validate_config(width, vendors, pillars, clearance_m=clearance, outlets=outlets)
    except ConfigError as exc:
        raise HTTPException(400, f"配置非法：{exc}")
    if body.name is not None:
        seg.name = body.name
    seg.width_m = width
    seg.clearance_m = clearance
    db.commit()
    db.refresh(seg)
    return _dump(seg)
