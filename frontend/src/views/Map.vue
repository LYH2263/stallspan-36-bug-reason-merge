<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { REASON_ORDER, reasonMeta } from '../reasons'

const data = ref<any>(null)
const vendors = ref<any[]>([])
const runs = ref<any[]>([])
const drawerOpen = ref(false)
const viewingRunId = ref<number | null>(null)
const isHistory = ref(false)
const error = ref('')
const busy = ref(false)

async function loadLatest() {
  const d = await api<any>('/allocate/latest?segment_id=1')
  data.value = d
  viewingRunId.value = d.id ?? null
  isHistory.value = false
}
async function loadRuns() {
  runs.value = await api('/allocate/runs?segment_id=1&limit=30')
}
async function run() {
  busy.value = true
  error.value = ''
  try {
    // 提交瞬间按当前配置重分；非法配置返回 400，data 保持改前快照（主图不变）
    data.value = await api('/allocate/run?segment_id=1', { method: 'POST' })
    viewingRunId.value = data.value.id
    isHistory.value = false
    await loadRuns()
  } catch (e: any) {
    error.value = (e?.message || String(e)).replace(/^Error:\s*/, '')
  } finally {
    busy.value = false
  }
}
function viewRun(r: any) {
  // 历史运行只读快照：拒因与当时提交瞬间配置冻结在一起
  data.value = r
  viewingRunId.value = r.id
  isHistory.value = true
}
async function backToLatest() {
  await loadLatest()
}

onMounted(async () => {
  vendors.value = await api('/vendors')
  await loadLatest()
  await loadRuns()
})

const colors = ['#e8a87c','#85dcb8','#e27d60','#c38d9e','#41b3a3','#f4a261','#e76f51']
const width = computed(() => data.value?.segment?.width_m || 1)
const clearance = computed(() => data.value?.config?.clearance_m ?? data.value?.segment?.clearance_m ?? 0)
const outlets = computed<any[]>(() => data.value?.outlets || data.value?.config?.outlets || [])

const cells = computed(() => {
  if (!data.value) return []
  const out: any[] = []
  for (const p of data.value.pillars || []) {
    out.push({ type: 'pillar', start: p.position_m - p.thickness_m/2, w: p.thickness_m, label: p.label || '挡柱' })
  }
  for (const [i, p] of (data.value.placements || []).entries()) {
    out.push({ type: 'stall', start: p.start_m, w: p.width_m, label: p.vendor_name + (p.needs_power ? ' ⚡' : ''), color: colors[i % colors.length] })
  }
  return out.sort((a,b) => a.start - b.start)
})

// 供电覆盖层：绝对定位在分配带上，帮助肉眼定位「供电覆盖不足」
const coverage = computed(() =>
  outlets.value.map((o) => ({
    left: Math.max(0, o.position_m - o.coverage_radius_m) / width.value * 100,
    w: Math.min(width.value, o.position_m + o.coverage_radius_m) / width.value * 100
       - Math.max(0, o.position_m - o.coverage_radius_m) / width.value * 100,
    pos: o.position_m / width.value * 100,
    label: o.label || '供电桩',
  })),
)

