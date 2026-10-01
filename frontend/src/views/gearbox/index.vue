<template>
  <section class="page" data-module="gearbox">
    <header class="page-head">
      <div>
        <h2>齿轮箱管理</h2>
        <p class="page-desc">围绕齿轮箱编号、所属机组、油温上限、油品型号做登记、筛选与换油确认；列表与详情取数口径一致。</p>
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
      <label class="filter-item">
        <span>齿轮箱编号</span>
        <input v-model="keyword" placeholder="按齿轮箱编号检索" />
      </label>
      <label class="filter-item">
        <span>齿轮箱状态</span>
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
            <template v-if="column === '齿轮箱状态'">
              {{ row[column] ?? '—' }}
              <span v-if="row['油温异常']" class="badge badge-danger">油温异常</span>
            </template>
            <template v-else-if="column === '齿轮箱编号'">
              <RouterLink class="link" :to="`/gearbox/${row.id}`">{{ row[column] }}</RouterLink>
            </template>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openOilDialog(row)">确认换油</button>
            <button class="link" type="button" @click="runSimpleAction('登记油温异常', row)">登记油温异常</button>
            <button class="link" type="button" @click="runSimpleAction('更换齿轮箱', row)">更换齿轮箱</button>
            <RouterLink class="link" :to="`/gearbox/${row.id}`">详情</RouterLink>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无齿轮箱数据，可先登记齿轮箱</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条齿轮箱记录</span>
      <span v-if="notice" :class="noticeOk ? 'ok-text' : 'error-text'">{{ notice }}</span>
    </footer>

    <div v-if="oilDialog.open" class="modal-mask" @click.self="closeOilDialog">
      <div class="modal">
        <h3 class="modal-title">确认换油 · {{ oilDialog.row?.['齿轮箱编号'] }}</h3>
        <p class="modal-desc">一次确认会同时改定齿轮箱状态、油温上限、油品型号并清除油温异常标记。</p>
        <form class="modal-form" @submit.prevent="confirmOilChange">
          <label class="filter-item">
            <span>油温上限（℃）</span>
            <input v-model="oilDialog.limit" type="number" step="0.1" min="0" max="200" placeholder="如 80" />
          </label>
          <label class="filter-item">
            <span>油品型号</span>
            <input v-model="oilDialog.oilModel" placeholder="如 ISO VG 320" />
          </label>
          <span v-if="oilDialog.error" class="error-text">{{ oilDialog.error }}</span>
          <div class="modal-actions">
            <button class="btn" type="button" :disabled="oilDialog.submitting" @click="closeOilDialog">取消</button>
            <button class="btn primary" type="submit" :disabled="oilDialog.submitting">
              {{ oilDialog.submitting ? '提交中…' : '确认换油' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request, submitAction } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/gearbox'
const columns = ["齿轮箱编号", "所属机组", "油温上限", "振动值", "上次换油日", "下次换油日", "油品型号", "齿轮箱状态"]
const statuses = ["待换油", "运行正常", "油温偏高", "已更换"]

const rows = ref<Row[]>([])
const total = ref(0)
const notice = ref('')
const noticeOk = ref(false)
const keyword = ref('')
const statusFilter = ref('')

const oilDialog = reactive({
  open: false,
  submitting: false,
  error: '',
  row: null as Row | null,
  limit: '',
  oilModel: '',
})

const stats = computed(() => {
  const monthPrefix = new Date().toISOString().slice(0, 7)
  return [
    { label: '待换油齿轮箱', value: rows.value.filter((r) => r['齿轮箱状态'] === '待换油').length },
    { label: '油温偏高台数', value: rows.value.filter((r) => r['油温异常']).length },
    { label: '本月换油数', value: rows.value.filter((r) => String(r['上次换油日'] ?? '').startsWith(monthPrefix)).length },
  ]
})

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  showNotice('齿轮箱登记入口尚未接入审批流', false)
}

function showNotice(message: string, ok: boolean) {
  notice.value = message
  noticeOk.value = ok
}

function openOilDialog(row: Row) {
  oilDialog.open = true
  oilDialog.error = ''
  oilDialog.row = row
  oilDialog.limit = String(row['油温上限'] ?? '')
  oilDialog.oilModel = String(row['油品型号'] ?? '')
}

function closeOilDialog() {
  oilDialog.open = false
  oilDialog.row = null
  oilDialog.error = ''
}

async function confirmOilChange() {
  if (!oilDialog.row) return
  oilDialog.submitting = true
  oilDialog.error = ''
  try {
    const result = await submitAction(`${ENDPOINT}/${oilDialog.row.id}/actions`, {
      action: '确认换油',
      油温上限: oilDialog.limit,
      油品型号: oilDialog.oilModel,
    })
    if (!result.ok) {
      oilDialog.error = result.message
      return
    }
    closeOilDialog()
    await reload()
    showNotice(result.message, true)
  } catch (error) {
    oilDialog.error = error instanceof Error ? error.message : '换油确认失败，请稍后重试'
  } finally {
    oilDialog.submitting = false
  }
}

async function runSimpleAction(action: string, row: Row) {
  if (action === '更换齿轮箱' && !window.confirm(`确认将 ${row['齿轮箱编号']} 标记为已更换？`)) {
    return
  }
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
      throw new Error('齿轮箱列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    showNotice(error instanceof Error ? error.message : '齿轮箱列表读取失败', false)
  }
}

onMounted(reload)
</script>
