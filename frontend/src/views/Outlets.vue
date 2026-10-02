<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

const outlets = ref<any[]>([])
const segments = ref<any[]>([])
const segId = ref(1)
const position = ref('')
const radius = ref('20')
const error = ref('')
const busy = ref(false)

async function load() {
  outlets.value = await api('/outlets')
  if (!segments.value.length) segments.value = await api('/segments')
}
onMounted(load)

async function addOutlet() {
  error.value = ''
  const pos = Number(position.value), rad = Number(radius.value)
  if (!Number.isFinite(pos) || pos < 0) { error.value = '位置须为不小于 0 的数字'; return }
  if (!Number.isFinite(rad) || rad <= 0) { error.value = '覆盖半径须为正数'; return }
  busy.value = true
  try {
    // 非法（越界等）后端 400 拒绝落库，列表不变
    await api('/outlets', { method: 'POST', body: JSON.stringify({
      segment_id: segId.value, position_m: pos, coverage_radius_m: rad }) })
    position.value = ''
    await load()
  } catch (e: any) {
    error.value = (e?.message || String(e)).replace(/^Error:\s*/, '')
  } finally {
    busy.value = false
  }
}
async function remove(o: any) {
  await api(`/outlets/${o.id}`, { method: 'DELETE' })
  await load()
}
function segName(id: number) { return segments.value.find(s => s.id === id)?.name || ('#' + id) }
</script>
<template>
  <h1>供电桩</h1>
  <p class="sub">供电桩按覆盖半径供电 · 街段一个桩都没有时，供电约束关闭（不会出现「供电覆盖不足」）</p>

  <div class="card">
    <div class="outlet-form">
      <label>街段
        <select v-model.number="segId">
          <option v-for="s in segments" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
      </label>
      <label>位置(m) <input v-model="position" type="number" step="0.1" style="width:6rem"></label>
      <label>覆盖半径(m) <input v-model="radius" type="number" step="0.5" style="width:6rem"></label>
      <button class="btn" :disabled="busy" @click="addOutlet">添加供电桩</button>
    </div>
    <p v-if="error" class="cfg-msg cfg-msg-bad">⚠ {{ error }}（未保存）</p>
  </div>

  <div class="card">
    <table>
      <thead><tr><th>街段</th><th>位置(m)</th><th>覆盖半径(m)</th><th>覆盖区间</th><th></th></tr></thead>
      <tbody>
        <tr v-for="o in outlets" :key="o.id">
          <td>{{ segName(o.segment_id) }}</td>
          <td>{{ o.position_m }}</td>
          <td>{{ o.coverage_radius_m }}</td>
          <td class="muted">{{ Math.max(0, o.position_m - o.coverage_radius_m) }} ~ {{ o.position_m + o.coverage_radius_m }} m</td>
          <td><button class="btn btn-ghost" @click="remove(o)">删除</button></td>
        </tr>
      </tbody>
    </table>
    <p v-if="!outlets.length" class="muted">当前无供电桩 —— 与绿仓一致，任何摊位都不会因供电被拒。</p>
  </div>
</template>

<style scoped>
.outlet-form { display: flex; gap: .8rem; align-items: flex-end; flex-wrap: wrap; }
.outlet-form label { font-size: .8rem; color: var(--ss-muted); display: flex; flex-direction: column; gap: .2rem; }
.outlet-form input, .outlet-form select { padding: .3rem .4rem; }
.btn-ghost { background: transparent; color: var(--ss-bad); border: 2px solid rgba(163,58,44,.4); box-shadow: none; }
.cfg-msg { margin: .5rem 0 0; font-size: .82rem; font-weight: 700; }
.cfg-msg-bad { color: var(--ss-bad); }
</style>
