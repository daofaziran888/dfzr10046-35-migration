<template>
  <section class="page" :data-module="meta.key">
    <header class="page-head">
      <div>
        <h2>{{ meta.name }}</h2>
        <p class="page-desc">{{ meta.desc }}</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" data-testid="open-create" type="button" @click="openCreate">
          登记{{ meta.entity }}
        </button>
        <button class="btn" data-testid="export" type="button" @click="exportRows">
          导出{{ meta.name }}清单
        </button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <p class="status-legend">
      <span v-for="item in statusSummary" :key="item.status" class="legend-item">
        {{ item.status }}：{{ item.count }}
      </span>
    </p>

    <div v-if="returnContext" class="notice-card return-banner" data-testid="measure-return-banner">
      <strong>正在为绑定 {{ returnContext.entryId }} 选择引用度量</strong>
      <span>在下方任一度量选择「选用为引用度量」，选择后会返回发起编辑的那份绑定。</span>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :data-testid="`filter-${field}`" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" data-testid="query" type="submit">查询</button>
      <button class="btn ghost" data-testid="reset" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in meta.fields" :key="column">{{ column }}</th>
          <th>当前状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :data-testid="`row-${row.id}`" :data-status="String(row.status)">
          <td v-for="column in meta.fields" :key="column">{{ row[column] ?? '—' }}</td>
          <td>{{ row.status }}</td>
          <td class="row-actions">
            <button
              v-for="action in meta.actions"
              :key="action"
              class="link"
              type="button"
              :data-testid="`action-${row.id}-${action}`"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <RouterLink
              v-if="isMetricBind"
              class="link"
              :to="{ name: 'binding_detail', params: { entryId: String(row.id) } }"
              :data-testid="`open-binding-${row.id}`"
            >
              打开绑定
            </RouterLink>
            <button
              v-if="returnContext"
              class="link"
              type="button"
              :data-testid="`select-measure-${row.id}`"
              @click="selectMeasure(row)"
            >
              选用为引用度量
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="meta.fields.length + 2" class="empty-state">
            暂无{{ meta.name }}数据，可先登记{{ meta.entity }}
          </td>
        </tr>
      </tbody>
    </table>

    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate">
        <h3>登记{{ meta.entity }}</h3>
        <label v-for="field in meta.fields" :key="field" class="create-field">
          <span>{{ field }}</span>
          <input v-model="createValues[field]" :data-testid="`create-${field}`" required />
        </label>
        <div class="page-actions">
          <button class="btn" type="button" @click="showCreate = false">取消</button>
          <button class="btn primary" data-testid="submit-create" type="submit" :disabled="creating">
            {{ creating ? '提交中…' : '确认登记' }}
          </button>
        </div>
      </form>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条{{ meta.name }}记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import {
  createEntry,
  downloadEntries,
  getBindingByCode,
  listEntries,
  moduleMeta,
  runAction as applyAction,
} from '@/api/backend-service'
import type { EntryRow } from '@/data/types'

const props = defineProps<{ moduleKey: string }>()
const route = useRoute()
const router = useRouter()
const meta = computed(() => moduleMeta(props.moduleKey))
const isMetricBind = computed(() => meta.value.key === 'metric_bind')
const rows = ref<EntryRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = computed(() => meta.value.fields.slice(0, 3))
const showCreate = ref(false)
const creating = ref(false)
const createValues = ref<Record<string, string>>({})
const returnContext = computed(() => {
  const returnTo = String(route.query.returnTo ?? '')
  if (meta.value.key !== 'measure_catalog' || !returnTo) return null
  return {
    entryId: returnTo,
    session: String(route.query.session ?? ''),
    bindingCode: String(route.query.bindingCode ?? ''),
    bindingName: String(route.query.bindingName ?? ''),
  }
})

