from app.services.first_fit_engine import REASON_CLEARANCE, REASON_POWER, REASON_SPAN


def _reason_map(payload):
    return {r["vendor_name"]: r["reason_code"] for r in payload["rejected"]}


def test_seed_run_shows_three_distinct_reasons(client):
    res = client.post("/api/allocate/run?segment_id=1")
    assert res.status_code == 200
    reasons = _reason_map(res.json())
    assert "巨型舞台车" in reasons and reasons["巨型舞台车"] == REASON_SPAN
    assert "棉花糖大阵" in reasons and reasons["棉花糖大阵"] == REASON_CLEARANCE
    assert "充电咖啡车" in reasons and reasons["充电咖啡车"] == REASON_POWER
    # 成功摊绝不带拒因标签
    assert all("reason_code" not in p and "reason" not in p for p in res.json()["placements"])
    # 配置随运行一起冻结
    assert res.json()["config"]["clearance_m"] == 1.0
    assert len(res.json()["config"]["outlets"]) == 1


def test_latest_and_run_drawer_read_same_judgement(client):
    run = client.post("/api/allocate/run?segment_id=1").json()
    latest = client.get("/api/allocate/latest?segment_id=1").json()
    drawer = client.get("/api/allocate/runs?segment_id=1").json()
    assert [r["reason_code"] for r in latest["rejected"]] == \
           [r["reason_code"] for r in run["rejected"]]
    assert drawer[0]["id"] == run["id"]
    assert [r["reason_code"] for r in drawer[0]["rejected"]] == \
           [r["reason_code"] for r in run["rejected"]]


def test_invalid_clearance_rejected_not_persisted_main_map_kept(client):
    before = client.post("/api/allocate/run?segment_id=1").json()
    runs_before = len(client.get("/api/allocate/runs?segment_id=1").json())
    # 净距过大 → 400，配置不写库
    res = client.patch("/api/segments/1", json={"clearance_m": 999})
    assert res.status_code == 400
    # 主图/最新仍是改前配置
    latest = client.get("/api/allocate/latest?segment_id=1").json()
    assert latest["config"]["clearance_m"] == 1.0
    seg = client.get("/api/segments").json()[0]
    assert seg["clearance_m"] == 1.0
    assert len(client.get("/api/allocate/runs?segment_id=1").json()) == runs_before
    assert _reason_map(latest) == _reason_map(before)


def test_invalid_outlet_rejected_not_persisted(client):
    client.post("/api/allocate/run?segment_id=1")
    res = client.post("/api/outlets", json={"segment_id": 1, "position_m": 50,
                                            "coverage_radius_m": 2})
    assert res.status_code == 400
    assert client.get("/api/outlets?segment_id=1").json() == [] or \
           all(o["position_m"] != 50 for o in client.get("/api/outlets?segment_id=1").json())


def test_clearance_to_zero_removes_clearance_class(client):
    client.post("/api/allocate/run?segment_id=1")
    # 净距改 0：棉花糖大阵（9m）可放下 → clearance 类消失，重分结果按提交瞬间新配置
    assert client.patch("/api/segments/1", json={"clearance_m": 0}).status_code == 200
    after = client.post("/api/allocate/run?segment_id=1").json()
    reasons = _reason_map(after)
    assert reasons.get("棉花糖大阵") is None
    assert after["config"]["clearance_m"] == 0.0
    assert REASON_CLEARANCE not in set(reasons.values())


def test_remove_outlet_removes_power_class_and_no_phantom_power(client):
    client.post("/api/allocate/run?segment_id=1")
    outlets = client.get("/api/outlets?segment_id=1").json()
    assert len(outlets) == 1
    assert client.delete(f"/api/outlets/{outlets[0]['id']}").status_code == 204
    after = client.post("/api/allocate/run?segment_id=1").json()
    reasons = _reason_map(after)
    # 无供电桩后用电约束关闭：不得凭空冒出 power 拒因
    assert REASON_POWER not in set(reasons.values())
    assert reasons.get("充电咖啡车") is None  # 净距 1m 下 6m 摊本可放下
    assert after["config"]["outlets"] == []


def test_greenfield_zero_clearance_no_outlets_has_no_last_two_classes(client):
    # 净距填 0 且未配供电桩：与绿仓一致，后两类拒因绝不凭空出现
    from app.database import SessionLocal
    from app.models.models import MarketDay, Segment, Vendor
    db = SessionLocal()
    try:
        day = db.query(MarketDay).first()
        seg = Segment(market_day_id=day.id, name="绿仓段", width_m=20.0, clearance_m=0.0)
        db.add(seg); db.flush()
        db.add(Vendor(market_day_id=day.id, name="绿仓用电摊", stall_width_m=18.0,
                      priority=1, needs_power=True))
        db.commit()
        sid = seg.id
    finally:
        db.close()
    payload = client.post(f"/api/allocate/run?segment_id={sid}").json()
    codes = {r["reason_code"] for r in payload["rejected"]}
    assert REASON_CLEARANCE not in codes and REASON_POWER not in codes


def test_run_with_invalid_config_returns_400_and_no_new_run(client):
    # 直接把净距改到非法，再触发运行：400 且不得产生 AllocationRun
    from app.database import SessionLocal
    from app.models.models import Segment
    client.post("/api/allocate/run?segment_id=1")
    db = SessionLocal()
    try:
        seg = db.get(Segment, 1)
        seg.clearance_m = 999.0
        db.commit()
    finally:
        db.close()
    runs_before = len(client.get("/api/allocate/runs?segment_id=1").json())
    res = client.post("/api/allocate/run?segment_id=1")
    assert res.status_code == 400
    assert "无法判定" in res.text  # 错误文案不得是半截成功
    assert len(client.get("/api/allocate/runs?segment_id=1").json()) == runs_before

