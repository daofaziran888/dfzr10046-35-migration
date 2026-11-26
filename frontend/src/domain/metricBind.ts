/**
 * 指标绑定编辑工作流：直连路由、跨模块选度量与并发冲突的纯前端领域层。
 *
 * 关键约束：
 * - 草稿按“编辑会话”存放，而不是按绑定编号；同一编号的两个页面互不覆盖。
 * - 会话标识写进当前 history entry 的 state，刷新与后退都能找回同一份草稿。
 * - 冲突分型由绑定版本与度量版本各自独立判定，据此决定能否沿用所选度量、
 *   是否必须重新取得编辑确认。
 */

export const EDITABLE_STATUSES = ['待生效', '生效中'] as const
export const INVALID_STATUSES = ['已替换', '已解除'] as const

export type BindingSnapshot = {
  id: number
  code: string
  name: string
  measureRef: string
  dimension: string
  caliber: string
  timeWindow: string
  version: string
  status: string
  revision: number
}

export type MeasureSnapshot = {
  id: number
  code: string
  name: string
  expression: string
  status: string
  revision: number
}

export type Ownership = {
  moduleKey: string
  moduleName: string
  entity: string
  entryId: number
  bindingCode: string
  metricName: string
  dimension: string
  measureRef: string
  status: string
}

export type FollowUp = { action: string; label: string }

export type BindingContext = {
  binding: BindingSnapshot
  measure: MeasureSnapshot | null
  editable: boolean
  invalid: boolean
  ownership: Ownership
  followUps: FollowUp[]
}

export type ConflictType =
  | 'binding_changed'
  | 'measure_changed'
  | 'binding_and_measure_changed'
  | 'measure_missing'
  | 'binding_invalid'
  | 'binding_missing'

export type BindingConflict = {
  type: ConflictType
  message: string
  canKeepMeasure: boolean
  mustReconfirm: boolean
  binding: BindingSnapshot | null
  measure: MeasureSnapshot | null
}

export type BindingDraft = {
  sessionId: string
  entryId: number
  values: Record<string, string>
  selectedMeasureRef: string
  selectedMeasureName: string
  selectedMeasureExpression: string
  baseBindingRevision: number
  baseMeasureRevision: number | null
  updatedAt: number
}

export const EDITABLE_FIELDS = ['指标名称', '绑定维度', '统计口径', '时间窗口', '绑定版本'] as const

const MEMORY = new Map<string, BindingDraft>()
const SESSION_STATE_KEY = 'metricBindSession'
const SESSION_ENTRY_KEY = 'metricBindSessionEntry'
const DRAFT_KEY_PREFIX = 'metricBind:draft:'

function randomId(): string {
  const cryptoApi = globalThis.crypto
  if (cryptoApi && typeof cryptoApi.randomUUID === 'function') {
    return cryptoApi.randomUUID()
  }
  return `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`
}

function canUseSessionStorage(): boolean {
  try {
    return typeof window !== 'undefined' && Boolean(window.sessionStorage)
  } catch {
    return false
  }
}

/**
 * 解析当前编辑会话：优先显式参数，其次当前 history entry 上记录的会话，
 * 最后才新建。两个页面各自持有自己的 history entry，因此不会共用会话。
 */
export function resolveSessionId(explicit?: string | null): string {
  if (explicit) return explicit
  if (typeof window !== 'undefined') {
    const state = (window.history.state ?? {}) as Record<string, unknown>
    const existing = state[SESSION_STATE_KEY]
    if (typeof existing === 'string' && existing) return existing
  }
  const id = randomId()
  rememberSession(id)
  return id
}

/** 把会话标识写回当前 history entry，刷新/后退后仍能定位同一份草稿。 */
export function rememberSession(sessionId: string, boundEntryId?: number): void {
  if (typeof window === 'undefined') return
  const state: Record<string, unknown> = {
    ...(window.history.state ?? {}),
    [SESSION_STATE_KEY]: sessionId,
  }
  if (boundEntryId != null) state[SESSION_ENTRY_KEY] = boundEntryId
  window.history.replaceState(state, '', window.location.href)
}

export function sessionIdFromState(): string | null {
  if (typeof window === 'undefined') return null
  const state = (window.history.state ?? {}) as Record<string, unknown>
  const value = state[SESSION_STATE_KEY]
  return typeof value === 'string' ? value : null
}

/**
 * 只回传“属于这份绑定”的会话，避免从绑定 1 后退/跳转到绑定 4 时把会话带过去。
 */
