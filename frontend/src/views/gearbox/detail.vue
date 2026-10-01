<template>
  <section class="page" data-module="gearbox-detail">
    <header class="page-head">
      <div>
        <h2>齿轮箱详情 · {{ record?.齿轮箱编号 ?? '—' }}</h2>
        <p class="page-desc">
          本页与换油记录列表读取同一个后端接口（GET /api/gearbox/:id），字段口径完全一致。
        </p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/gearbox">返回列表</RouterLink>
      </div>
    </header>

    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>

    <template v-if="record">
      <div class="detail-head">
        <span :class="['status-tag', statusClass(record.status)]">{{ record.齿轮箱状态 }}</span>
        <span v-if="record.abnormal" class="abnormal-tag">油温异常未消除</span>
        <span class="muted-text">最近动作：{{ record.last_action ?? '暂无' }}</span>
      </div>

      <!-- 可执行动作：状态与列表页同一套判定，重复确认不会推回待换油 -->
      <div class="action-bar">
        <button
          v-for="action in actions"
          :key="action.name"
          class="btn"
          :class="{ primary: action.name === '确认换油' }"
          type="button"
          :disabled="!availability(action.name, record).enabled || busy"
          :title="availability(action.name, record).reason"
          @click="onAction(action.name)"
        >
          {{ action.name }}
        </button>
      </div>

      <table class="data-table detail-table">
        <tbody>
          <tr v-for="field in displayFields" :key="field">
            <th>{{ field }}</th>
            <td>{{ record?.[field] || '—' }}</td>
          </tr>
          <tr v-if="record">
            <th>内部流转状态</th>
            <td>{{ record.status }}（pending: {{ String(record.pending) }}，abnormal: {{ String(record.abnormal) }}）</td>
          </tr>
        </tbody>
      </table>

      <!-- 台账编辑：保存失败时给出后端返回的可读原因 -->
      <h3 class="block-title">编辑台账字段</h3>
      <form class="edit-form" @submit.prevent="saveEdit">
        <label v-for="field in editableFields" :key="field" class="form-item">
          <span>{{ field }}</span>
          <input
            v-model="editForm[field]"
            :type="field.includes('日') ? 'date' : field === '油温上限' ? 'number' : 'text'"
          />
        </label>
        <div class="modal-actions">
          <button class="btn primary" type="button" :disabled="saving" @click="saveEdit">
            {{ saving ? '保存中…' : '保存台账' }}
          </button>
          <button class="btn ghost" type="button" @click="resetEdit">重置</button>
        </div>
        <p v-if="editError" class="error-text">{{ editError }}</p>
        <p v-if="editSuccess" class="success-text">{{ editSuccess }}</p>
      </form>
    </template>

    <!-- 确认换油弹窗（与列表页同一接口、同一校验） -->
    <div v-if="oilForm.open" class="modal-mask" @click.self="closeOilChange">
      <div class="modal-card">
        <h3>确认换油 · {{ record?.齿轮箱编号 }}</h3>
        <label class="form-item">
          <span>油品型号 <em>*</em></span>
          <input v-model="oilForm.油品型号" placeholder="例如 ISO VG 460" />
        </label>
        <label class="form-item">
          <span>油温上限（℃） <em>*</em></span>
          <input v-model="oilForm.油温上限" placeholder="例如 75" type="number" />
        </label>
        <label class="form-item">
          <span>下次换油日</span>
          <input v-model="oilForm.下次换油日" placeholder="留空按 180 天周期自动推算" type="date" />
        </label>
        <p v-if="oilForm.error" class="error-text">{{ oilForm.error }}</p>
        <div class="modal-actions">
          <button class="btn ghost" type="button" :disabled="busy" @click="closeOilChange">取消</button>
          <button class="btn primary" type="button" :disabled="busy" @click="submitOilChange">
            {{ busy ? '提交中…' : '确认换油' }}
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import { request } from '@/api/client'
import {
  actionAvailability,
  fetchGearbox,
  GEARBOX_ENDPOINT,
  OIL_ACTIONS,
  readActionResult,
  type GearboxRecord,
} from './api'

const route = useRoute()

const actions = [
  { name: OIL_ACTIONS.oilChange },
  { name: OIL_ACTIONS.reportHighTemp },
  { name: OIL_ACTIONS.replace },
]
const displayFields = [
  '齿轮箱编号', '所属机组', '油温上限', '振动值',
  '上次换油日', '下次换油日', '油品型号',
]
const editableFields = ['所属机组', '油温上限', '振动值', '上次换油日', '下次换油日', '油品型号']

