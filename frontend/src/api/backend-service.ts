import { request } from './client'
import { moduleMeta } from '@/data/modules'
import type { ActionResult, EntryRow, OverviewResult, PageResult } from '@/data/types'

export { moduleMeta }

export async function listEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<PageResult> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}?${query}`)
  if (!response.ok) throw new Error('业务数据读取失败')
  return await response.json()
}

export async function createEntry(
  key: string,
  values: Record<string, string>,
): Promise<ActionResult> {
  const response = await request(`/api/${key}`, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  return await response.json()
}

export async function runAction(
  key: string,
  id: number,
  action: string,
): Promise<ActionResult> {
  const response = await request(`/api/${key}/${id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ action }),
  })
  return await response.json()
}

export async function downloadEntries(
  key: string,
  filters: Record<string, string> = {},
): Promise<void> {
  const query = new URLSearchParams(filters).toString()
  const response = await request(`/api/${key}/export?${query}`)
  if (!response.ok) throw new Error('业务数据导出失败')
  const url = URL.createObjectURL(await response.blob())
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `${key}.csv`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
}

export async function loadOverview(): Promise<OverviewResult> {
  const response = await request('/api/overview')
  if (!response.ok) throw new Error('运营概览读取失败')
  return await response.json()
}

// ---------- 指标绑定直连与并发编辑 ----------

export type BindingEditResult = {
  ok: boolean
  message: string
  entry: EntryRow | null
  conflict: {
    type: string
    message: string
    canKeepMeasure: boolean
    mustReconfirm: boolean
    binding: Record<string, unknown> | null
    measure: Record<string, unknown> | null
  } | null
}

export async function getBindingContext(entryId: number): Promise<Record<string, unknown>> {
  const response = await request(`/api/metric_bind/${entryId}/context`)
  if (response.status === 404) throw new Error(`绑定 ${entryId} 不存在或已归档`)
  if (!response.ok) throw new Error('绑定上下文读取失败')
  return await response.json()
}

export async function getBindingByCode(bindCode: string): Promise<Record<string, unknown>> {
  const response = await request(`/api/metric_bind/by-code/${encodeURIComponent(bindCode)}`)
  if (response.status === 404) throw new Error(`绑定编号 ${bindCode} 不存在或已归档`)
  if (!response.ok) throw new Error('绑定编号解析失败')
  return await response.json()
}

export async function applyBindingMeasure(
  entryId: number,
  payload: {
    measureRef: string
    values: Record<string, string>
    expectedBindingRevision: number
    expectedMeasureRevision: number | null
  },
): Promise<BindingEditResult> {
  const response = await request(`/api/metric_bind/${entryId}/edit`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error('绑定修改提交失败')
  return await response.json()
}

export async function updateBindingFields(
  entryId: number,
  values: Record<string, string>,
  expectedRevision?: number,
): Promise<BindingEditResult> {
  const response = await request(`/api/metric_bind/${entryId}`, {
    method: 'PATCH',
    body: JSON.stringify({ values, expectedRevision: expectedRevision ?? null }),
  })
  if (!response.ok) throw new Error('绑定更新失败')
  return await response.json()
}

export async function duplicateBinding(entryId: number): Promise<BindingEditResult> {
  const response = await request(`/api/metric_bind/${entryId}/duplicate`, { method: 'POST' })
  if (!response.ok) throw new Error('复制绑定失败')
  return await response.json()
}

export async function restoreBinding(entryId: number): Promise<BindingEditResult> {
  const response = await request(`/api/metric_bind/${entryId}/restore`, { method: 'POST' })
  if (!response.ok) throw new Error('重新启用绑定失败')
  return await response.json()
}

export async function updateMeasureFields(
  entryId: number,
  values: Record<string, string>,
  expectedRevision?: number,
): Promise<BindingEditResult> {
  const response = await request(`/api/measure_catalog/${entryId}`, {
    method: 'PATCH',
    body: JSON.stringify({ values, expectedRevision: expectedRevision ?? null }),
  })
  if (!response.ok) throw new Error('度量更新失败')
  return await response.json()
}
