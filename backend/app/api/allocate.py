import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import AllocationRun, Pillar, PowerOutlet, Segment, Vendor
from app.services.first_fit_engine import ConfigError, allocate_first_fit, result_to_dict
router = APIRouter(prefix="/allocate", tags=["allocate"])


def _gather(segment_id: int, db: Session):
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    pillars = [{"position_m": p.position_m, "thickness_m": p.thickness_m}
               for p in db.scalars(select(Pillar).where(Pillar.segment_id == segment_id)).all()]
    outlets = [{"id": o.id, "position_m": o.position_m,
                "coverage_radius_m": o.coverage_radius_m, "label": o.label}
               for o in db.scalars(select(PowerOutlet).where(PowerOutlet.segment_id == segment_id)
                                   .order_by(PowerOutlet.position_m)).all()]
    vendors = [{"id": v.id, "name": v.name, "stall_width_m": v.stall_width_m,
                "priority": v.priority, "needs_power": v.needs_power}
               for v in db.scalars(select(Vendor).where(Vendor.market_day_id == seg.market_day_id)).all()]
    return seg, pillars, outlets, vendors


def _run(seg: Segment, pillars: list[dict], outlets: list[dict], vendors: list[dict]) -> dict:
    """唯一的运行入口：非法配置抛 400，且不产生 AllocationRun（拒绝落库）。"""
    try:
        result = result_to_dict(allocate_first_fit(
            seg.width_m, vendors, pillars, clearance_m=seg.clearance_m or 0.0, outlets=outlets))
    except ConfigError as exc:
        raise HTTPException(400, f"配置非法，无法判定：{exc}")
    result["segment"] = {"id": seg.id, "name": seg.name, "width_m": seg.width_m,
                         "clearance_m": seg.clearance_m or 0.0}
    result["pillars"] = pillars
    result["outlets"] = outlets
    return result


@router.post("/run")
def run_allocate(segment_id: int = 1, db: Session = Depends(get_db)):
    seg, pillars, outlets, vendors = _gather(segment_id, db)
    result = _run(seg, pillars, outlets, vendors)
    run = AllocationRun(segment_id=segment_id, created_at=datetime.utcnow(),
                        result_json=json.dumps(result, ensure_ascii=False))
    db.add(run)
    db.commit()
    db.refresh(run)
    return {"id": run.id, **result}


@router.get("/latest")
def latest(segment_id: int = 1, db: Session = Depends(get_db)):
    run = db.scalars(select(AllocationRun).where(AllocationRun.segment_id == segment_id)
                     .order_by(AllocationRun.id.desc())).first()
    if not run:
        return run_allocate(segment_id=segment_id, db=db)
    data = json.loads(run.result_json)
    return {"id": run.id, "created_at": run.created_at.isoformat(), **data}


@router.get("/runs")
def list_runs(segment_id: int = 1, limit: int = 20, db: Session = Depends(get_db)):
    """运行抽屉：每次成功提交的快照；拒因与当时提交瞬间的配置一起冻结在此。"""
    rows = db.scalars(select(AllocationRun).where(AllocationRun.segment_id == segment_id)
                      .order_by(AllocationRun.id.desc()).limit(max(1, min(limit, 100)))).all()
    out = []
    for run in rows:
        data = json.loads(run.result_json)
        out.append({
            "id": run.id,
            "created_at": run.created_at.isoformat(),
            "segment": data.get("segment"),
            "config": data.get("config", {}),
            "pillars": data.get("pillars", []),
            "outlets": data.get("outlets", []),
            "free_spans": data.get("free_spans", []),
            "placements": data.get("placements", []),
            "rejected": data.get("rejected", []),
        })
    return out
