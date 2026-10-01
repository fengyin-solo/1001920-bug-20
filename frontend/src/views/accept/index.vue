<template>
  <section class="page" data-module="accept">
    <header class="page-head">
      <div>
        <h2>验收确认管理</h2>
        <p class="page-desc">验收结论回写台账并保留历史等级；重复提交只算一次，列表与详情取数口径一致。</p>
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
      <label class="filter-item">
        <span>验收单号</span>
        <input v-model="keyword" placeholder="按验收单号检索" />
      </label>
      <label class="filter-item">
        <span>验收状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
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
              {{ row[column] ?? '—' }}
              <span v-if="row['验收状态'] === '需返工'" class="badge badge-danger">需返工</span>
            </template>
            <template v-else-if="column === '验收结论'">
              {{ row[column] ?? '—' }}
              <button
                v-if="historyOf(row).length"
                class="link"
                type="button"
                @click="openHistory(row)"
              >（历史 {{ historyOf(row).length }} 条）</button>
            </template>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="runSimpleAction('开始验收', row)">开始验收</button>
            <button class="link" type="button" @click="openVerdictDialog('确认通过', row)">确认通过</button>
            <button class="link" type="button" @click="openVerdictDialog('下发返工', row)">下发返工</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无验收确认数据，可先登记验收单</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条验收确认记录</span>
      <span v-if="notice" :class="noticeOk ? 'ok-text' : 'error-text'">{{ notice }}</span>
    </footer>

    <div v-if="verdictDialog.open" class="modal-mask" @click.self="closeVerdictDialog">
      <div class="modal">
        <h3 class="modal-title">{{ verdictDialog.action }} · {{ verdictDialog.row?.['验收单号'] }}</h3>
        <p class="modal-desc">
          {{ verdictDialog.action === '确认通过'
            ? '通过后验收结论将回写台账，历史结论等级原样保留。'
            : '返工后结论登记为不合格并标记需返工，后续需复验重新出具结论。' }}
        </p>
        <form class="modal-form" @submit.prevent="submitVerdict">
          <label v-if="verdictDialog.action === '确认通过'" class="filter-item">
            <span>验收结论（等级）</span>
            <input v-model="verdictDialog.conclusion" placeholder="如 合格 / 优良" />
          </label>
          <label class="filter-item">
            <span>验收人员</span>
            <input v-model="verdictDialog.inspector" placeholder="请输入验收人员姓名" />
          </label>
          <span v-if="verdictDialog.error" class="error-text">{{ verdictDialog.error }}</span>
          <div class="modal-actions">
            <button class="btn" type="button" :disabled="verdictDialog.submitting" @click="closeVerdictDialog">取消</button>
            <button class="btn primary" type="submit" :disabled="verdictDialog.submitting">
              {{ verdictDialog.submitting ? '提交中…' : verdictDialog.action }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <div v-if="historyDialog.open" class="modal-mask" @click.self="historyDialog.open = false">
      <div class="modal">
        <h3 class="modal-title">结论历史 · {{ historyDialog.row?.['验收单号'] }}</h3>
        <table class="data-table">
          <thead>
            <tr><th>验收日期</th><th>验收结论</th><th>验收人员</th></tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in historyOf(historyDialog.row)" :key="index">
              <td>{{ item['验收日期'] ?? '—' }}</td>
              <td>{{ item['验收结论'] ?? '—' }}</td>
              <td>{{ item['验收人员'] ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
        <div class="modal-actions">
          <button class="btn primary" type="button" @click="historyDialog.open = false">关闭</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request, submitAction } from '@/api/client'

type HistoryItem = Record<string, string | null>
type Row = Record<string, string | number | boolean | HistoryItem[] | null>

const ENDPOINT = '/api/accept'
const columns = ["验收单号", "关联任务", "验收项目", "验收标准", "验收结论", "验收人员", "验收日期", "验收状态"]
const statuses = ["待验收", "验收中", "已通过", "需返工"]

const rows = ref<Row[]>([])
const total = ref(0)
const notice = ref('')
const noticeOk = ref(false)
const keyword = ref('')
const statusFilter = ref('')

const verdictDialog = reactive({
  open: false,
  submitting: false,
  error: '',
  action: '确认通过' as '确认通过' | '下发返工',
  row: null as Row | null,
  conclusion: '合格',
  inspector: '',
})

const historyDialog = reactive({ open: false, row: null as Row | null })

const stats = computed(() => [
  { label: '待验收单据', value: rows.value.filter((r) => r['验收状态'] === '待验收' || r['验收状态'] === '验收中').length },
  { label: '本月通过数', value: rows.value.filter((r) => r['验收状态'] === '已通过').length },
  { label: '需返工项数', value: rows.value.filter((r) => r['验收状态'] === '需返工').length },
])

function historyOf(row: Row | null): HistoryItem[] {
  const value = row?.['结论历史']
  return Array.isArray(value) ? (value as HistoryItem[]) : []
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  showNotice('验收单登记入口尚未接入审批流', false)
}

function showNotice(message: string, ok: boolean) {
  notice.value = message
  noticeOk.value = ok
}

function openVerdictDialog(action: '确认通过' | '下发返工', row: Row) {
  verdictDialog.open = true
  verdictDialog.error = ''
  verdictDialog.action = action
  verdictDialog.row = row
  verdictDialog.conclusion = String(row['验收结论'] ?? '合格') || '合格'
  verdictDialog.inspector = String(row['验收人员'] ?? '')
}

function closeVerdictDialog() {
  verdictDialog.open = false
  verdictDialog.row = null
  verdictDialog.error = ''
}

function openHistory(row: Row) {
  historyDialog.open = true
  historyDialog.row = row
}

async function submitVerdict() {
  if (!verdictDialog.row) return
  verdictDialog.submitting = true
  verdictDialog.error = ''
  try {
    const values: Record<string, string> = {
      action: verdictDialog.action,
      验收人员: verdictDialog.inspector,
    }
    if (verdictDialog.action === '确认通过') {
      values['验收结论'] = verdictDialog.conclusion
    }
    const result = await submitAction(`${ENDPOINT}/${verdictDialog.row.id}/actions`, values)
    if (!result.ok) {
      verdictDialog.error = result.message
      return
    }
    closeVerdictDialog()
    await reload()
    showNotice(result.message, true)
  } catch (error) {
    verdictDialog.error = error instanceof Error ? error.message : '验收结论提交失败，请稍后重试'
  } finally {
    verdictDialog.submitting = false
  }
}

async function runSimpleAction(action: string, row: Row) {
  try {
    const result = await submitAction(`${ENDPOINT}/${row.id}/actions`, { action })
    await reload()
    showNotice(result.message, result.ok)
  } catch (error) {
    showNotice(error instanceof Error ? error.message : '操作失败，请稍后重试', false)
  }
}

async function reload() {
  notice.value = ''
  const query = new URLSearchParams()
  if (keyword.value) query.set('keyword', keyword.value)
  if (statusFilter.value) query.set('status', statusFilter.value)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('验收单列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    showNotice(error instanceof Error ? error.message : '验收确认列表读取失败', false)
  }
}

onMounted(reload)
</script>