function selectMeasure(row: EntryRow) {
  const ctx = returnContext.value
  if (!ctx) return
  // 用 replace 返回发起编辑的绑定：浏览器后退时直接落回那份绑定，
  // 而不是再退回度量目录。
  router.replace({
    name: 'binding_detail',
    params: { entryId: ctx.entryId },
    query: {
      session: ctx.session,
      measureRef: String(row['度量编号'] ?? ''),
      measureId: String(row.id),
      measureName: String(row['度量名称'] ?? ''),
      measureExpression: String(row['计算表达式'] ?? ''),
      measureStatus: String(row.status ?? ''),
      measureRevision: String(row.revision ?? 1),
      from: 'measure_catalog',
    },
  })
}
const stats = computed(() => [
  { label: meta.value.metrics[0], value: total.value },
  { label: meta.value.metrics[1], value: rows.value.filter((row) => row.status === meta.value.statuses[1]).length },
  {
    label: meta.value.metrics[2],
    value: rows.value.filter((row) => row.status === meta.value.statuses[meta.value.statuses.length - 1]).length,
  },
])
const statusSummary = computed(() =>
  meta.value.statuses.map((status) => ({
    status,
    count: rows.value.filter((row) => String(row.status) === status).length,
  })),
)

function resetFilters() {
  filters.value = {}
  void reload()
}

async function exportRows() {
  errorMessage.value = ''
  try {
    await downloadEntries(meta.value.key, filters.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '导出失败'
  }
}

function openCreate() {
  createValues.value = Object.fromEntries(meta.value.fields.map((field) => [field, '']))
  errorMessage.value = ''
  showCreate.value = true
}

async function submitCreate() {
  creating.value = true
  errorMessage.value = ''
  try {
    const result = await createEntry(meta.value.key, createValues.value)
    if (!result.ok) throw new Error(result.message)
    showCreate.value = false
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '登记失败'
  } finally {
    creating.value = false
  }
}

async function runAction(action: string, row: EntryRow) {
  errorMessage.value = ''
  try {
    const result = await applyAction(meta.value.key, Number(row.id), action)
    if (!result.ok) throw new Error(result.message)
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  try {
    const payload = await listEntries(meta.value.key, filters.value)
    rows.value = payload.items
    total.value = payload.total
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '业务列表读取失败'
  }
}

/**
 * 老书签可能带 `?bind=BND-002` 或 `?keyword=BND-002` 直接指向某份绑定。
 * 列表本身仍可正常使用；若能解析出唯一绑定，再跳到对应的新路由。
 */
async function resolveLegacyBindingLink() {
  if (!isMetricBind.value) {
    await reload()
    return
  }
  const legacyCode = String(route.query.bind ?? route.query.bindingCode ?? '').trim()
  if (legacyCode) {
    errorMessage.value = ''
    try {
      const row = await getBindingByCode(legacyCode)
      const id = Number(row.id ?? 0)
      if (id) {
        await router.replace({ name: 'binding_detail', params: { entryId: String(id) } })
        return
      }
    } catch (error) {
      errorMessage.value = error instanceof Error ? error.message : '绑定编号解析失败'
      return
    }
  }
  // 只带绑定编号的模糊检索：命中唯一一条时同样直接打开，命中多条时留在列表让值班挑选。
  const keyword = String(route.query.keyword ?? '').trim()
  if (keyword) {
    filters.value = { ...filters.value, 绑定编号: keyword }
    await reload()
    if (rows.value.length === 1) {
      const only = rows.value[0]
      await router.replace({ name: 'binding_detail', params: { entryId: String(only.id) } })
    }
    return
  }
  await reload()
}

const ready = ref(false)
onMounted(async () => {
  await resolveLegacyBindingLink()
  ready.value = true
})

// 模块切换时重新载入（同一组件实例会被 vue-router 复用）。
watch(
  () => props.moduleKey,
  () => {
    filters.value = {}
    showCreate.value = false
    void resolveLegacyBindingLink()
  },
)

watch(
  () => route.query,
  async () => {
    if (!ready.value) return
    await resolveLegacyBindingLink()
  },
)

</script>
