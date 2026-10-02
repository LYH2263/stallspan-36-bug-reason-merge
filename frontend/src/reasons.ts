// 拒因主因的唯一前端映射 —— 判定全部来自后端 reason_code，
// 这里只负责文案与配色；分配图 / 放不下页 / 运行抽屉共用本模块。
export const REASON_SPAN = 'span'
export const REASON_CLEARANCE = 'clearance'
export const REASON_POWER = 'power'

export interface ReasonMeta {
  code: string
  label: string
  hint: string
  badge: string
}

export const REASONS: Record<string, ReasonMeta> = {
  [REASON_POWER]: {
    code: REASON_POWER,
    label: '供电覆盖不足',
    hint: '摊位需要接电，但没有任何供电桩的覆盖范围能容纳其完整宽度',
    badge: 'reason-badge reason-power',
  },
  [REASON_CLEARANCE]: {
    code: REASON_CLEARANCE,
    label: '消防净距不足',
    hint: '裸空档放得下，但靠墙/柱端让出消防净距后连续长度不够',
    badge: 'reason-badge reason-clearance',
  },
  [REASON_SPAN]: {
    code: REASON_SPAN,
    label: '空档连续长度不足',
    hint: '没有足够长的连续空档（含被挡柱切开），与净距、供电无关',
    badge: 'reason-badge reason-span',
  },
}

// 固定短路顺序：供电 > 净距 > 空档（仅用于展示排序，与后端判定一致）
export const REASON_ORDER = [REASON_POWER, REASON_CLEARANCE, REASON_SPAN]

export function reasonMeta(code: string): ReasonMeta {
  return REASONS[code] || { code, label: code, hint: '', badge: 'badge-warn' }
}
