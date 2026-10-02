from datetime import date
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.models import MarketDay, Pillar, PowerOutlet, Segment, Vendor

# 干净快照即自备三类拒因触发：
#   街段宽 30m，挡柱@10/@20 把街段切成三段约 9.5~9.75m 的空档；
#   消防净距 1m；供电桩 1 个 @25m、覆盖半径 2m（仅覆盖 23~27m）。
WIDTH = 30.0
CLEARANCE = 1.0
PILLARS = [(10.0, 0.5, "灯柱A"), (20.0, 0.5, "灯柱B")]
OUTLETS = [(25.0, 2.0, "供电桩①")]
# (name, width, priority, needs_power, 预期主因)；优先 1 的三个拒因摊在任何占用前判定
VENDORS = [
    ("巨型舞台车", 12.0, 1, False, "span"),       # 裸空档最长 9.75m：空档连续长度不足
    ("棉花糖大阵", 9.0, 1, False, "clearance"),   # 裸空档放得下，两端各让 1m 后仅 7.75m
    ("充电咖啡车", 6.0, 1, True, "power"),        # 净距后放得下，但供电覆盖段只有 4m
    ("阿强烧烤", 4.0, 2, False, None),
    ("林记糖水", 3.0, 2, False, None),
    ("充电柠檬茶", 3.0, 2, True, None),           # 落在 23~27m 供电覆盖内
    ("老周水果", 5.0, 2, False, None),
    ("小美饰品", 2.5, 3, False, None),
]


def seed_if_empty(db: Session) -> None:
    if (db.scalar(select(func.count()).select_from(MarketDay)) or 0) > 0:
        return
    day = MarketDay(name="周末夜市", day=date(2026, 9, 20))
    db.add(day); db.flush()
    seg = Segment(market_day_id=day.id, name="东街段", width_m=WIDTH, clearance_m=CLEARANCE)
    db.add(seg); db.flush()
    for pos, thick, label in PILLARS:
        db.add(Pillar(segment_id=seg.id, position_m=pos, thickness_m=thick, label=label))
    for pos, radius, label in OUTLETS:
        db.add(PowerOutlet(segment_id=seg.id, position_m=pos,
                           coverage_radius_m=radius, label=label))
    for name, wdt, pri, needs_power, _reason in VENDORS:
        db.add(Vendor(market_day_id=day.id, name=name, stall_width_m=wdt,
                      priority=pri, needs_power=needs_power))
    db.commit()
