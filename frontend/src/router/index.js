import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: () => import('@/views/DashboardView.vue'),
      meta: { title: 'A股量化策略' }
    },
    {
      path: '/screener',
      name: 'screener',
      component: () => import('@/views/ScreenerView.vue'),
      meta: { title: '选股列表' }
    },
    {
      path: '/strategies',
      name: 'strategies',
      component: () => import('@/views/StrategiesView.vue'),
      meta: { title: '策略配置中心' }
    }
  ]
})

// 设置页面标题
router.beforeEach((to, _from, next) => {
  document.title = to.meta.title || 'A股量化策略监控平台'
  next()
})

export default router
