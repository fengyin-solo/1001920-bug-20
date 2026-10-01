/**
 * 齿轮箱共享数据层：列表页与详情页都从这里取数，保证两边调用的是同一组后端接口、
 * 同一份字段口径（后端 serialize 输出），不会再出现两页读值不一致。
 */
import { request } from '@/api/client'

export const GEARBOX_ENDPOINT = '/api/gearbox'

export type GearboxRecord = {
  id: number
  齿轮箱编号: string
  所属机组: string
  油温上限: string
  振动值: string
  上次换油日: string
  下次换油日: string
  油品型号: string
  齿轮箱状态: string
  status: string
  pending: boolean
  abnormal: boolean
  last_action: string | null
  // 允许按中文字段列名取值（表格按 columns 渲染）
  [key: string]: string | number | boolean | null
}

export const OIL_ACTIONS = {
  oilChange: '确认换油',
  reportHighTemp: '登记油温异常',
  replace: '更换齿轮箱',
} as const

export const STATUS_PENDING = '待换油'
export const STATUS_NORMAL = '运行正常'
export const STATUS_HIGH_TEMP = '油温偏高'
export const STATUS_REPLACED = '已更换'

/** 动作在当前状态下是否允许执行；不允许时按钮置灰并给出原因。 */
export function actionAvailability(
  action: string,
  row: Pick<GearboxRecord, 'status' | 'last_action'>,
): { enabled: boolean; reason: string } {
  const { status, last_action } = row
  if (status === STATUS_REPLACED) {
    return { enabled: false, reason: '齿轮箱已更换归档' }
  }
  if (action === OIL_ACTIONS.oilChange) {
    if (status === STATUS_NORMAL && last_action === OIL_ACTIONS.oilChange) {
      return { enabled: false, reason: '已完成换油确认，无需重复提交' }
    }
    return { enabled: true, reason: '' }
  }
  if (action === OIL_ACTIONS.reportHighTemp) {
    if (status === STATUS_HIGH_TEMP) {
      return { enabled: false, reason: '油温异常已登记，等待换油' }
    }
    return { enabled: true, reason: '' }
  }
  if (action === OIL_ACTIONS.replace) {
    return { enabled: true, reason: '' }
  }
  return { enabled: false, reason: '未知动作' }
}

/** 读取动作接口的失败原因：优先展示后端 message，网络层失败时展示异常文案。 */
export async function readActionResult(
  response: Response,
  fallback: string,
): Promise<{ ok: boolean; message: string }> {
  try {
    const payload = await response.json()
    if (response.ok && typeof payload?.ok === 'boolean') {
      return { ok: payload.ok, message: payload.message ?? fallback }
    }
    return { ok: false, message: payload?.detail ?? payload?.message ?? fallback }
  } catch {
    return { ok: false, message: `接口返回异常（HTTP ${response.status}），数据未保存` }
  }
}

export async function fetchGearbox(id: number): Promise<GearboxRecord> {
  const response = await request(`${GEARBOX_ENDPOINT}/${id}`)
  if (!response.ok) {
    let detail = `齿轮箱 ${id} 读取失败`
    try {
      detail = (await response.json())?.detail ?? detail
    } catch {
      /* 保留默认说明 */
    }
    throw new Error(detail)
  }
  return (await response.json()) as GearboxRecord
}