const record = ref<GearboxRecord | null>(null)
const errorMessage = ref('')
const busy = ref(false)
const saving = ref(false)
const editError = ref('')
const editSuccess = ref('')

const editForm = reactive<Record<string, string>>({})
const oilForm = reactive({
  open: false,
  油品型号: '',
  油温上限: '',
  下次换油日: '',
  error: '',
})

function entryId(): number {
  return Number(route.params.id)
}

function statusClass(status: string) {
  return {
    待换油: 'status-pending',
    运行正常: 'status-ok',
    油温偏高: 'status-warn',
    已更换: 'status-done',
  }[status] ?? ''
}

function availability(action: string, row: GearboxRecord) {
  return actionAvailability(action, row)
}

async function load() {
  errorMessage.value = ''
  try {
    record.value = await fetchGearbox(entryId())
    resetEdit()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '齿轮箱详情读取失败'
  }
}

function resetEdit() {
  if (!record.value) return
  for (const field of editableFields) {
    editForm[field] = String(record.value[field] ?? '')
  }
  editError.value = ''
  editSuccess.value = ''
}

function onAction(action: string) {
  if (!record.value) return
  const guard = actionAvailability(action, record.value)
  if (!guard.enabled) {
    editError.value = guard.reason
    return
  }
  if (action === OIL_ACTIONS.oilChange) {
    Object.assign(oilForm, {
      open: true,
      油品型号: record.value.油品型号 ?? '',
      油温上限: record.value.油温上限 ?? '',
      下次换油日: '',
      error: '',
    })
    return
  }
  void submitAction(action, {})
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
  await submitAction(OIL_ACTIONS.oilChange, {
    油品型号: oilForm.油品型号.trim(),
    油温上限: String(oilForm.油温上限).trim(),
    ...(oilForm.下次换油日 ? { 下次换油日: oilForm.下次换油日 } : {}),
  })
  if (!oilForm.error) {
    oilForm.open = false
  }
}

async function submitAction(action: string, values: Record<string, string>) {
  busy.value = true
  editError.value = ''
  editSuccess.value = ''
  try {
    const response = await request(`${GEARBOX_ENDPOINT}/${entryId()}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, ...values } }),
    })
    const result = await readActionResult(response, '操作未生效，请稍后重试')
    if (!result.ok) {
      if (action === OIL_ACTIONS.oilChange) {
        oilForm.error = result.message
      } else {
        editError.value = result.message
      }
      return
    }
    editSuccess.value = result.message
    await load()
  } catch (error) {
    const message = error instanceof Error ? error.message : '请求失败'
    if (action === OIL_ACTIONS.oilChange) {
      oilForm.error = message
    } else {
      editError.value = message
    }
  } finally {
    busy.value = false
  }
}

async function saveEdit() {
  saving.value = true
  editError.value = ''
  editSuccess.value = ''
  const values: Record<string, string> = {}
  for (const field of editableFields) {
    const text = editForm[field]?.trim() ?? ''
    if (text) {
      values[field] = text
    }
  }
  try {
    const response = await request(`${GEARBOX_ENDPOINT}/${entryId()}`, {
      method: 'PATCH',
      body: JSON.stringify({ values }),
    })
    const result = await readActionResult(response, '台账保存失败，请稍后重试')
    if (!result.ok) {
      editError.value = result.message
      return
    }
    editSuccess.value = result.message
    await load()
  } catch (error) {
    editError.value = error instanceof Error ? error.message : '台账保存请求失败'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.page-actions { display: flex; gap: 8px; }
.detail-head { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.status-tag { display: inline-block; padding: 2px 10px; border-radius: 10px; font-size: 13px; }
.status-pending { background: #fef3c7; color: #92400e; }
.status-ok { background: #dcfce7; color: #166534; }
.status-warn { background: #fee2e2; color: #991b1b; }
.status-done { background: #e2e8f0; color: #475569; }
.abnormal-tag { padding: 2px 8px; border-radius: 4px; font-size: 12px; background: #fecaca; color: #b42318; }
.muted-text { color: #64748b; font-size: 12px; }
.action-bar { display: flex; gap: 8px; margin-bottom: 14px; }
.detail-table th { width: 180px; background: #f8fafc; }
.block-title { margin: 18px 0 8px; font-size: 15px; }
.edit-form { background: #fff; border: 1px solid #d8dee6; border-radius: 8px; padding: 12px; }
.success-text { color: #166534; }
.btn:disabled { opacity: .55; cursor: not-allowed; }
</style>
