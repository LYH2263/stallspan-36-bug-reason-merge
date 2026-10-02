"""1D First-Fit stall placement along a street segment.

三类拒因（同一套判定，分配图 / 放不下页 / 运行抽屉共用）：
  span       空档连续长度不足（含被挡柱切开）
  clearance  消防净距不足
  power      供电覆盖不足

短路固定顺序：power > clearance > span。同一拒绝条目只带一类主因。
约束开关（关闭时绝不产生对应文案）：
  净距 clearance_m == 0  → 不检查消防净距
  街段无供电桩 outlets=[] → 即使摊位 needs_power 也不检查供电
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

REASON_SPAN = "span"
REASON_CLEARANCE = "clearance"
REASON_POWER = "power"

REASON_LABELS = {
    REASON_SPAN: "空档连续长度不足",
    REASON_CLEARANCE: "消防净距不足",
    REASON_POWER: "供电覆盖不足",
}
# 短路顺序：下标越小越优先。同时满足多类时只保留最靠前的一类。
REASON_PRECEDENCE = (REASON_POWER, REASON_CLEARANCE, REASON_SPAN)

_EPS = 1e-9


class ConfigError(ValueError):
    """配置非法、无法判定；调用方必须拒绝落库且不得产出半截结果。"""


@dataclass
class Placement:
    vendor_id: int
    vendor_name: str
    start_m: float
    end_m: float
    width_m: float
    needs_power: bool = False


@dataclass
class Rejected:
    vendor_id: int
    vendor_name: str
    width_m: float
    reason_code: str
    reason: str


@dataclass
class AllocResult:
    placements: list[Placement]
    rejected: list[Rejected]
    free_spans: list[tuple[float, float]]
    clearance_m: float = 0.0
    outlets: list[dict] | None = None


def validate_config(width_m: float, vendors: list[dict], pillars: list[dict],
                    clearance_m: float = 0.0, outlets: list[dict] | None = None) -> None:
    """配置非法即抛 ConfigError —— 不允许在非法配置上产出任何分配/拒因。"""
    outlets = outlets or []
    if not isinstance(width_m, (int, float)) or width_m <= 0:
        raise ConfigError("街段宽度必须为正数")
    if not isinstance(clearance_m, (int, float)) or clearance_m < 0:
        raise ConfigError("消防净距不能为负")
    if clearance_m * 2.0 >= width_m:
        raise ConfigError("消防净距过大：双侧内缩后街段已无可用长度")
    for v in vendors:
        if not isinstance(v.get("stall_width_m"), (int, float)) or v["stall_width_m"] <= 0:
            raise ConfigError(f"摊主「{v.get('name', v.get('id'))}」的需求宽度必须为正数")
        if not isinstance(v.get("priority", 1), int) or v.get("priority", 1) < 0:
            raise ConfigError(f"摊主「{v.get('name', v.get('id'))}」的优先级必须为非负整数")
    for p in pillars:
        pos = p.get("position_m")
        thick = p.get("thickness_m", 0.4)
        if not isinstance(pos, (int, float)) or pos < 0 or pos > width_m:
            raise ConfigError("挡柱位置超出街段范围")
        if not isinstance(thick, (int, float)) or thick < 0:
            raise ConfigError("挡柱厚度不能为负")
    for o in outlets:
        pos = o.get("position_m")
        radius = o.get("coverage_radius_m", 20.0)
        if not isinstance(pos, (int, float)) or pos < 0 or pos > width_m:
            raise ConfigError("供电桩位置超出街段范围")
        if not isinstance(radius, (int, float)) or radius <= 0:
            raise ConfigError("供电覆盖半径必须为正数")


def free_spans_from_pillars(width_m: float, pillars: list[dict]) -> list[tuple[float, float]]:
    """pillars: position_m, thickness_m — treated as blocked intervals."""
    blocked = []
    for p in pillars:
        half = p.get("thickness_m", 0.4) / 2.0
        lo = max(0.0, p["position_m"] - half)
        hi = min(width_m, p["position_m"] + half)
        if hi > lo:
            blocked.append((lo, hi))
    blocked.sort()
    merged = []
    for lo, hi in blocked:
        if not merged or lo > merged[-1][1]:
            merged.append([lo, hi])
        else:
            merged[-1][1] = max(merged[-1][1], hi)
    spans = []
    cursor = 0.0
    for lo, hi in merged:
        if lo > cursor:
            spans.append((cursor, lo))
        cursor = hi
    if cursor < width_m:
        spans.append((cursor, width_m))
    return [(round(a, 3), round(b, 3)) for a, b in spans if b - a > 1e-6]


def _union(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    intervals = sorted((a, b) for a, b in intervals if b - a > _EPS)
    out: list[list[float]] = []
    for lo, hi in intervals:
        if not out or lo > out[-1][1]:
            out.append([lo, hi])
        else:
            out[-1][1] = max(out[-1][1], hi)
    return [(a, b) for a, b in out]


def powered_unions(width_m: float, outlets: list[dict]) -> list[tuple[float, float]]:
    """所有供电桩覆盖区间（按覆盖半径）的并集；空列表表示街段无供电桩。"""
    if not outlets:
        return []
    return _union([
        (max(0.0, o["position_m"] - o.get("coverage_radius_m", 20.0)),
         min(width_m, o["position_m"] + o.get("coverage_radius_m", 20.0)))
        for o in outlets
    ])


def _intersect(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    i = j = 0
    while i < len(a) and j < len(b):
        lo = max(a[i][0], b[j][0])
        hi = min(a[i][1], b[j][1])
        if hi - lo > _EPS:
            out.append((lo, hi))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return out


def feasible_intervals(lo: float, hi: float, need: float, *,
                       pad_left: bool, pad_right: bool,
                       clearance_on: bool, clearance_m: float,
                       power_on: bool, powered: list[tuple[float, float]]
                       ) -> list[tuple[float, float]]:
    """空档 [lo, hi) 在启用约束裁剪后、几何上能容纳 need 的全部子区间。

    pad_left/pad_right 标记该端是否挨着墙或挡柱（需让消防净距）；
    摊位占走后露出的一端挨着邻摊，不内缩（摊与摊紧贴）。
    放置扫描与拒因诊断共用本函数，保证成功与拒绝不可能用到两套判定。
    """
    clo = lo + (clearance_m if clearance_on and pad_left else 0.0)
    chi = hi - (clearance_m if clearance_on and pad_right else 0.0)
    if chi - clo + _EPS < need:
        return []
    if power_on:
        return [(a, b) for a, b in _intersect([(clo, chi)], powered)
                if b - a + _EPS >= need]
    return [(clo, chi)]


def _diagnose(remain: list[list], need: float, *, clearance_m: float,
              power_on: bool, powered: list[tuple[float, float]]) -> str:
    """第一拟合失败后定位唯一主因。

    各约束独立判定：只看裸空档、只加净距、只加供电分别能否放下；
    两条约束都独立失效时才按短路顺序 power > clearance 取舍，
    避免把「供电充足、净距不足」误记成供电问题。
    """
    clearance_on = clearance_m > 0.0

    def any_fit(*, use_clearance: bool, use_power: bool) -> bool:
        return any(
            feasible_intervals(
                lo, hi, need,
                pad_left=bool(pl), pad_right=bool(pr),
                clearance_on=use_clearance, clearance_m=clearance_m,
                power_on=use_power, powered=powered)
            for lo, hi, pl, pr in remain if hi - lo > _EPS
        )

    if not any_fit(use_clearance=False, use_power=False):
        return REASON_SPAN
    clearance_blocks = clearance_on and not any_fit(use_clearance=True, use_power=False)
    power_blocks = power_on and not any_fit(use_clearance=False, use_power=True)
    # 两类同时独立成立：固定短路，供电优先
    if power_blocks and clearance_blocks:
        return REASON_POWER
    if power_blocks:
        return REASON_POWER
    if clearance_blocks:
        return REASON_CLEARANCE
    # 单独都成立、交集（既满足净距又在供电范围内）放不下：按短路归供电
    if power_on and not any_fit(use_clearance=True, use_power=True):
        return REASON_POWER
    return REASON_SPAN


def allocate_first_fit(width_m: float, vendors: list[dict], pillars: list[dict],
                       clearance_m: float = 0.0, outlets: list[dict] | None = None) -> AllocResult:
    """vendors sorted by priority ascending then id.

    每个摊位需在某条空档内取得 stall_width_m 连续长度：不跨挡柱；
    clearance_m>0 时靠墙/柱端让消防净距（邻摊端不让）；
    needs_power 且街段有供电桩时须落在某桩覆盖内。
    remain 每条为 [lo, hi, pad_left, pad_right]，占用后邻摊端 pad 置 False。
    """
    outlets = outlets or []
    validate_config(width_m, vendors, pillars, clearance_m, outlets)
    spans = free_spans_from_pillars(width_m, pillars)
    remain: list[list] = [[a, b, True, True] for a, b in spans]
    powered = powered_unions(width_m, outlets)
    clearance_on = clearance_m > 0.0
    ordered = sorted(vendors, key=lambda v: (v.get("priority", 1), v["id"]))
    placements: list[Placement] = []
    rejected: list[Rejected] = []
    for v in ordered:
        need = float(v["stall_width_m"])
        power_on = bool(v.get("needs_power")) and len(outlets) > 0
        cand = None
        target_idx = -1
        for idx, span in enumerate(remain):
            lo, hi, pl, pr = span
            for sub_lo, sub_hi in feasible_intervals(
                    lo, hi, need,
                    pad_left=pl, pad_right=pr,
                    clearance_on=clearance_on, clearance_m=clearance_m,
                    power_on=power_on, powered=powered):
                start = max(lo, sub_lo)
                if start + need <= sub_hi + _EPS:
                    cand, target_idx = start, idx
                    break
            if target_idx >= 0:
                break
        if target_idx >= 0 and cand is not None:
            lo, hi, pl, pr = remain[target_idx]
            end = cand + need
            # 跳过的缺口（如未供电段）保留为独立空档；新露出的端挨着邻摊，不要求净距
            pieces: list[list] = []
            if cand - lo > _EPS:
                pieces.append([lo, cand, pl, False])
            if hi - end > _EPS:
                pieces.append([end, hi, False, pr])
            remain[target_idx:target_idx + 1] = pieces
            placements.append(Placement(v["id"], v["name"], round(cand, 3), round(end, 3),
                                         need, bool(v.get("needs_power"))))
        else:
            # 与放置扫描同一函数、同一份 remain 诊断；短路顺序 power > clearance > span，
            # 一条拒绝只带一个 code，绝不另立页面专用判定。
            code = _diagnose(remain, need, clearance_m=clearance_m,
                             power_on=power_on, powered=powered)
            rejected.append(Rejected(v["id"], v["name"], need, code, REASON_LABELS[code]))
    free = [(round(a, 3), round(b, 3)) for a, b, _pl, _pr in remain if b - a > 1e-6]
    return AllocResult(placements, rejected, free, clearance_m=clearance_m,
                       outlets=[dict(o) for o in outlets])


def result_to_dict(r: AllocResult) -> dict:
    return {
        "placements": [asdict(p) for p in r.placements],
        "rejected": [asdict(x) for x in r.rejected],
        "free_spans": [{"start_m": a, "end_m": b} for a, b in r.free_spans],
        "config": {
            "clearance_m": r.clearance_m,
            "outlets": r.outlets or [],
            "reason_precedence": list(REASON_PRECEDENCE),
        },
    }
