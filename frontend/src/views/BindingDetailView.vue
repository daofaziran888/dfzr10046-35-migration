<template>
  <section class="page binding-page" data-testid="binding-page" :data-entry-id="entryId">
    <header class="page-head">
      <div>
        <h2>指标绑定 · 绑定工作台</h2>
        <p class="page-desc">
          绑定编号 {{ bindingCode || `#${entryId}` }}
          <span v-if="context"> · 当前状态 {{ context.binding.status }}</span>
        </p>
      </div>
      <div class="page-actions">
        <button class="btn" data-testid="back-to-list" type="button" @click="goList">回到绑定列表</button>
        <button
          v-if="context && !context.invalid"
          class="btn"
          data-testid="open-measure-catalog"
          type="button"
          @click="goMeasureCatalog"
        >
          前往度量目录选度量
        </button>
      </div>
    </header>

    <p v-if="loading" class="status-legend" data-testid="binding-loading">正在载入绑定…</p>

    <template v-else-if="notFound">
      <article class="notice-card error-card" data-testid="binding-not-found">
        <h3>绑定不存在或已归档</h3>
        <p>{{ notFoundMessage }}</p>
        <p class="notice-meta" data-testid="missing-ownership">
          对象归属：指标绑定（metric_bind） / 绑定 #{{ entryId }}
        </p>
        <div class="page-actions">
          <button class="btn" data-testid="open-list-from-missing" type="button" @click="goList">
            回到指标绑定列表
          </button>
        </div>
      </article>
    </template>

    <template v-else-if="context">
      <article class="notice-card" data-testid="binding-ownership" :data-invalid="String(context.invalid)">
        <h3>对象归属</h3>
        <dl class="kv-grid">
          <div><dt>所属模块</dt><dd>{{ context.ownership.moduleName }}（{{ context.ownership.moduleKey }}）</dd></div>
          <div><dt>业务对象</dt><dd>{{ context.ownership.entity }}</dd></div>
          <div><dt>绑定编号</dt><dd data-testid="ownership-code">{{ context.ownership.bindingCode }}</dd></div>
          <div><dt>指标名称</dt><dd data-testid="ownership-name">{{ context.ownership.metricName }}</dd></div>
          <div><dt>绑定维度</dt><dd>{{ context.ownership.dimension || '—' }}</dd></div>
          <div><dt>引用度量</dt><dd>{{ context.ownership.measureRef || '—' }}</dd></div>
        </dl>
      </article>

      <article v-if="context.invalid" class="notice-card invalid-card" data-testid="binding-invalid">
        <h3>绑定已失效</h3>
        <p>
          该绑定当前状态为「{{ context.binding.status }}」，历史读数仍按原绑定口径保留，
          但不能在此直接编辑。可执行以下后续动作：
        </p>
        <div class="page-actions">
          <button
            v-for="item in context.followUps"
            :key="item.action"
            class="btn"
            :class="{ primary: item.action === 'duplicate' }"
            :data-testid="`followup-${item.action}`"
            type="button"
            :disabled="busy"
            @click="runFollowUp(item.action)"
          >
            {{ item.label }}
          </button>
        </div>
        <p v-if="followUpMessage" class="followup-message" data-testid="followup-message">{{ followUpMessage }}</p>
        <p v-if="errorMessage" class="error-text" data-testid="binding-error">{{ errorMessage }}</p>
      </article>

      <template v-else>
        <article class="editor-card" data-testid="binding-editor">
          <h3>编辑绑定</h3>
          <p class="notice-meta" data-testid="session-indicator">
            编辑会话 {{ shortSession }} · 基线绑定版本 rev {{ draft?.baseBindingRevision ?? '—' }}
          </p>

          <label v-for="field in EDITABLE_FIELDS" :key="field" class="create-field">
            <span>{{ field }}</span>
            <input
              v-model="draftValues[field]"
              :data-testid="`edit-${field}`"
              @input="persistDraft"
            />
          </label>

          <div class="measure-picker-row">
            <div>
              <span class="picker-label">引用度量</span>
              <strong data-testid="selected-measure">
                {{ draft?.selectedMeasureRef || '未选择' }}
                <template v-if="draft?.selectedMeasureName"> · {{ draft.selectedMeasureName }}</template>
              </strong>
              <p v-if="draft?.selectedMeasureExpression" class="notice-meta">
                表达式 {{ draft.selectedMeasureExpression }} · 度量版本 rev {{ draft.baseMeasureRevision ?? '—' }}
              </p>
            </div>
            <button class="btn" data-testid="pick-measure" type="button" @click="goMeasureCatalog">
              从度量目录选择
            </button>
          </div>

          <div class="page-actions">
            <button class="btn ghost" data-testid="discard-draft" type="button" :disabled="busy" @click="discardDraft">
              放弃改动并重新载入
            </button>
            <button class="btn primary" data-testid="submit-binding" type="button" :disabled="busy" @click="submit">
              {{ busy ? '提交中…' : '提交绑定修改' }}
            </button>
          </div>
        </article>

        <article
          v-if="conflict"
          class="notice-card conflict-card"
          data-testid="binding-conflict"
          :data-conflict-type="conflict.type"
        >
          <h3>{{ conflictLabel(conflict.type) }}</h3>
          <p data-testid="conflict-message">{{ conflict.message }}</p>
          <ul class="conflict-facts">
            <li data-testid="conflict-can-keep">
              能否沿用当前所选度量：{{ conflict.canKeepMeasure ? '可以沿用' : '不能沿用，需重新选择' }}
            </li>
            <li data-testid="conflict-must-reconfirm">
              是否须重新取得编辑确认：{{ conflict.mustReconfirm ? '必须重新确认' : '无需重新确认' }}
            </li>
            <li v-if="conflict.binding">
              最新绑定：{{ conflict.binding.name }} · 版本 rev {{ conflict.binding.revision }}
            </li>
            <li v-if="conflict.measure">
              最新度量：{{ conflict.measure.name }} · rev {{ conflict.measure.revision }}
            </li>
          </ul>
          <div class="page-actions">
            <button
              v-if="conflict.canKeepMeasure"
              class="btn primary"
              data-testid="conflict-keep-measure"
              type="button"
              :disabled="busy"
              @click="keepMeasureAndReconfirm"
            >
              沿用所选度量并重新确认
            </button>
            <button
              v-if="!conflict.canKeepMeasure"
              class="btn primary"
              data-testid="conflict-repick-measure"
              type="button"
              @click="goMeasureCatalog"
            >
              重新选择度量
            </button>
            <button
              class="btn"
              data-testid="conflict-reload"
              type="button"
              :disabled="busy"
              @click="reloadContext(true)"
            >
              以最新版本重新载入
            </button>
          </div>
          <p v-if="reconfirmRequired" class="notice-meta" data-testid="reconfirm-hint">
            已沿用所选度量并把基线对齐到最新绑定版本；请核对最新指标名称后再次提交，提交时才真正写入。
          </p>
        </article>
      </template>

      <p v-if="submitMessage" class="submit-message" data-testid="submit-message">{{ submitMessage }}</p>
      <p v-if="errorMessage && !context.invalid" class="error-text" data-testid="binding-error">{{ errorMessage }}</p>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  applyBindingMeasure,
  duplicateBinding,
  getBindingContext,
  restoreBinding,
} from '@/api/backend-service'
import {
  EDITABLE_FIELDS,
  type BindingConflict,
  type BindingContext,
  type BindingDraft,
  type MeasureSnapshot,
  applyMeasureSelection,
  classifyConflict,
  conflictLabel,
  createDraft,
  loadDraft,
  rememberSession,
  resetDraft,
  resolveSessionId,
  saveDraft,
  sessionIdForEntry,
  sessionIdFromState,
} from '@/domain/metricBind'