const rejectedByReason = computed(() =>
  REASON_ORDER
    .map((code) => ({ code, meta: reasonMeta(code), items: (data.value?.rejected || []).filter((x: any) => x.reason_code === code) }))
    .filter((g) => g.items.length),
)
function reasonBreakdown(run: any) {
  const m = new Map<string, number>()
  for (const r of run.rejected || []) m.set(r.reason_code, (m.get(r.reason_code) || 0) + 1)
  return REASON_ORDER.filter((c) => m.has(c)).map((c) => ({ meta: reasonMeta(c), n: m.get(c)! }))
}
</script>
<template>
  <div class="ss-street-wrap">
    <h1>街段分配带</h1>
    <p class="sub">沿街一维开间 · 挡柱为竖直阻断 · ⚡ 为需供电摊 · 黄色覆盖带为供电桩范围</p>
    <div class="map-toolbar">
      <button class="btn" :disabled="busy" @click="run">{{ busy ? '分配中…' : '重新分配' }}</button>
      <button class="btn btn-ghost" @click="drawerOpen = !drawerOpen">运行抽屉 ({{ runs.length }})</button>
      <span v-if="isHistory" class="muted snapshot-tag">
        正在查看历史运行 #{{ viewingRunId }}（只读快照）
        <a href="#" @click.prevent="backToLatest">回到最新</a>
      </span>
    </div>
    <p v-if="error" class="map-error">⚠ {{ error }} —— 已拒绝落库，主图保持改前配置。</p>

    <div class="config-strip card" v-if="data">
      <span>街段：<strong>{{ data.segment.name }}</strong>（{{ data.segment.width_m }} m）</span>
      <span>消防净距：<strong :class="{ 'cfg-off': !clearance }">{{ clearance }} m</strong><em v-if="!clearance" class="muted">（0＝不检查）</em></span>
      <span>供电桩：<strong :class="{ 'cfg-off': !outlets.length }">{{ outlets.length }} 个</strong><em v-if="!outlets.length" class="muted">（无桩＝不检查供电）</em></span>
      <span>成功 {{ data.placements?.length || 0 }} · 放不下 {{ data.rejected?.length || 0 }}</span>
    </div>

    <div class="ss-band-ruler" v-if="data">
      <span>0 m</span>
      <span>运行 #{{ data.id }}</span>
      <span>{{ data.segment.width_m }} m</span>
    </div>
    <div class="ss-street-band" v-if="data">
      <div class="ss-coverage-layer">
        <div v-for="(c,i) in coverage" :key="'cov'+i" class="ss-coverage"
             :style="{ left: c.left + '%', width: c.w + '%' }">
          <span class="ss-outlet-tick" :style="{ left: ((c.pos - c.left) / c.w * 100) + '%' }">⚡{{ i + 1 }}</span>
        </div>
      </div>
      <div class="ss-street-inner">
        <div
          v-for="(c,i) in cells" :key="i"
          class="ss-band-cell"
          :class="{ 'ss-pillar': c.type === 'pillar' }"
          :style="{ width: (c.w / data.segment.width_m * 100) + '%', background: c.type === 'pillar' ? undefined : c.color, flex: '0 0 ' + (c.w / data.segment.width_m * 100) + '%' }"
        >{{ c.label }}</div>
      </div>
    </div>
    <div class="ss-vendor-queue">
      <div v-for="v in vendors" :key="v.id" class="ss-vendor-chip">
        <strong>{{ v.name }}<template v-if="v.needs_power"> ⚡</template></strong>
        <span>需 {{ v.stall_width_m }} m · 优先 {{ v.priority }}</span>
      </div>
    </div>

    <div v-if="data && (data.rejected?.length || 0) > 0" class="card">
      <h2 class="reject-h">放不下（与「放不下」页同源）</h2>
      <div v-for="g in rejectedByReason" :key="g.code" class="reject-line">
        <span :class="g.meta.badge">{{ g.meta.label }}</span>
        <span v-for="r in g.items" :key="r.vendor_id" class="reject-name">{{ r.vendor_name }}（{{ r.width_m }}m）</span>
      </div>
    </div>

    <div class="card" v-if="data">
      <table>
        <thead><tr><th>摊主</th><th>起点</th><th>终点</th><th>宽度</th><th>供电</th></tr></thead>
        <tbody>
          <tr v-for="p in data.placements" :key="p.vendor_id">
            <td>{{ p.vendor_name }}</td><td>{{ p.start_m }}</td><td>{{ p.end_m }}</td><td>{{ p.width_m }}</td>
            <td>{{ p.needs_power ? '⚡ 需要' : '—' }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <transition name="drawer">
      <aside v-if="drawerOpen" class="run-drawer">
        <header><strong>运行抽屉</strong><button class="drawer-x" @click="drawerOpen = false">×</button></header>
        <p class="muted drawer-note">每次成功提交冻结一版；非法配置 400 不会出现在这里。拒因按提交瞬间配置判定。</p>
        <div v-for="r in runs" :key="r.id" class="run-item"
             :class="{ active: r.id === viewingRunId }" @click="viewRun(r)">
          <div class="run-item-head">
            <strong>#{{ r.id }}</strong>
            <span class="muted">{{ (r.created_at || '').replace('T', ' ').slice(0, 19) }}</span>
          </div>
          <div class="run-item-counts">成功 {{ r.placements?.length || 0 }} · 放不下 {{ r.rejected?.length || 0 }}</div>
          <div class="run-item-reasons">
            <span v-for="b in reasonBreakdown(r)" :key="b.meta.code" :class="b.meta.badge">
              {{ b.meta.label }} ×{{ b.n }}
            </span>
            <em v-if="!(r.rejected?.length)" class="muted">全放下</em>
          </div>
        </div>
      </aside>
    </transition>
  </div>
</template>

<style scoped>
.map-toolbar { display: flex; align-items: center; gap: .6rem; margin-bottom: .5rem; flex-wrap: wrap; }
.btn-ghost { background: transparent; color: var(--ss-asphalt); border: 2px solid var(--ss-curb); box-shadow: none; }
.snapshot-tag { font-size: .78rem; }
.snapshot-tag a { color: var(--ss-accent); font-weight: 700; }
.map-error {
  background: rgba(163,58,44,.12); border: 2px solid var(--ss-bad); color: var(--ss-bad);
  padding: .45rem .7rem; border-radius: 4px; font-size: .85rem; font-weight: 700;
}
.config-strip { display: flex; gap: 1.2rem; flex-wrap: wrap; font-size: .82rem; padding: .5rem .8rem; }
.cfg-off { color: var(--ss-muted); }
.ss-coverage-layer { position: absolute; inset: 0; pointer-events: none; z-index: 1; }
.ss-coverage {
  position: absolute; top: 0; bottom: 0;
  background: rgba(242, 201, 76, 0.22);
  border-left: 1px dashed rgba(180,140,20,.6); border-right: 1px dashed rgba(180,140,20,.6);
}
.ss-outlet-tick {
  position: absolute; top: 2px; transform: translateX(-50%);
  font-size: .68rem; font-weight: 800; color: #6b5410;
  background: rgba(242,201,76,.9); border-radius: 2px; padding: 0 .2rem;
}
.ss-street-inner { z-index: 0; }
.reject-h { margin: 0 0 .45rem; font-size: .95rem; }
.reject-line { display: flex; align-items: center; gap: .5rem; flex-wrap: wrap; margin-bottom: .35rem; }
.reject-name { font-size: .8rem; background: rgba(0,0,0,.05); padding: .05rem .4rem; border-radius: 3px; }
.run-drawer {
  position: fixed; top: 42px; right: 0; bottom: 0; width: 320px; z-index: 20;
  background: var(--ss-paper); border-left: 3px solid var(--ss-accent);
  box-shadow: -8px 0 24px rgba(0,0,0,.25); padding: .8rem; overflow-y: auto;
}
.run-drawer header { display: flex; justify-content: space-between; align-items: center; margin-bottom: .4rem; }
.drawer-x { border: none; background: none; font-size: 1.3rem; cursor: pointer; line-height: 1; }
.drawer-note { font-size: .72rem; margin: 0 0 .6rem; }
.run-item { border: 2px solid rgba(92,74,50,.25); border-radius: 4px; padding: .45rem .55rem; margin-bottom: .5rem; cursor: pointer; }
.run-item:hover { border-color: var(--ss-curb); }
.run-item.active { border-color: var(--ss-accent); background: rgba(196,92,38,.07); }
.run-item-head { display: flex; justify-content: space-between; font-size: .82rem; }
.run-item-counts { font-size: .78rem; margin: .15rem 0; }
.run-item-reasons { display: flex; gap: .3rem; flex-wrap: wrap; }
.drawer-enter-from, .drawer-leave-to { transform: translateX(100%); }
.drawer-enter-active, .drawer-leave-active { transition: transform .18s ease; }
</style>