export function sessionIdForEntry(entryId: number): string | null {
  if (typeof window === 'undefined') return null
  const state = (window.history.state ?? {}) as Record<string, unknown>
  if (state[SESSION_ENTRY_KEY] !== entryId) return null
  const value = state[SESSION_STATE_KEY]
  return typeof value === 'string' ? value : null
}

/**
 * 本 history entry 上是否已经消费过从度量目录带回的选择。
 * 用 history state 而不是组件内变量，刷新后也不会重复套用同一份参数。
 */
export function measurePickConsumed(): boolean {
  if (typeof window === 'undefined') return false
  const state = (window.history.state ?? {}) as Record<string, unknown>
  return state['metricBindPickConsumed'] === true
}

export function markMeasurePickConsumed(consumed: boolean): void {
  if (typeof window === 'undefined') return
  const state = { ...(window.history.state ?? {}), metricBindPickConsumed: consumed }
  window.history.replaceState(state, '', window.location.href)
}

function snapshotValues(binding: BindingSnapshot): Record<string, string> {
  return {
    指标名称: binding.name,
    绑定维度: binding.dimension,
    统计口径: binding.caliber,
    时间窗口: binding.timeWindow,
    绑定版本: binding.version,
  }
}

export function createDraft(sessionId: string, context: BindingContext): BindingDraft {
  const draft: BindingDraft = {
    sessionId,
    entryId: context.binding.id,
    values: snapshotValues(context.binding),
    selectedMeasureRef: context.measure?.code ?? context.binding.measureRef ?? '',
    selectedMeasureName: context.measure?.name ?? '',
    selectedMeasureExpression: context.measure?.expression ?? '',
    baseBindingRevision: context.binding.revision,
    baseMeasureRevision: context.measure?.revision ?? null,
    updatedAt: Date.now(),
  }
  saveDraft(draft)
  return draft
}

/** 从服务端最新上下文重新起草，丢弃本会话已有的本地填写。 */
export function resetDraft(sessionId: string, context: BindingContext): BindingDraft {
  const fresh = createDraft(sessionId, context)
  return fresh
}

export function saveDraft(draft: BindingDraft): void {
  draft.updatedAt = Date.now()
  MEMORY.set(draft.sessionId, { ...draft, values: { ...draft.values } })
  if (canUseSessionStorage()) {
    try {
      window.sessionStorage.setItem(
        `${DRAFT_KEY_PREFIX}${draft.sessionId}`,
        JSON.stringify(draft),
      )
    } catch {
      /* 存储受限时退回内存副本 */
    }
  }
}

export function loadDraft(sessionId: string): BindingDraft | null {
  const inMemory = MEMORY.get(sessionId)
  if (inMemory) return cloneDraft(inMemory)
  if (canUseSessionStorage()) {
    try {
      const raw = window.sessionStorage.getItem(`${DRAFT_KEY_PREFIX}${sessionId}`)
      if (raw) {
        const parsed = JSON.parse(raw) as BindingDraft
        MEMORY.set(sessionId, parsed)
        return cloneDraft(parsed)
      }
    } catch {
      /* 解析失败按无草稿处理 */
    }
  }
  return null
}

export function clearDraft(sessionId: string): void {
  MEMORY.delete(sessionId)
  if (canUseSessionStorage()) {
    try {
      window.sessionStorage.removeItem(`${DRAFT_KEY_PREFIX}${sessionId}`)
    } catch {
      /* ignore */
    }
  }
}

function cloneDraft(draft: BindingDraft): BindingDraft {
  return { ...draft, values: { ...draft.values } }
}

export function applyMeasureSelection(
  sessionId: string,
  row: {
    度量编号?: string
    度量名称?: string
    计算表达式?: string
    revision?: number | string
  },
): BindingDraft | null {
  const draft = loadDraft(sessionId)
  if (!draft) return null
  draft.selectedMeasureRef = String(row.度量编号 ?? '')
  draft.selectedMeasureName = String(row.度量名称 ?? '')
  draft.selectedMeasureExpression = String(row.计算表达式 ?? '')
  draft.baseMeasureRevision = row.revision == null ? null : Number(row.revision)
  saveDraft(draft)
  return draft
}

/**
 * 冲突分型：
 * - 仅绑定被改：所选度量仍可沿用，但须重新取得编辑确认；
 * - 仅度量被改：不能沿用所选度量，无需重新确认（重新选度量即可）；
 * - 两者都被改：既不能沿用度量，也须重新确认。
 *
 * `latestMeasure` 是所选度量在提交前的最新快照；不传时退回到绑定上下文里的
 * 当前引用度量。两条路径都只比对 revision，避免用名称猜变化。
 */
