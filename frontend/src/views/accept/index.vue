<template>
  <section class="page" data-module="accept">
    <header class="page-head">
      <div>
        <h2>验收确认管理</h2>
        <p class="page-desc">维护验收单，围绕验收单号、关联任务、验收项目、验收标准做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记验收单</button>
        <button class="btn" type="button" @click="exportRows">导出验收确认清单</button>
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
            <template v-if="column === '验收状态'">
              <span :class="['status-tag', statusClass(row.status)]">{{ row.验收状态 }}</span>
            </template>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              :disabled="!availability(action, row).enabled"
              :title="availability(action, row).reason"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无验收确认数据，可先登记验收单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条验收确认记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="successMessage" class="success-text">{{ successMessage }}</span>
    </footer>

    <!-- 结论动作弹窗：提交的结论与等级会回写检修任务台账，历史等级保留 -->
    <div v-if="conclusionForm.open" class="modal-mask" @click.self="conclusionForm.open = false">
      <div class="modal-card">
        <h3>{{ conclusionForm.action }} · {{ conclusionForm.code }}</h3>
        <p class="page-desc">结论将回写到关联检修任务台账，重复提交只算一次，历次结论等级均会保留。</p>
        <label class="form-item">
          <span>验收结论</span>
          <input v-model="conclusionForm.conclusion" placeholder="留空使用默认结论" />
        </label>
        <label class="form-item">
          <span>验收人员</span>
          <input v-model="conclusionForm.inspector" placeholder="留空记为值班验收员" />
        </label>
        <label class="form-item">
          <span>验收日期</span>
          <input v-model="conclusionForm.date" type="date" />
        </label>
        <p v-if="conclusionForm.error" class="error-text">{{ conclusionForm.error }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" :disabled="conclusionForm.submitting" @click="conclusionForm.open = false">取消</button>
          <button class="btn primary" type="button" :disabled="conclusionForm.submitting" @click="submitConclusion">
            {{ conclusionForm.submitting ? '提交中…' : '提交结论' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null> & {
  id: number
  status: string
  last_action: string | null
}

const ENDPOINT = '/api/accept'
const columns = ["验收单号", "关联任务", "验收项目", "验收标准", "验收结论", "验收人员", "验收日期", "验收状态"]
const actions = ["开始验收", "确认通过", "下发返工"]
const stats = [{"label": "待验收单据", "value": 0}, {"label": "本月通过数", "value": 0}, {"label": "需返工项数", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const successMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const conclusionForm = reactive({
  open: false,
  submitting: false,
  id: 0,
  code: '',
  action: '确认通过',
  conclusion: '',
  inspector: '',
  date: '',
  error: '',
})

function statusClass(status: string) {
  return {
    待验收: 'status-pending',
    验收中: 'status-doing',
    已通过: 'status-ok',
    需返工: 'status-warn',
  }[status] ?? ''
}

/** 前端按同一套状态机约束按钮，后端仍会再校验一次并返回可读原因。 */
function availability(action: string, row: Row): { enabled: boolean; reason: string } {
  const status = String(row.status ?? '')
  if (action === '开始验收') {
    if (status === '验收中') return { enabled: false, reason: '已在验收中' }
    if (status === '已通过' || status === '需返工') return { enabled: false, reason: '验收已有结论' }
    return { enabled: true, reason: '' }
  }
  if (action === '确认通过') {
    if (status === '待验收') return { enabled: false, reason: '请先开始验收' }
    if (status === '已通过') return { enabled: false, reason: '已确认通过，重复提交只算一次' }
    return { enabled: true, reason: '' }
  }
  if (action === '下发返工') {
    if (status === '待验收') return { enabled: false, reason: '请先开始验收' }
    if (status === '已通过') return { enabled: false, reason: '已通过并归档' }
    if (status === '需返工') return { enabled: false, reason: '已下发返工，重复提交只算一次' }
    return { enabled: true, reason: '' }
  }
  return { enabled: false, reason: '未知动作' }
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '验收单登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  successMessage.value = ''
  const guard = availability(action, row)
  if (!guard.enabled) {
    errorMessage.value = guard.reason
    return
  }
  if (action === '确认通过' || action === '下发返工') {
    Object.assign(conclusionForm, {
      open: true,
      submitting: false,
      id: row.id,
      code: String(row.验收单号 ?? ''),
      action,
      conclusion: '',
      inspector: '',
      date: '',
      error: '',
    })
    return
  }
  await postAction(action, row.id, {})
}

async function submitConclusion() {
  conclusionForm.submitting = true
  conclusionForm.error = ''
  const values: Record<string, string> = { action: conclusionForm.action }
  if (conclusionForm.conclusion.trim()) values.验收结论 = conclusionForm.conclusion.trim()
  if (conclusionForm.inspector.trim()) values.验收人员 = conclusionForm.inspector.trim()
  if (conclusionForm.date) values.验收日期 = conclusionForm.date
  const ok = await postAction(conclusionForm.action, conclusionForm.id, values)
  conclusionForm.submitting = false
  if (ok) {
    conclusionForm.open = false
  }
}

async function postAction(action: string, id: number, values: Record<string, string>): Promise<boolean> {
  try {
    const response = await request(`${ENDPOINT}/${id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, ...values } }),
    })
    const payload = await response.json().catch(() => null)
    if (response.ok && payload?.ok === true) {
      successMessage.value = payload.message ?? '操作已生效'
      await reload()
      return true
    }
    const message = payload?.detail ?? payload?.message ?? '验收动作未生效，请稍后重试'
    if (conclusionForm.open) {
      conclusionForm.error = message
    } else {
      errorMessage.value = message
    }
    return false
  } catch (error) {
    const message = error instanceof Error ? error.message : '验收确认操作失败'
    if (conclusionForm.open) {
      conclusionForm.error = message
    } else {
      errorMessage.value = message
    }
    return false
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('验收单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '验收确认列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.page-actions { display: flex; gap: 8px; }
.status-tag { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 12px; }
.status-pending { background: #fef3c7; color: #92400e; }
.status-doing { background: #dbeafe; color: #1e40af; }
.status-ok { background: #dcfce7; color: #166534; }
.status-warn { background: #fee2e2; color: #991b1b; }
.link:disabled { color: #94a3b8; cursor: not-allowed; }
.success-text { color: #166534; }
</style>
