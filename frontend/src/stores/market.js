import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiMethods } from '@/utils/api'

export const useMarketStore = defineStore('market', () => {
  // 状态
  const marketState = ref({
    index: { name: '上证指数', price: 0, change_pct: 0 },
    stocks: [],
    last_update: '--:--:--',
    is_monitoring: false,
    config: { update_interval: 10 }
  })

  const loading = ref(false)
  const refreshing = ref(false)

  // 计算属性
  const stockCount = computed(() => marketState.value.stocks.length)
  const isMonitoring = computed(() => marketState.value.is_monitoring)

  // 方法
  const fetchStatus = async () => {
    try {
      const data = await apiMethods.getStatus()
      marketState.value = data
      return data
    } catch (error) {
      console.error('获取市场状态失败:', error)
      throw error
    }
  }

  const toggleMonitor = async () => {
    try {
      const data = await apiMethods.toggleMonitor()
      marketState.value.is_monitoring = data.is_monitoring
      return data
    } catch (error) {
      console.error('切换监控状态失败:', error)
      throw error
    }
  }

  const refreshRealtime = async () => {
    refreshing.value = true
    try {
      const data = await apiMethods.refreshRealtime()
      if (data.status === 'success') {
        marketState.value.stocks = data.stocks
        marketState.value.index = data.index
        marketState.value.last_update = data.last_update
      }
      return data
    } catch (error) {
      console.error('刷新实时数据失败:', error)
      throw error
    } finally {
      refreshing.value = false
    }
  }

  const getStockBySymbol = (symbol) => {
    return marketState.value.stocks.find(s => s.symbol === symbol)
  }

  return {
    marketState,
    loading,
    refreshing,
    stockCount,
    isMonitoring,
    fetchStatus,
    toggleMonitor,
    refreshRealtime,
    getStockBySymbol
  }
})
