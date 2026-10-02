<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { REASON_ORDER, reasonMeta } from '../reasons'

interface RejectedRow {
  vendor_id: number
  vendor_name: string
  width_m: number
  reason_code: string
  reason: string
}
const rows = ref<RejectedRow[]>([])
const loading = ref(true)
const runId = ref<number | null>(null)
const createdAt = ref<string | null>(null)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await api<any>('/allocate/latest?segment_id=1')
    rows.value = data.rejected || []
    runId.value = data.id
    createdAt.value = data.created_at || null
  } catch (e: any) {
    error.value = '读取最新分配失败：' + (e?.message || e)
  } finally {
    loading.value = false
  }
}
onMounted(load)

// 只按后端钉死的三类分组；永不出现笼统「放不下」
const groups = computed(() =>
  REASON_ORDER.map((code) => ({
    code,
    meta: reasonMeta(code),
    items: rows.value.filter((r) => r.reason_code === code),
  })).filter((g) => g.items.length > 0),
)
</script>
<template>
  <h1>放不下</h1>
  <p class="sub">每条拒绝只有一类主因 · 判定与分配图、运行抽屉完全同源 · 短路顺序：供电 &gt; 净距 &gt; 空档</p>

  <p v-if="error" class="card" style="color:var(--ss-bad)">{{ error }}</p>

  <div class="card" v-if="!loading && rows.length">
    <div class="muted" style="font-size:.78rem">
      取自运行 #{{ runId }}<span v-if="createdAt"> · {{ createdAt.replace('T', ' ').slice(0, 19) }}</span>
      提交瞬间的配置快照
    </div>
  </div>

  <div v-if="!loading && !rows.length && !error" class="card">
    <span class="badge badge-ok">全部放下</span>
    <span class="muted" style="margin-left:.5rem">当前配置下没有拒绝条目</span>
  </div>

  <section v-for="g in groups" :key="g.code" class="card reason-group">
    <header class="reason-group-head">
      <span :class="g.meta.badge">{{ g.meta.label }}</span>
      <strong>{{ g.items.length }}</strong>
      <span class="muted reason-hint">{{ g.meta.hint }}</span>
    </header>
    <table>
      <thead><tr><th>摊主</th><th>需求宽度</th><th>主因</th></tr></thead>
      <tbody>
        <tr v-for="r in g.items" :key="r.vendor_id">
          <td>{{ r.vendor_name }}</td>
          <td>{{ r.width_m }} m</td>
          <td><span :class="reasonMeta(r.reason_code).badge">{{ reasonMeta(r.reason_code).label }}</span></td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.reason-group { padding: 0.7rem 0.9rem; }
.reason-group-head { display: flex; align-items: center; gap: 0.6rem; margin-bottom: 0.4rem; }
.reason-group-head strong { font-size: 1.05rem; }
.reason-hint { font-size: 0.74rem; }
</style>
