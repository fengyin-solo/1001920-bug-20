<template>
  <section class="page" data-module="gearbox-detail">
    <header class="page-head">
      <div>
        <h2>齿轮箱详情 <span class="muted-text">{{ entry?.['齿轮箱编号'] }}</span></h2>
        <p class="page-desc">详情页与列表页从同一后端接口取数；确认换油后状态、油温上限、油品型号与异常标记一并改定。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/gearbox">返回列表</RouterLink>
      </div>
    </header>

    <div v-if="loading" class="empty-state">正在加载齿轮箱明细…</div>
    <template v-else-if="entry">
      <div class="detail-grid">
        <article v-for="field in detailFields" :key="field" class="stat-card">
          <span class="stat-label">{{ field }}</span>
          <strong class="stat-value stat-value-sm">{{ entry[field] ?? '—' }}</strong>
        </article>
        <article class="stat-card">
          <span class="stat-label">油温异常标记</span>
          <strong class="stat-value stat-value-sm">
            <span :class="entry['油温异常'] ? 'badge badge-danger' : 'badge badge-ok'">
              {{ entry['油温异常'] ? '油温异常' : '正常' }}
            </span>
          </strong>
        </article>
      </div>

      <section class="panel">
        <h3 class="panel-title">确认换油</h3>
        <form class="filter-bar" @submit.prevent="confirmOilChange">
          <label class="filter-item">
            <span>油温上限（℃）</span>
            <input v-model="form.limit" type="number" step="0.1" min="0" max="200" placeholder="如 80" />
          </label>
          <label class="filter-item">
            <span>油品型号</span>
            <input v-model="form.oilModel" placeholder="如 ISO VG 320" />
          </label>
          <button class="btn primary" type="submit" :disabled="submitting">确认换油</button>
        </form>
        <div class="panel-actions">
          <button class="btn" type="button" :disabled="submitting" @click="runSimpleAction('登记油温异常')">登记油温异常</button>
          <button class="btn" type="button" :disabled="submitting" @click="replaceGearbox">更换齿轮箱</button>
        </div>
        <p v-if="notice" :class="noticeOk ? 'ok-text' : 'error-text'">{{ notice }}</p>
      </section>

      <section class="panel">
        <h3 class="panel-title">换油记录（{{ oilRecords.length }} 次）</h3>
        <table class="data-table">
          <thead>
            <tr>
              <th>上次换油日</th>
              <th>下次换油日</th>
              <th>油温上限（℃）</th>
              <th>油品型号</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(record, index) in oilRecords" :key="index">
              <td>{{ record['上次换油日'] ?? '—' }}</td>
              <td>{{ record['下次换油日'] ?? '—' }}</td>
              <td>{{ record['油温上限'] ?? '—' }}</td>
              <td>{{ record['油品型号'] ?? '—' }}</td>
            </tr>
            <tr v-if="!oilRecords.length">
              <td colspan="4" class="empty-state">暂无换油记录</td>
            </tr>
          </tbody>
        </table>
      </section>
    </template>
    <div v-else class="empty-state error-text">{{ loadError || '齿轮箱不存在或已归档' }}</div>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import { request, submitAction } from '@/api/client'

type RecordRow = Record<string, string | number | null>
type Entry = Record<string, string | number | boolean | RecordRow[] | null>

const ENDPOINT = '/api/gearbox'
const route = useRoute()
const entryId = Number(route.params.id)

const detailFields = ["齿轮箱编号", "所属机组", "油温上限", "振动值", "上次换油日", "下次换油日", "油品型号", "齿轮箱状态"]

const entry = ref<Entry | null>(null)
const loading = ref(true)
const loadError = ref('')
const submitting = ref(false)
const notice = ref('')
const noticeOk = ref(false)
const form = reactive({ limit: '', oilModel: '' })

const oilRecords = computed<RecordRow[]>(() => {
  const value = entry.value?.['换油记录']
  return Array.isArray(value) ? (value as RecordRow[]) : []
})

function hydrateForm() {
  form.limit = String(entry.value?.['油温上限'] ?? '')
  form.oilModel = String(entry.value?.['油品型号'] ?? '')
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const response = await request(`${ENDPOINT}/${entryId}`)
    if (!response.ok) {
      const data = (await response.json().catch(() => null)) as { detail?: string } | null
      throw new Error(data?.detail ?? `齿轮箱 ${entryId} 读取失败`)
    }
    entry.value = await response.json()
    hydrateForm()
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '齿轮箱明细读取失败'
  } finally {
    loading.value = false
  }
}

function showNotice(message: string, ok: boolean) {
  notice.value = message
  noticeOk.value = ok
}

async function confirmOilChange() {
  submitting.value = true
  notice.value = ''
  try {
    const result = await submitAction(`${ENDPOINT}/${entryId}/actions`, {
      action: '确认换油',
      油温上限: form.limit,
      油品型号: form.oilModel,
    })
    showNotice(result.message, result.ok)
    if (result.ok) await load()
  } catch (error) {
    showNotice(error instanceof Error ? error.message : '换油确认失败，请稍后重试', false)
  } finally {
    submitting.value = false
  }
}

async function runSimpleAction(action: string) {
  submitting.value = true
  notice.value = ''
  try {
    const result = await submitAction(`${ENDPOINT}/${entryId}/actions`, { action })
    showNotice(result.message, result.ok)
    if (result.ok) await load()
  } catch (error) {
    showNotice(error instanceof Error ? error.message : '操作失败，请稍后重试', false)
  } finally {
    submitting.value = false
  }
}

function replaceGearbox() {
  if (window.confirm('确认将该齿轮箱标记为已更换？')) {
    void runSimpleAction('更换齿轮箱')
  }
}

void load()
</script>