export function classifyConflict(
  draft: BindingDraft,
  context: BindingContext,
  latestMeasure?: MeasureSnapshot | null,
): BindingConflict | null {
  if (!context.editable || context.invalid) {
    return {
      type: 'binding_invalid',
      message: `绑定 ${context.binding.code} 当前为「${context.binding.status}」，已失效，不能直接编辑。`,
      canKeepMeasure: false,
      mustReconfirm: false,
      binding: context.binding,
      measure: context.measure,
    }
  }
  const bindingStale = context.binding.revision !== draft.baseBindingRevision
  const selectedRef = draft.selectedMeasureRef
  const measure = resolveMeasureForSelection(draft, context, latestMeasure)
  let measureStale: boolean
  if (!selectedRef) {
    measureStale = true
  } else if (context.measure?.code === selectedRef) {
    // 选的就是绑定当前引用的度量：直接比版本。
    measureStale = measure == null
      || draft.baseMeasureRevision == null
      || measure.revision !== draft.baseMeasureRevision
  } else if (latestMeasure !== undefined) {
    // 草稿改选了别的度量：只在拿到该度量的最新快照时才能判定。
    measureStale = latestMeasure == null
      || draft.baseMeasureRevision == null
      || latestMeasure.revision !== draft.baseMeasureRevision
  } else {
    // 没有最新快照时不做本地猜测，交给提交时服务端按版本判定。
    measureStale = false
  }

  if (bindingStale && measureStale) {
    return {
      type: 'binding_and_measure_changed',
      message: '所选绑定与引用度量都已被他人修改：度量不能沿用，且须重新取得编辑确认。',
      canKeepMeasure: false,
      mustReconfirm: true,
      binding: context.binding,
      measure,
    }
  }
  if (bindingStale) {
    return {
      type: 'binding_changed',
      message: '这份绑定的指标信息已被他人修改：所选度量仍可沿用，但须重新取得编辑确认。',
      canKeepMeasure: true,
      mustReconfirm: true,
      binding: context.binding,
      measure,
    }
  }
  if (measureStale) {
    if (measure == null) {
      return {
        type: 'measure_missing',
        message: `引用的度量 ${selectedRef || '（空）'} 已不存在：不能沿用，须重新选择度量。`,
        canKeepMeasure: false,
        mustReconfirm: false,
        binding: context.binding,
        measure: null,
      }
    }
    return {
      type: 'measure_changed',
      message: '所选度量已被他人修改：不能沿用当前度量定义，须重新选择度量后提交。',
      canKeepMeasure: false,
      mustReconfirm: false,
      binding: context.binding,
      measure,
    }
  }
  return null
}

/**
 * 找出“当前草稿所选度量”的最新快照：
 * - 若草稿选的正是绑定仍引用的度量，优先用显式拉取的最新快照；
 * - 若草稿改选了别的度量，只能依赖显式拉取，缺省即视为未知（按缺失处理）。
 */
export function resolveMeasureForSelection(
  draft: BindingDraft,
  context: BindingContext,
  latestMeasure?: MeasureSnapshot | null,
): MeasureSnapshot | null {
  const selectedRef = draft.selectedMeasureRef
  if (!selectedRef) return null
  if (context.measure && context.measure.code === selectedRef) {
    return latestMeasure === undefined ? context.measure : latestMeasure
  }
  return latestMeasure === undefined ? null : latestMeasure
}

export function toMeasureSnapshot(row: Record<string, unknown> | null | undefined): MeasureSnapshot | null {
  if (!row) return null
  return {
    id: Number(row.id ?? 0),
    code: String(row['度量编号'] ?? ''),
    name: String(row['度量名称'] ?? ''),
    expression: String(row['计算表达式'] ?? ''),
    status: String(row.status ?? ''),
    revision: Number(row.revision ?? 1),
  }
}

/** 冲突的简短类型说明，供页面与测试共用。 */
export function conflictLabel(type: ConflictType | null | undefined): string {
  switch (type) {
    case 'binding_changed':
      return '绑定信息已被他人修改'
    case 'measure_changed':
      return '所选度量已被他人修改'
    case 'binding_and_measure_changed':
      return '绑定与度量都已被他人修改'
    case 'measure_missing':
      return '所选度量已不存在'
    case 'binding_invalid':
      return '绑定已失效'
    case 'binding_missing':
      return '绑定不存在'
    default:
      return ''
  }
}

export function draftValuesEqual(
  draft: BindingDraft,
  context: BindingContext,
): boolean {
  const server = snapshotValues(context.binding)
  return EDITABLE_FIELDS.every((field) => (draft.values[field] ?? '') === (server[field] ?? ''))
}
