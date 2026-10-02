import pytest

from app.services.first_fit_engine import (
    REASON_CLEARANCE,
    REASON_POWER,
    REASON_SPAN,
    ConfigError,
    allocate_first_fit,
    free_spans_from_pillars,
    result_to_dict,
    validate_config,
)


def vendor(vid, name, width, priority=1, needs_power=False):
    return {"id": vid, "name": name, "stall_width_m": width,
            "priority": priority, "needs_power": needs_power}


PILLARS = [{"position_m": 10.0, "thickness_m": 0.5},
           {"position_m": 20.0, "thickness_m": 0.5}]


def test_free_spans_with_pillars():
    spans = free_spans_from_pillars(30.0, PILLARS)
    assert len(spans) == 3
    assert spans[0][0] == 0.0


def test_first_fit_no_cross_pillar():
    vendors = [vendor(1, "A", 4.0), vendor(2, "B", 12.0)]
    r = allocate_first_fit(30.0, vendors, [PILLARS[0]])
    assert any(p.vendor_name == "A" for p in r.placements)
    assert len(r.placements) + len(r.rejected) == 2


def test_reject_oversized_is_span():
    r = allocate_first_fit(30.0, [vendor(1, "Huge", 25.0)], PILLARS)
    assert len(r.rejected) == 1
    assert r.rejected[0].vendor_name == "Huge"
    assert r.rejected[0].reason_code == REASON_SPAN


# ---------- 三类拒因各自可区分 ----------

def test_reason_span():
    r = allocate_first_fit(30.0, [vendor(1, "巨", 25.0)], PILLARS)
    assert r.rejected[0].reason_code == REASON_SPAN
    assert "空档连续长度" in r.rejected[0].reason


def test_reason_clearance():
    # 裸空档 9.75 放得下 8；净距 1m 内缩后 7.75 放不下
    r = allocate_first_fit(30.0, [vendor(1, "摊", 8.0)], PILLARS, clearance_m=1.0)
    assert r.rejected[0].reason_code == REASON_CLEARANCE
    assert "消防净距" in r.rejected[0].reason


def test_reason_power():
    # 桩只覆盖 0~3m，8m 用电摊无处可落
    r = allocate_first_fit(30.0, [vendor(1, "电", 8.0, needs_power=True)],
                           [PILLARS[0]], outlets=[{"position_m": 1, "coverage_radius_m": 2}])
    assert r.rejected[0].reason_code == REASON_POWER
    assert "供电覆盖" in r.rejected[0].reason


# ---------- 短路顺序钉死：power > clearance > span ----------

def test_precedence_power_over_clearance_when_both_block():
    # 净距 2m 单独即挡死；供电桩@26 半径 1.5 只覆盖尾段，也挡死 → 必须归 power
    r = allocate_first_fit(30.0, [vendor(1, "电", 9.2, needs_power=True)],
                           [PILLARS[0]], clearance_m=2.0,
                           outlets=[{"position_m": 26, "coverage_radius_m": 1.5}])
    assert [x.reason_code for x in r.rejected] == [REASON_POWER]


def test_power_ample_clearance_blocking_is_clearance():
    # 供电覆盖全段时不得抢标签：真正卡人的是净距
    r = allocate_first_fit(30.0, [vendor(1, "摊", 8.0, needs_power=True)],
                           PILLARS, clearance_m=2.0,
                           outlets=[{"position_m": 15, "coverage_radius_m": 30}])
    assert [x.reason_code for x in r.rejected] == [REASON_CLEARANCE]


def test_one_reason_code_per_rejection():
    r = allocate_first_fit(30.0, [vendor(1, "电", 9.2, needs_power=True)],
                           [PILLARS[0]], clearance_m=2.0,
                           outlets=[{"position_m": 26, "coverage_radius_m": 1.5}])
    for rej in r.rejected:
        assert isinstance(rej.reason_code, str)
        assert rej.reason_code in (REASON_SPAN, REASON_CLEARANCE, REASON_POWER)


# ---------- 默认关闭：净距 0 + 无供电桩 ----------

def test_defaults_off_no_clearance_or_power_reasons():
    r = allocate_first_fit(30.0, [vendor(1, "电", 8.0, needs_power=True)], [PILLARS[0]])
    assert len(r.placements) == 1
    assert r.rejected == []


def test_zero_clearance_never_clearance_reason():
    # 贴着柱子 9.5m 放 9m 摊：净距为 0 时必须成功
    r = allocate_first_fit(30.0, [vendor(1, "x", 9.0)], PILLARS, clearance_m=0.0)
    assert r.placements and not r.rejected


def test_no_outlets_never_power_reason_even_for_power_vendor():
    r = allocate_first_fit(30.0, [vendor(1, "电", 40.0, needs_power=True)], [])
    assert [x.reason_code for x in r.rejected] == [REASON_SPAN]


# ---------- 成功摊不得带拒因标签，也不得被记成拒绝 ----------

def test_success_has_no_reason_and_placement_respects_constraints():
    r = allocate_first_fit(30.0, [vendor(1, "电", 4.0, needs_power=True),
                                  vendor(2, "普", 4.0)],
                           [], outlets=[{"position_m": 10, "coverage_radius_m": 2}])
    placed = {p.vendor_id: p for p in r.placements}
    assert set(placed) == {1, 2}
    # 用电摊落在 8~12 覆盖内；普通摊可复用其跳过的未供电前缀 0~4
    assert placed[1].start_m == 8.0 and placed[1].end_m == 12.0
    assert placed[2].start_m == 0.0
    d = result_to_dict(r)
    assert all("reason_code" not in p and "reason" not in p for p in d["placements"])
    assert d["rejected"] == []


def test_stall_to_stall_no_double_clearance():
    # 净距只让墙/柱端：两个 4m 摊在宽 10（可用 8）内必须紧贴放下
    r = allocate_first_fit(10.0, [vendor(1, "a", 4.0), vendor(2, "b", 4.0)],
                           [], clearance_m=1.0)
    assert [(p.start_m, p.end_m) for p in r.placements] == [(1.0, 5.0), (5.0, 9.0)]


# ---------- 非法配置：无法判定，不得产出半截结果 ----------

@pytest.mark.parametrize("kwargs", [
    dict(width_m=0, vendors=[], pillars=[]),
    dict(width_m=10, vendors=[vendor(1, "x", -1)], pillars=[]),
    dict(width_m=10, vendors=[], pillars=[], clearance_m=5.0),
    dict(width_m=10, vendors=[], pillars=[{"position_m": 11, "thickness_m": 0.4}]),
    dict(width_m=10, vendors=[], pillars=[], outlets=[{"position_m": 5, "coverage_radius_m": 0}]),
    dict(width_m=10, vendors=[], pillars=[], outlets=[{"position_m": 12, "coverage_radius_m": 1}]),
])
def test_invalid_config_raises(kwargs):
    with pytest.raises(ConfigError):
        allocate_first_fit(**kwargs)
