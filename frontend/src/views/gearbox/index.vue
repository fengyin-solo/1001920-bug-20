<template>
  <section class="page" data-module="gearbox">
    <header class="page-head">
      <div>
        <h2>齿轮箱管理</h2>
        <p class="page-desc">维护齿轮箱，围绕齿轮箱编号、所属机组、油温上限、振动值做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记齿轮箱</button>
        <button class="btn" type="button" @click="exportRows">导出齿轮箱清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <template v-if="column === '齿轮箱编号'">
              <RouterLink class="link" :to="`/gearbox/${row.id}`">{{ row[column] }}</RouterLink>
            </template>
            <template v-else-if="column === '齿轮箱状态'">
              <span :class="['status-tag', statusClass(row.status)]">{{ row.齿轮箱状态 }}</span>
              <span v-if="row.abnormal" class="abnormal-tag" title="已登记油温异常">油温异常</span>
            </template>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <template v-for="action in actions" :key="action">
              <button
                v-if="action === '确认换油'"
                class="link"
                type="button"
                @click="openOilChange(row)"
              >
                {{ action }}
              </button>
              <button
                v-else
                class="link"
                type="button"
                :disabled="!availability(action, row).enabled"
                :title="availability(action, row).reason"
                @click="runAction(action, row, {})"
              >
                {{ action }}
              </button>
            </template>
            <RouterLink class="link detail-link" :to="`/gearbox/${row.id}`">详情</RouterLink>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无齿轮箱数据，可先登记齿轮箱</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条齿轮箱记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="successMessage" class="success-text">{{ successMessage }}</span>
    </footer>

    <!-- 确认换油弹窗：油品型号、油温上限为本轮换油必须改定的字段 -->
    <div v-if="oilForm.open" class="modal-mask" @click.self="closeOilChange">
      <div class="modal-card">
        <h3>确认换油 · {{ oilForm.code }}</h3>
        <p class="page-desc">
          提交后状态、油温上限、油品型号、上次/下次换油日与异常标记会一次性改定；
          重复提交不会把记录推回待换油。
        </p>
        <label class="form-item">
          <span>油品型号 <em>*</em></span>
          <input v-model="oilForm.油品型号" placeholder="例如 ISO VG 460" />
        </label>
        <label class="form-item">
          <span>油温上限（℃） <em>*</em></span>
          <input v-model="oilForm.油温上限" placeholder="例如 75" />
        </label>
        <label class="form-item">
          <span>下次换油日</span>
          <input v-model="oilForm.下次换油日" placeholder="留空按 180 天周期自动推算" type="date" />
        </label>
        <p v-if="oilForm.error" class="error-text">{{ oilForm.error }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" :disabled="oilForm.submitting" @click="closeOilChange">取消</button>
          <button class="btn primary" type="button" :disabled="oilForm.submitting" @click="submitOilChange">
            {{ oilForm.submitting ? '提交中…' : '确认换油' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import {
  actionAvailability,
  GEARBOX_ENDPOINT,
  OIL_ACTIONS,
  readActionResult,
  type GearboxRecord,
} from './api'

const columns = ["齿轮箱编号", "所属机组", "油温上限", "振动值", "上次换油日", "下次换油日", "油品型号", "齿轮箱状态"]
const actions = ["确认换油", "登记油温异常", "更换齿轮箱"]
const stats = [{"label": "待换油齿轮箱", "value": 0}, {"label": "油温偏高台数", "value": 0}, {"label": "本月换油数", "value": 0}]

const rows = ref<GearboxRecord[]>([])
const total = ref(0)
const errorMessage = ref('')
const successMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const oilForm = reactive({
  open: false,
  submitting: false,
  id: 0,
  code: '',
  油品型号: '',
  油温上限: '',
  下次换油日: '',
  error: '',
})

function availability(action: string, row: GearboxRecord) {
  return actionAvailability(action, row)
}

function statusClass(status: string) {
  return {
    待换油: 'status-pending',
    运行正常: 'status-ok',
    油温偏高: 'status-warn',
    已更换: 'status-done',
  }[status] ?? ''
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${GEARBOX_ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '齿轮箱登记入口尚未接入审批流'
}

function openOilChange(row: GearboxRecord) {
  const guard = actionAvailability(OIL_ACTIONS.oilChange, row)
  if (!guard.enabled) {
    errorMessage.value = guard.reason
    return
  }
  Object.assign(oilForm, {
    open: true,
    submitting: false,
    id: row.id,
    code: row.齿轮箱编号,
    油品型号: row.油品型号 ?? '',
    油温上限: row.油温上限 ?? '',
    下次换油日: '',
    error: '',
  })
}

function closeOilChange() {
  oilForm.open = false
}

async function submitOilChange() {
  oilForm.error = ''
  if (!oilForm.油品型号.trim()) {
    oilForm.error = '请填写本次加注的油品型号'
    return
  }
  if (!String(oilForm.油温上限).trim()) {
    oilForm.error = '请填写油温上限（摄氏度数字）'
    return
  }
  oilForm.submitting = true
  try {
    const response = await request(`${GEARBOX_ENDPOINT}/${oilForm.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({
        values: {
          action: OIL_ACTIONS.oilChange,
          油品型号: oilForm.油品型号.trim(),
          油温上限: String(oilForm.油温上限).trim(),
          ...(oilForm.下次换油日 ? { 下次换油日: oilForm.下次换油日 } : {}),
        },
      }),
    })
    const result = await readActionResult(response, '换油确认未生效，请稍后重试')
    if (!result.ok) {
      oilForm.error = result.message
      return
    }
    oilForm.open = false
    successMessage.value = result.message
    await reload()
  } catch (error) {
    oilForm.error = error instanceof Error ? error.message : '换油确认请求失败'
  } finally {
    oilForm.submitting = false
  }
}

async function runAction(action: string, row: GearboxRecord, values: Record<string, string>) {
  errorMessage.value = ''
  successMessage.value = ''
  const guard = actionAvailability(action, row)
  if (!guard.enabled) {
    errorMessage.value = guard.reason
    return
  }
  try {
    const response = await request(`${GEARBOX_ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, ...values } }),
    })
    const result = await readActionResult(response, '齿轮箱动作未生效，请稍后重试')
    if (!result.ok) {
      errorMessage.value = result.message
      return
    }
    successMessage.value = result.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '齿轮箱操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${GEARBOX_ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('齿轮箱列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '齿轮箱列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.page-actions { display: flex; gap: 8px; }
.status-tag { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 12px; }
.status-pending { background: #fef3c7; color: #92400e; }
.status-ok { background: #dcfce7; color: #166534; }
.status-warn { background: #fee2e2; color: #991b1b; }
.status-done { background: #e2e8f0; color: #475569; }
.abnormal-tag { display: inline-block; margin-left: 6px; padding: 1px 6px; border-radius: 4px; font-size: 11px; background: #fecaca; color: #b42318; }
.detail-link { margin-left: 8px; }
.link:disabled { color: #94a3b8; cursor: not-allowed; }
.success-text { color: #166534; }
</style>
