<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const rows = ref<any[]>([])
onMounted(async () => { rows.value = await api('/vendors') })

async function togglePower(r: any) {
  const next = !r.needs_power
  try {
    const updated = await api(`/vendors/${r.id}`, { method: 'PATCH', body: JSON.stringify({ needs_power: next }) })
    Object.assign(r, updated)
  } catch {
    // 后端拒绝时保持原值（开关回退）
  }
}
</script>
<template>
  <h1>摊主队列</h1>
  <p class="sub">底部排队条 · 宽度与优先级 · ⚡ 需要供电（街段无供电桩时该约束自动关闭）</p>
  <div class="ss-vendor-queue" style="border-top:none; background:transparent; margin:0; padding:0.5rem 0 1rem">
    <div v-for="r in rows" :key="r.id ?? JSON.stringify(r)" class="ss-vendor-chip">
      <strong>{{ r.name }}<template v-if="r.needs_power"> ⚡</template></strong>
      <span>需 {{ r.stall_width_m }} m · 优先 {{ r.priority }}</span>
    </div>
  </div>
  <div class="card">
    <table>
      <thead><tr><th>摊主</th><th>宽度(m)</th><th>优先级</th><th>需要供电</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id ?? JSON.stringify(r)">
          <td>{{ r.name }}</td><td>{{ r.stall_width_m }}</td><td>{{ r.priority }}</td>
          <td>
            <label class="power-switch">
              <input type="checkbox" :checked="r.needs_power" @change="togglePower(r)">
              <span>{{ r.needs_power ? '⚡ 需要' : '不需要' }}</span>
            </label>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.power-switch { display: inline-flex; align-items: center; gap: .35rem; cursor: pointer; font-size: .85rem; }
</style>
