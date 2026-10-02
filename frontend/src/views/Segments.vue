<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
const drafts = ref<Record<number, string>>({})
const errors = ref<Record<number, string>>({})
const saving = ref<number | null>(null)

async function load() {
  rows.value = await api('/segments')
  drafts.value = {}
  errors.value = {}
  for (const r of rows.value) drafts.value[r.id] = String(r.clearance_m ?? 0)
}
onMounted(load)

async function saveClearance(r: any) {
  const val = Number(drafts.value[r.id])
  errors.value[r.id] = ''
  if (!Number.isFinite(val) || val < 0) {
    errors.value[r.id] = '净距须为不小于 0 的数字；0 表示不检查消防净距'
    drafts.value[r.id] = String(r.clearance_m ?? 0)
    return
  }
  saving.value = r.id
  try {
    // 非法配置后端 400 拒绝落库：本地行也回滚为改前值
    const updated = await api(`/segments/${r.id}`, { method: 'PATCH', body: JSON.stringify({ clearance_m: val }) })
    Object.assign(r, updated)
    drafts.value[r.id] = String(updated.clearance_m)
  } catch (e: any) {
    errors.value[r.id] = (e?.message || String(e)).replace(/^Error:\s*/, '')
    drafts.value[r.id] = String(r.clearance_m ?? 0)
  } finally {
    saving.value = null
  }
}
</script>
<template>
  <h1>街段</h1>
  <p class="sub">沿街可用宽度与消防净距 · 净距默认 0（不检查），改大后须重新分配才生效</p>
  <div class="card">
    <table>
      <thead><tr><th>街段</th><th>宽度(m)</th><th>消防净距(m)</th><th></th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id">
          <td>{{ r.name }}</td>
          <td>{{ r.width_m }}</td>
          <td>
            <input v-model.number="drafts[r.id]" type="number" min="0" step="0.1" style="width:5.5rem"
                   @keyup.enter="saveClearance(r)">
          </td>
          <td><button class="btn" :disabled="saving === r.id" @click="saveClearance(r)">保存净距</button></td>
        </tr>
      </tbody>
    </table>
    <p v-for="(msg, id) in errors" :key="'e' + id" class="cfg-msg cfg-msg-bad">⚠ {{ msg }}（配置未保存，主图保持改前）</p>
    <p class="muted" style="font-size:.75rem">提示：净距只在靠墙/挡柱端让出，摊位之间紧贴；净距为 0 时绝不会出现「消防净距不足」。</p>
  </div>
</template>

<style scoped>
.cfg-msg { margin: .35rem 0 0; font-size: .8rem; font-weight: 700; }
.cfg-msg-bad { color: var(--ss-bad); }
</style>