const props = defineProps<{ entryId: string }>()
const route = useRoute()
const router = useRouter()

const entryId = computed(() => Number(props.entryId))
const bindingCode = ref('')
const context = ref<BindingContext | null>(null)
const draft = ref<BindingDraft | null>(null)
const draftValues = ref<Record<string, string>>({})
const loading = ref(false)
const busy = ref(false)
const notFound = ref(false)
const notFoundMessage = ref('')
const conflict = ref<BindingConflict | null>(null)
const submitMessage = ref('')
const errorMessage = ref('')
const followUpMessage = ref('')
const reconfirmRequired = ref(false)
const sessionId = ref('')

const shortSession = computed(() => (sessionId.value ? sessionId.value.slice(0, 8) : '—'))

function measureFromQuery(): MeasureSnapshot | null {
  const code = String(route.query.measureRef ?? route.query.measure ?? '')
  if (!code) return null
  return {
    id: Number(route.query.measureId ?? 0),
    code,
    name: String(route.query.measureName ?? ''),
    expression: String(route.query.measureExpression ?? ''),
    status: String(route.query.measureStatus ?? ''),
    revision: Number(route.query.measureRevision ?? 1),
  }
}

/**
 * 会话标识只放在地址栏：vue-router 每次导航都会重写 history.state，
 * 把会话挂在 state 上刷新后就丢了；放进 query 才能经受后退、刷新与跨模块往返。
 */
