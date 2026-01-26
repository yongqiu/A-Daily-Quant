import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
api.interceptors.request.use(
  config => {
    return config
  },
  error => {
    return Promise.reject(error)
  }
)

// 响应拦截器
api.interceptors.response.use(
  response => response.data,
  error => {
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

export default api

// API 方法
export const apiMethods = {
  // 市场状态
  getStatus: () => api.get('/status'),

  toggleMonitor: () => api.post('/monitor/toggle'),

  refreshRealtime: () => api.post('/realtime/refresh'),

  // 持仓管理
  getHoldings: () => api.get('/holdings'),

  addHolding: (data) => api.post('/holdings', data),

  updateHolding: (symbol, data) => api.put(`/holdings/${symbol}`, data),

  deleteHolding: (symbol) => api.delete(`/holdings/${symbol}`),

  searchStock: (symbol) => api.get(`/stock/search/${symbol}`),

  // K线数据
  getKline: (symbol) => api.get(`/kline/${symbol}`),

  // 分析
  analyzeStock: (symbol) => api.post(`/analyze/${symbol}`),

  calculateStockScore: (symbol) => api.post(`/analyze/${symbol}/score`),

  getStockMetrics: (symbol, date) => {
    const params = date ? `?date=${date}` : ''
    return api.get(`/analyze/${symbol}/metrics${params}`)
  },

  analyzeStockStream: async (symbol, mode = 'multi_agent', onProgress, onComplete, onError) => {
    const response = await fetch(`/api/analyze/${symbol}/report/stream?mode=${mode}`)
    const reader = response.body.getReader()
    const decoder = new TextDecoder()

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        const chunk = decoder.decode(value)
        const lines = chunk.split('\n')

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              if (data.type === 'progress' || data.type === 'step' || data.type === 'token') {
                onProgress?.(data)
              } else if (data.type === 'final_html' || data.type === 'result') {
                onComplete?.(data)
              } else if (data.type === 'complete') {
                onComplete?.(data)
              } else if (data.type === 'error') {
                onError?.(data)
              }
            } catch (e) {
              // Ignore parse errors
            }
          }
        }
      }
    } catch (error) {
      onError?.(error)
    }
  },

  getLatestAnalysis: (symbol, mode = 'multi_agent') =>
    api.get(`/analyze/${symbol}/latest?mode=${mode}`),

  getAnalysisDates: (symbol, mode = 'multi_agent') =>
    api.get(`/analyze/${symbol}/dates?mode=${mode}`),

  getAnalysisHistory: (symbol, date, mode = 'multi_agent') =>
    api.get(`/analyze/${symbol}/history?date=${date}&mode=${mode}`),

  // 策略报告
  getLatestReport: () => api.get('/report/latest'),

  generateReport: (section = 'all') =>
    api.post(`/report/generate?section=${section}`),

  getReportStatus: () => api.get('/report/status'),

  getReportLogs: () => api.get('/report/logs'),

  // 策略管理
  getStrategies: () => api.get('/strategies'),

  getStrategy: (slug) => api.get(`/strategies/${slug}`),

  updateStrategyTemplate: (id, template) =>
    api.post(`/strategies/${id}/template`, { template }),

  updateStrategyParam: (id, key, value) =>
    api.post(`/strategies/${id}/params`, { key, value }),

  // 选股相关
  getDailySelections: (date = null) => {
    const params = date ? `?date=${date}` : ''
    return api.get(`/selections${params}`)
  },

  analyzeCandidate: (symbol) => api.post(`/analyze/candidate/${symbol}`)
}
