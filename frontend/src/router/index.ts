import { createRouter, createWebHistory } from 'vue-router'

import Overview from '@/views/Overview.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'
import BindingDetailView from '@/views/BindingDetailView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    // 指标绑定的存量入口 /metric_bind 继续指向列表工作台；
    // 新链接 /metric_bind/<绑定id> 可直接打开指定绑定。
    {
      path: '/metric_bind/:entryId(\\d+)',
      name: 'binding_detail',
      component: BindingDetailView,
      props: true,
    },
    { path: '/:moduleKey', name: 'module', component: WorkbenchView, props: true },
    // 旧链接后面多带了一段（如 /metric_bind/BND-001）时，仍回到指标绑定列表。
    { path: '/metric_bind/:legacyPath(.*)', redirect: '/metric_bind' },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

const SESSION_STATE_KEY = 'metricBindSession'
const SESSION_ENTRY_KEY = 'metricBindSessionEntry'

/**
 * 前进/后退会换回旧的 history entry。如果该 entry 在 state 里记过编辑会话，
 * 就把它补回地址栏，让后退也能落到发起编辑的那份绑定草稿上。
 */
router.beforeEach((to) => {
  if (to.name !== 'binding_detail') return true
  if (typeof to.query.session === 'string' && to.query.session) return true
  if (typeof window === 'undefined') return true
  const state = (window.history.state ?? {}) as Record<string, unknown>
  const session = state[SESSION_STATE_KEY]
  const entryId = Number(to.params.entryId ?? 0)
  if (typeof session !== 'string' || !session) return true
  // state 里的会话属于另一份绑定时不带过去，避免同编号以外的对象串草稿。
  if (state[SESSION_ENTRY_KEY] != null && Number(state[SESSION_ENTRY_KEY]) !== entryId) {
    return true
  }
  return { path: to.path, query: { ...to.query, session }, replace: true }
})

export default router