function adoptSession(): string {
  const fromQuery = typeof route.query.session === 'string' ? route.query.session : null
  const entryScoped = sessionIdForEntry(entryId.value)
  const resolved = fromQuery || entryScoped || resolveSessionId()
  sessionId.value = resolved
  rememberSession(resolved, entryId.value)
  if (!fromQuery) {
    void router.replace({
      path: route.path,
      query: { ...route.query, session: resolved },
    })
  }
  return resolved
}

function persistDraft() {
  if (!draft.value) return
  draft.value.values = { ...draftValues.value }
  saveDraft(draft.value)
}

async function reloadContext(preserveDraft = true) {
  loading.value = true
  errorMessage.value = ''
  try {
    const payload = (await getBindingContext(entryId.value)) as unknown as BindingContext
    context.value = payload
    bindingCode.value = payload.binding.code
    notFound.value = false
    const stored = loadDraft(sessionId.value)
    if (!preserveDraft || !stored || stored.entryId !== entryId.value) {
      draft.value = createDraft(sessionId.value, payload)
    } else {
      draft.value = stored
    }
    draftValues.value = { ...draft.value.values }
    // 刷新 / 后退回来后也要重新判定冲突，而不是只在提交时才提示。
    conflict.value = classifyConflict(draft.value, payload)
  } catch (error) {
    context.value = null
    draft.value = null
    conflict.value = null
    notFound.value = true
    notFoundMessage.value = error instanceof Error ? error.message : '绑定读取失败'
  } finally {
    loading.value = false
  }
}

/** 从度量目录返回（或刷新）时把选中的度量并入本会话草稿。 */
function absorbIncomingMeasure() {
  const incoming = measureFromQuery()
  if (!incoming || !draft.value) return
  const from = String(route.query.from ?? '')
  if (from && from !== 'measure_catalog') return
  applyMeasureSelection(sessionId.value, {
    度量编号: incoming.code,
    度量名称: incoming.name,
    计算表达式: incoming.expression,
    revision: incoming.revision,
  })
  const updated = loadDraft(sessionId.value)
  if (updated) {
    draft.value = updated
    draftValues.value = { ...updated.values }
  }
  // 选度量参数是一次性的：并入草稿后从地址栏抹掉，避免后退/刷新重复套用。
  void stripMeasureQuery()
  if (context.value && draft.value) {
    // 刚选中的度量若已不是最新版本，这里就要提示冲突；传入刚带回来的快照。
    conflict.value = classifyConflict(draft.value, context.value, incoming)
    if (conflict.value) reconfirmRequired.value = false
  }
}

async function stripMeasureQuery() {
  const query: Record<string, string> = {}
  for (const [key, value] of Object.entries(route.query)) {
    if (typeof value === 'string') query[key] = value
  }
  for (const key of [
    'measureRef', 'measure', 'measureId', 'measureName',
    'measureExpression', 'measureStatus', 'measureRevision', 'from',
  ]) {
    delete query[key]
  }
  if (sessionId.value) query.session = sessionId.value
  await router.replace({ path: route.path, query })
}

function goMeasureCatalog() {
  if (!draft.value) return
  persistDraft()
  void router.push({
    name: 'module',
    params: { moduleKey: 'measure_catalog' },
    query: {
      returnTo: String(entryId.value),
      session: sessionId.value,
      bindingCode: bindingCode.value,
      bindingName: draft.value.values['指标名称'] ?? '',
    },
  })
}

function goList() {
  void router.push({ name: 'module', params: { moduleKey: 'metric_bind' } })
}

