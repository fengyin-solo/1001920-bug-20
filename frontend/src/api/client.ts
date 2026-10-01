/** 统一请求封装：拼后端地址、抛网络错误、给页脚留一句可读的说明。 */
const API_BASE = import.meta.env.VITE_API_BASE ?? ''

export function request(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  return fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  }).catch((error: unknown) => {
    const detail = error instanceof Error ? error.message : '请求未送达'
    throw new Error(`接口请求失败：${detail}`)
  })
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) {
    throw new Error(`接口返回 ${response.status}，数据未更新`)
  }
  return (await response.json()) as T
}

export interface ActionResponse {
  ok: boolean
  message: string
  entry: Record<string, unknown> | null
}

/** 提交动作：后端业务失败也是 HTTP 200（ok=false），这里统一转成可读 message。 */
export async function submitAction(
  path: string,
  values: Record<string, unknown>,
): Promise<ActionResponse> {
  const response = await request(path, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  if (!response.ok) {
    let detail = `接口返回 ${response.status}`
    try {
      const data = (await response.json()) as { detail?: string }
      if (data.detail) detail = data.detail
    } catch {
      // 响应体不是 JSON 时保留默认说明
    }
    return { ok: false, message: detail, entry: null }
  }
  return (await response.json()) as ActionResponse
}
