from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Pillar, PowerOutlet, Segment, Vendor
from app.services.first_fit_engine import ConfigError, validate_config
router = APIRouter(prefix="/outlets", tags=["outlets"])


def _dump(o: PowerOutlet) -> dict:
    return {"id": o.id, "segment_id": o.segment_id, "position_m": o.position_m,
            "coverage_radius_m": o.coverage_radius_m, "label": o.label}


@router.get("")
def list_outlets(segment_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(PowerOutlet).order_by(PowerOutlet.segment_id, PowerOutlet.position_m)
    if segment_id is not None:
        stmt = stmt.where(PowerOutlet.segment_id == segment_id)
    return [_dump(o) for o in db.scalars(stmt).all()]


class OutletIn(BaseModel):
    segment_id: int = 1
    position_m: float
    coverage_radius_m: float = 20.0
    label: str = "供电桩"


@router.post("")
def add_outlet(body: OutletIn, db: Session = Depends(get_db)):
    seg = db.get(Segment, body.segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    pillars = [{"position_m": p.position_m, "thickness_m": p.thickness_m}
               for p in db.scalars(select(Pillar).where(Pillar.segment_id == seg.id)).all()]
    existing = [{"position_m": o.position_m, "coverage_radius_m": o.coverage_radius_m}
                for o in db.scalars(select(PowerOutlet).where(PowerOutlet.segment_id == seg.id)).all()]
    vendors = [{"id": v.id, "name": v.name, "stall_width_m": v.stall_width_m,
                "priority": v.priority}
               for v in db.scalars(select(Vendor).where(Vendor.market_day_id == seg.market_day_id)).all()]
    candidate = existing + [{"position_m": body.position_m,
                             "coverage_radius_m": body.coverage_radius_m}]
    try:
        validate_config(seg.width_m, vendors, pillars,
                        clearance_m=seg.clearance_m or 0.0, outlets=candidate)
    except ConfigError as exc:
        raise HTTPException(400, f"配置非法：{exc}")
    out = PowerOutlet(segment_id=body.segment_id, position_m=body.position_m,
                      coverage_radius_m=body.coverage_radius_m, label=body.label)
    db.add(out)
    db.commit()
    db.refresh(out)
    return _dump(out)


@router.delete("/{outlet_id}", status_code=204)
def delete_outlet(outlet_id: int, db: Session = Depends(get_db)):
    out = db.get(PowerOutlet, outlet_id)
    if not out:
        raise HTTPException(404, "供电桩不存在")
    db.delete(out)
    db.commit()