function discardDraft() {
  if (!context.value) return
  conflict.value = null
  reconfirmRequired.value = false
  draft.value = resetDraft(sessionId.value, context.value)
  draftValues.value = { ...draft.value.values }
  submitMessage.value = '已放弃本地改动，按服务端最新版本重新起草'
}

async function submit() {
  if (!draft.value || !context.value) return
  busy.value = true
  errorMessage.value = ''
  submitMessage.value = ''
  persistDraft()
  try {
    const result = await applyBindingMeasure(entryId.value, {
      measureRef: draft.value.selectedMeasureRef,
      values: { ...draft.value.values },
      expectedBindingRevision: draft.value.baseBindingRevision,
      expectedMeasureRevision: draft.value.baseMeasureRevision,
    })
    if (!result.ok && result.conflict) {
      conflict.value = result.conflict as unknown as BindingConflict
      reconfirmRequired.value = false
      return
    }
    if (!result.ok) {
      errorMessage.value = result.message
      return
    }
    conflict.value = null
    reconfirmRequired.value = false
    submitMessage.value = result.message
    await reloadContext(false)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '提交失败'
  } finally {
    busy.value = false
  }
}

/**
 * 仅绑定被改的冲突：所选度量仍可沿用。用户确认后把基线对齐到最新服务端版本，
 * 再提交一次才算“重新取得编辑确认”。
 */
async function keepMeasureAndReconfirm() {
  if (!draft.value || !conflict.value) return
  busy.value = true
  submitMessage.value = ''
  errorMessage.value = ''
  try {
    const fresh = (await getBindingContext(entryId.value)) as unknown as BindingContext
    context.value = fresh
    bindingCode.value = fresh.binding.code
    // 指标名称等字段仍以本地填写为准，只把版本基线对齐服务端。
    draft.value.baseBindingRevision = fresh.binding.revision
    draft.value.baseMeasureRevision = fresh.measure?.revision ?? draft.value.baseMeasureRevision
    saveDraft(draft.value)
    conflict.value = null
    reconfirmRequired.value = true
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '重新载入失败'
  } finally {
    busy.value = false
  }
}

async function runFollowUp(action: string) {
  busy.value = true
  errorMessage.value = ''
  followUpMessage.value = ''
  try {
    if (action === 'duplicate') {
      const result = await duplicateBinding(entryId.value)
      if (!result.ok || !result.entry) throw new Error(result.message)
      followUpMessage.value = result.message
      await router.push({ name: 'binding_detail', params: { entryId: String(result.entry.id) } })
      return
    }
    if (action === 'restore') {
      const result = await restoreBinding(entryId.value)
      if (!result.ok) throw new Error(result.message)
      followUpMessage.value = result.message
      await reloadContext(false)
      return
    }
    if (action === 'open_measure') {
      const ref = context.value?.ownership.measureRef
      if (ref) {
        await router.push({
          name: 'module',
          params: { moduleKey: 'measure_catalog' },
          query: { keyword: ref },
        })
      }
      return
    }
    if (action === 'open_list') {
      goList()
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '后续动作执行失败'
  } finally {
    busy.value = false
  }
}

let loadedEntryId: number | null = null

async function boot() {
  adoptSession()
  await reloadContext(true)
  loadedEntryId = entryId.value
  absorbIncomingMeasure()
}

onMounted(boot)

watch(
  () => props.entryId,
  async () => {
    if (entryId.value === loadedEntryId) return
    // 同一个组件实例被复用到另一份绑定：开新会话，避免把上一份的填写带过去。
    sessionId.value = ''
    conflict.value = null
    submitMessage.value = ''
    adoptSession()
    await reloadContext(true)
    loadedEntryId = entryId.value
    absorbIncomingMeasure()
  },
)

watch(
  () => [route.query.measureRef, route.query.measure, route.query.session],
  async () => {
    if (String(route.params.entryId ?? '') !== String(entryId.value)) return
    const querySession = typeof route.query.session === 'string' ? route.query.session : ''
    if (querySession && querySession !== sessionId.value) {
      sessionId.value = querySession
      rememberSession(querySession, entryId.value)
      await reloadContext(true)
      absorbIncomingMeasure()
      return
    }
    // stripMeasureQuery 会改写 query；只有确实带着度量参数时才并入，避免自触发循环。
    if (route.query.measureRef || route.query.measure) {
      absorbIncomingMeasure()
    }
  },
)
</script>
