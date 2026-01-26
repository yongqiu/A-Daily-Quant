<template>
  <div class="grid grid-cols-12 h-screen overflow-hidden bg-bg-pattern-grid">
    
    <!-- Left Column: Selection List (Width: 25%) -->
    <div class="flex-col h-full border-r border-border-subtle bg-bg-elevated/50 backdrop-blur-sm transition-all duration-300"
         :class="selectedStockSymbol ? 'hidden lg:flex lg:col-span-3 xl:col-span-3' : 'flex col-span-12 lg:col-span-3 xl:col-span-3'">
        <!-- Header -->
        <div class="px-4 py-3 border-b border-border-subtle bg-bg-elevated/80 flex-shrink-0">
            <div class="flex items-center justify-between mb-2">
                <div class="flex items-center gap-2">
                    <div class="w-2 h-2 rounded-full bg-cyan animate-pulse"></div>
                    <h2 class="text-xs font-semibold uppercase tracking-wider text-text-tertiary">每日选股</h2>
                </div>
                <div class="flex items-center gap-1">
                     <button @click="runSelectionTask" :disabled="runningSelection" class="btn-icon text-cyan hover:text-cyan-light hover:bg-cyan/10" :title="runningSelection ? '选股执行中...' : '立即运行选股'">
                        <PlayIcon v-if="!runningSelection" class="w-4 h-4" />
                        <span v-else class="w-3.5 h-3.5 rounded-full border-2 border-cyan/30 border-t-cyan animate-spin"></span>
                    </button>
                    <button @click="loadSelections" :disabled="loading" class="btn-icon" title="刷新列表">
                        <ArrowPathIcon class="w-4 h-4" :class="{ 'animate-spin': loading }" />
                    </button>
                </div>
            </div>
            
            <!-- Date Filter -->
            <div class="relative w-full">
                <select v-model="selectedDate" @change="handleDateChange"
                    class="w-full appearance-none bg-bg-card border border-border-subtle text-xs text-text-primary rounded pl-3 pr-8 py-2 focus:border-primary outline-none cursor-pointer transition-all">
                    <option value="">最新 ({{ availableDates[0] || 'Today' }})</option>
                    <option v-for="date in availableDates" :key="date" :value="date">{{ date }}</option>
                </select>
                <ChevronDownIcon class="w-3.5 h-3.5 text-text-tertiary absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            </div>
        </div>
        
        <!-- Running Notification -->
        <div v-if="runningSelection" class="px-4 py-2 bg-primary/10 border-b border-primary/20 text-[10px] text-cyan flex justify-between items-center">
            <span class="animate-pulse">正在全市场扫描选股中...</span>
            <span class="font-mono">{{ selectionTime }}s</span>
        </div>

        <!-- List Content -->
        <div class=" flex-auto h-10 overflow-y-auto scrollbar-thin min-h-0 relative pb-4">
             <!-- Loading State -->
             <div v-if="loading" class="flex flex-col items-center justify-center py-10">
                <div class="w-6 h-6 border-2 border-primary/30 border-t-primary rounded-full animate-spin mb-2"></div>
                <span class="text-xs text-text-tertiary">加载中...</span>
             </div>

             <!-- Empty State -->
             <div v-else-if="selections.length === 0" class="p-8 text-center flex flex-col items-center">
                 <div class="w-12 h-12 rounded-full bg-bg-elevated flex items-center justify-center mb-3">
                   <FunnelIcon class="w-6 h-6 text-text-tertiary" />
                 </div>
                 <p class="text-sm text-text-tertiary">该日期暂无选股</p>
             </div>

             <!-- List Items -->
             <div v-else class="flex flex-col">
                <div v-for="stock in selections" :key="stock.symbol"
                     @click="selectStock(stock)"
                     class="group border-b border-border-subtle cursor-pointer transition-all duration-200 px-4 py-3 relative hover:bg-white/5"
                     :class="selectedStockSymbol === stock.symbol ? 'bg-primary/5 border-l-2 border-l-primary pl-[14px]' : ''">
                     
                     <div class="flex justify-between items-center mb-1.5">
                        <div class="flex items-center gap-2">
                           <span class="font-mono font-bold text-base text-text-primary">{{ stock.symbol }}</span>
                           <!-- Tags -->
                           <span class="px-1 py-[1px] rounded text-[10px] border font-medium"
                               :class="stock.asset_type === 'etf' ? 'bg-purple-500/20 text-purple-400 border-purple-500/30' : 'bg-blue-500/20 text-blue-400 border-blue-500/30'">
                            {{ stock.asset_type === 'etf' ? 'ETF' : '个股' }}
                           </span>
                           <!-- Created At Time -->
                           <span v-if="stock.created_at" class="text-[10px] text-text-tertiary font-mono ml-auto mr-2">
                             {{ stock.created_at.substring(0, 5) }}
                           </span>
                        </div>
                        <span class="digit-display-md text-text-primary">
                             {{ stock.close_price ? stock.close_price.toFixed(2) : '----' }}
                        </span>
                     </div>

                     <div class="flex justify-between items-center mb-1">
                        <span class="text-sm text-text-secondary truncate max-w-[120px]">{{ stock.name }}</span>
                        <!-- Score Badge -->
                        <span v-if="stock.composite_score" class="font-mono font-bold text-sm" :class="getScoreColor(stock.composite_score)">
                            {{ stock.composite_score }}分
                        </span>
                     </div>

                     <!-- Active Indicator -->
                     <div v-if="selectedStockSymbol === stock.symbol" class="absolute left-0 top-0 bottom-0 w-0.5 bg-gradient-to-b from-primary via-cyan to-primary opacity-50"></div>
                </div>
             </div>
        </div>
    </div>

    <!-- Right Column: Details Area (Width: 75%) -->
    <div class="flex-col h-full bg-bg/50 backdrop-blur-sm relative overflow-hidden"
         :class="selectedStockSymbol ? 'flex col-span-12 lg:col-span-9 xl:col-span-9' : 'hidden lg:flex lg:col-span-9 xl:col-span-9'">
        
        <!-- Empty State (No Selection) -->
        <div v-if="!selectedStockSymbol" class="flex-1 flex flex-col items-center justify-center text-text-tertiary opacity-60">
             <div class="w-16 h-16 rounded-full bg-bg-elevated flex items-center justify-center mb-4 border border-border-subtle">
                <ArrowRightIcon class="w-8 h-8 text-text-tertiary" />
             </div>
             <p class="text-base font-medium">请从左侧选择一只股票查看详情</p>
        </div>

        <!-- Detail Content -->
        <div v-else class="flex flex-col h-full overflow-hidden">
             <!-- Toolbar / Header -->
             <div class="h-12 flex-shrink-0 border-b border-border-subtle flex items-center justify-between px-4 bg-bg-elevated/80 backdrop-blur-sm">
                 <div class="flex items-center gap-3">
                    <span class="font-bold text-text-primary text-base">{{ selectedStock?.name }}</span>
                    <span class="text-xs font-mono text-text-tertiary px-2 py-0.5 rounded bg-bg-elevated border border-border-subtle">{{ selectedStockSymbol }}</span>
                 </div>
                 
                 <div class="flex gap-2">
                     <button @click="showKlineChart = !showKlineChart"
                             class="px-3 py-1.5 text-xs font-medium rounded transition-all duration-200 flex items-center gap-1.5"
                             :class="showKlineChart ? 'bg-primary/20 text-primary border border-primary/30' : 'bg-bg-elevated text-text-tertiary border border-border-subtle hover:text-text-secondary'">
                        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
                        </svg>
                        {{ showKlineChart ? '关闭K线' : 'K线图' }}
                     </button>
                     <button @click="addToHoldings(selectedStock)" class="btn-primary flex items-center gap-1.5 text-xs py-1.5 px-3">
                        <PlusIcon class="w-3.5 h-3.5" />
                        加入自选
                     </button>
                      <button @click="handleRefreshDetail" class="btn-icon" title="刷新详情">
                        <ArrowPathIcon class="w-4 h-4" />
                     </button>
                     <button @click="closeDetail" class="btn-icon text-text-tertiary hover:text-text-primary ml-1" title="关闭详情">
                         <XMarkIcon class="w-5 h-5" />
                     </button>
                 </div>
             </div>

             <!-- Kline Chart Area -->
             <div v-if="showKlineChart && selectedStockSymbol" class="flex-1 relative bg-bg-card/30">
                <div ref="chartContainer" class="absolute inset-0 w-full h-full"></div>
                <div class="absolute inset-0 pointer-events-none bg-grid opacity-30"></div>

                <!-- Timeframes -->
                <div class="absolute top-3 left-4 flex gap-1">
                   <button class="px-2 py-1 text-xs font-medium rounded bg-primary/20 text-primary border border-primary/30" title="日线">日</button>
                   <button class="px-2 py-1 text-xs font-medium rounded text-text-tertiary hover:text-text-secondary hover:bg-white/5 transition-colors" title="周线">周</button>
                   <button class="px-2 py-1 text-xs font-medium rounded text-text-tertiary hover:text-text-secondary hover:bg-white/5 transition-colors" title="月线">月</button>
                </div>

                <!-- Technical Indicators Panel -->
                <div class="absolute bottom-0 left-0 right-0 h-32 border-t border-border-subtle bg-bg-elevated/80 backdrop-blur-sm p-3">
                   <h3 class="text-xs font-semibold uppercase tracking-wider text-text-tertiary mb-2 flex items-center gap-2">
                     <span class="w-1.5 h-1.5 rounded-full bg-cyan"></span>
                     技术指标
                   </h3>
                   <div class="grid grid-cols-3 gap-2">
                       <div class="indicator-card p-2">
                         <span class="text-[9px] text-text-tertiary uppercase tracking-wide">MA20 趋势</span>
                         <span class="text-xs font-bold text-text-primary mt-0.5 block">{{ selectedStock?.ma20_signal || '---' }}</span>
                       </div>
                       <div class="indicator-card p-2">
                         <span class="text-[9px] text-text-tertiary uppercase tracking-wide">RSI (14)</span>
                         <span class="text-xs font-bold text-text-primary mt-0.5 block">--</span>
                       </div>
                       <div class="indicator-card p-2">
                         <span class="text-[9px] text-text-tertiary uppercase tracking-wide">量比</span>
                         <span class="text-xs font-bold font-mono text-text-primary mt-0.5 block">--</span>
                       </div>
                   </div>
                </div>
             </div>

             <!-- Content Scrollable Area -->
             <div v-else class="flex-1 overflow-y-auto scrollbar-thin bg-bg/30 flex flex-col">
                
                <!-- 1. Score Card Section -->
                <div class="flex-shrink-0 px-4 pt-4 pb-2">
                    <StockScoreCard
                        v-if="scoreResult"
                        :metrics="scoreResult"
                        :loading="calculatingScore"
                        :default-expanded="true"
                        @refresh="runScoreCalculation"
                    />
                     <!-- Loading or Empty Score State -->
                     <div v-else-if="calculatingScore" class="dashboard-card p-6 flex items-center justify-center">
                        <div class="w-5 h-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin mr-2"></div>
                        <span class="text-sm text-text-tertiary">正在加载评分数据...</span>
                     </div>
                     <div v-else class="dashboard-card p-6 text-center text-text-tertiary text-sm border-dashed border border-border-subtle">
                        暂无详细评分数据，请尝试刷新
                        <button @click="runScoreCalculation" class="ml-2 text-primary hover:underline">重新计算</button>
                     </div>
                </div>

                <!-- 2. Analysis Content (Single Mode for Screener) -->
               <div class="flex-1 p-4 min-h-0 overflow-hidden">
                   <div class="prose-container h-full my-0 flex flex-col">
                        <!-- Action Header -->
                        <div class="flex-shrink-0 mb-4 flex justify-between items-center border-b border-border-subtle pb-3">
                           <h3 class="text-sm font-bold text-text-primary m-0 flex items-center gap-2">
                               <span class="w-1.5 h-4 bg-primary rounded-full"></span>
                               AI 机会诊断报告
                           </h3>
                           
                           <button @click="runAIAnalysis" :disabled="analyzing || loadingAnalysis"
                                   class="btn-primary flex items-center gap-2 text-xs py-1.5 px-3 shadow-md transition-all duration-200">
                               <SparklesIcon v-if="!analyzing && !loadingAnalysis" class="w-3.5 h-3.5 group-hover:animate-pulse" />
                               <span v-else class="w-3.5 h-3.5 rounded-full border-2 border-primary/30 border-t-primary animate-spin"></span>
                               {{ analyzing ? '正在生成分析...' : (loadingAnalysis ? '加载中...' : '生成最新分析') }}
                           </button>
                        </div>

                        <div class="flex-1 overflow-y-auto min-h-0 pr-1">
                            <!-- Analysis Progress -->
                         <div v-if="analysisProgress && analyzing" class="mb-4 p-3 rounded bg-bg-elevated/50 border border-border-subtle">
                           <div class="flex items-center gap-2 text-xs font-mono text-primary">
                             <span class="animate-pulse">▶</span>
                             <span class="truncate">{{ analysisProgress }}</span>
                           </div>
                         </div>

                         <!-- Loading State -->
                         <div v-if="loadingAnalysis" class="flex-1 flex flex-col items-center justify-center py-12 text-text-tertiary gap-3">
                           <div class="w-8 h-8 rounded-full border-2 border-border-subtle border-t-primary animate-spin"></div>
                           <span class="text-sm">正在加载分析报告...</span>
                         </div>

                             <!-- Analysis Result -->
                             <div v-else-if="analysisResult" class="flex-1">
                               <div class="prose max-w-none pb-4" v-html="analysisResult"></div>
                             </div>

                             <!-- Empty State -->
                             <div v-else class="flex-1 flex flex-col items-center justify-center text-text-tertiary py-12 opacity-60">
                                 <SparklesIcon class="w-10 h-10 mb-2 opacity-50" />
                                 <span class="text-sm">暂无详细分析内容</span>
                                 <div class="mt-2 text-xs text-text-tertiary max-w-md text-center">
                                     (如果您刚选中该股票，可能需要点击上方按钮生成完整报告)
                                 </div>
                                 <!-- Optional: Fallback to the short ai_analysis field from selection list if available, but usually we want full report here -->
                                <div v-if="selectedStock?.ai_analysis" class="mt-4 p-4 bg-bg-elevated/30 rounded border border-border-subtle text-xs text-text-secondary w-full max-w-lg">
                                     <strong>摘要:</strong> {{ stripHtml(selectedStock.ai_analysis) }}
                                </div>
                             </div>
                         </div>
                    </div>
                </div>

             </div>
        </div>

    </div>

    <!-- Modals if needed (AddHoldingModal logic could be embedded or simple alert) -->
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { apiMethods } from '@/utils/api'
import { useKlineChart } from '@/composables/useKlineChart'
import StockScoreCard from '@/components/StockScoreCard.vue'
import { marked } from 'marked'
import {
  FunnelIcon,
  ArrowPathIcon,
  ChevronDownIcon,
  SparklesIcon,
  PlusIcon,
  ArrowRightIcon,
  PlayIcon,
  XMarkIcon
} from '@heroicons/vue/24/outline'

// State (List)
const selections = ref([])
const loading = ref(false)
const runningSelection = ref(false)
const selectionTime = ref(0)
let timerInterval = null
const selectedDate = ref('')
const availableDates = ref([])
const selectedStockSymbol = ref(null)

// State (Detail)
const scoreResult = ref(null)
const calculatingScore = ref(false)
const activeAnalyzerTab = ref('single_expert') // Default to single_expert (Candidate Mode)
const analyzing = ref(false)
const loadingAnalysis = ref(false)
const analysisProgress = ref('')
const analysisResult = ref('')
const showKlineChart = ref(false)
const chartContainer = ref(null)

// Chart
const { loadKlineData } = useKlineChart(chartContainer, selectedStockSymbol)

// Computed
const selectedStock = computed(() => {
    return selections.value.find(s => s.symbol === selectedStockSymbol.value)
})

// === Actions: List ===
const loadSelections = async () => {
  loading.value = true
  try {
    const data = await apiMethods.getDailySelections(selectedDate.value)
    selections.value = data.selections || []
    if (data.available_dates) availableDates.value = data.available_dates
    // Auto-select first date if empty
    if (!selectedDate.value && availableDates.value.length > 0) {
        // usually the backend returns selections for default date anyway, but visual sync:
        // selectedDate.value = availableDates.value[0] 
    }
  } catch (error) {
    console.error('Failed to load selections:', error)
  } finally {
    loading.value = false
  }
}

const handleDateChange = () => {
    selectedStockSymbol.value = null // Reset selection on date change
    loadSelections()
}

const selectStock = (stock) => {
    if (selectedStockSymbol.value === stock.symbol) return
    selectedStockSymbol.value = stock.symbol
    
    // Reset Data
    scoreResult.value = null
    analysisResult.value = ''
    
    // Fetch Detail Data
    loadDetailData(stock.symbol)
}

const closeDetail = () => {
    selectedStockSymbol.value = null
}

const runSelectionTask = async () => {
    if (runningSelection.value) return
    if (!confirm('确定要立即开始全市场选股扫描吗？\n这可能需要1-2分钟。')) return
    
    runningSelection.value = true
    selectionTime.value = 0
    timerInterval = setInterval(() => { selectionTime.value++ }, 1000)
    
    try {
        // Trigger report generation for "candidates" section only
        const res = await apiMethods.generateReport('candidates')
        if (res.status === 'started' || res.status === 'success') {
            // Since backend is async background task (if using generateReport), we might need to poll
            // BUT api.generateReport calls /api/report/generate which returns {status: started}
            // and runs in background.
            // We should poll for completion.
            await pollReportStatus()
            
            // After completion, reload list
            alert('选股任务完成！')
            selectedDate.value = '' // Switch to latest
            loadSelections()
        }
    } catch (e) {
        console.error('Run selection failed:', e)
        alert('执行失败: ' + e.message)
    } finally {
        runningSelection.value = false
        clearInterval(timerInterval)
    }
}

const pollReportStatus = async () => {
    return new Promise((resolve) => {
        const check = async () => {
            try {
                const statusRes = await apiMethods.getReportStatus()
                // statusRes: { status: "running" | "idle" | "success" | "error", message: ... }
                // The API /api/report/status returns the global report generation status
                
                if (statusRes.status === 'idle' || statusRes.status === 'success') {
                    resolve()
                } else if (statusRes.status === 'error') {
                    throw new Error(statusRes.message)
                } else {
                    setTimeout(check, 2000)
                }
            } catch (e) {
                // If checking fails, stop polling after some retries or just resolve to let user reload manually
                console.error("Polling error", e)
                resolve()
            }
        }
        check()
    })
}

// === Actions: Detail ===
const loadDetailData = async (symbol) => {
    loadStockMetrics(symbol)
    
    // Try to load detailed analysis for this specific selection date
    // Note: The selection list item `ai_analysis` is usually a summary.
    // We want to see if there is a full report generated.
    // We use the same API as Dashboard: getLatestAnalysis or getAnalysisHistory
    // Ideally, for Screener, we want to see the analysis generated *for that selection date*.
    const dateQuery = selectedDate.value || getCurrentDateString()
    
    // Since `loadAnalysisHistory` logic in Dashboard handles "today" vs "history", let's replicate simpler version
    // If selectedDate is empty (latest) or today, use latest logic.
    if (!selectedDate.value || selectedDate.value === getCurrentDateString()) {
         loadLatestAnalysis(symbol)
    } else {
         loadHistoryAnalysis(symbol, selectedDate.value)
    }
}

const loadStockMetrics = async (symbol) => {
    calculatingScore.value = true
    try {
        const date = selectedDate.value || null
        const response = await apiMethods.getStockMetrics(symbol, date)
        if (response.status === 'success') {
            scoreResult.value = response.data
        } else {
            // Fail silently or try recalculate if needed? 
            // For screener, we expect metrics to exist as it's a selection. 
            // However, maybe we need to fetch fresh if it's "Today"
            scoreResult.value = null
        }
    } catch (e) {
        console.error('Failed to load metrics:', e)
        scoreResult.value = null
    } finally {
        calculatingScore.value = false
    }
}

const runScoreCalculation = async () => {
    if (!selectedStockSymbol.value) return
    calculatingScore.value = true
    try {
        const res = await apiMethods.calculateStockScore(selectedStockSymbol.value)
        if (res.status === 'success') {
            scoreResult.value = res.data
        }
    } catch (e) {
        console.error('Score calculation failed:', e)
    } finally {
        calculatingScore.value = false
    }
}

const loadLatestAnalysis = async (symbol) => {
    loadingAnalysis.value = true
    analysisResult.value = ''
    try {
        const response = await apiMethods.getLatestAnalysis(symbol, activeAnalyzerTab.value)
        if (response.status === 'success' && response.data?.html) {
            analysisResult.value = marked.parse(response.data.html)
        }
    } catch (e) {
        console.error('Load latest analysis failed', e)
    } finally {
        loadingAnalysis.value = false
    }
}

const loadHistoryAnalysis = async (symbol, date) => {
    loadingAnalysis.value = true
    analysisResult.value = ''
    try {
        const response = await apiMethods.getAnalysisHistory(symbol, date, activeAnalyzerTab.value)
        if (response.status === 'success' && response.data?.html) {
            analysisResult.value = marked.parse(response.data.html)
        } else {
            // Fallback: If history not found, maybe show the summary from selection list?
            // Handled in template via selectedStock.ai_analysis
        }
    } catch (e) {
        console.error('Load history analysis failed', e)
    } finally {
        loadingAnalysis.value = false
    }
}

const runAIAnalysis = async () => {
  if (!selectedStockSymbol.value || analyzing.value) return

  analyzing.value = true
  analysisProgress.value = 'Initializing analysis...'
  analysisResult.value = ''
  let accumulatedMarkdown = ''

  try {
    await apiMethods.analyzeStockStream(
      selectedStockSymbol.value,
      activeAnalyzerTab.value,
      (data) => {
        if (data.type === 'progress' || data.type === 'step') {
          analysisProgress.value = data.message || data.content
        } else if (data.type === 'token') {
          accumulatedMarkdown += data.content
          analysisResult.value = marked.parse(accumulatedMarkdown)
        }
      },
      (data) => {
        if (data.type === 'final_html') {
          analysisResult.value = marked.parse(data.content)
        }
        if (data.type === 'complete') {
          analyzing.value = false
          analysisProgress.value = 'Complete'
        }
      },
      (error) => {
        console.error('Analysis failed:', error)
        analysisResult.value = `<div class="text-danger">Analysis Failed: ${error.message}</div>`
        analyzing.value = false
      }
    )
  } catch (error) {
    console.error('Analysis failed:', error)
    analyzing.value = false
  }
}

const addToHoldings = async (stock) => {
  if(!stock) return
  if(confirm(`Add ${stock.symbol} to your watchlist?`)) {
      try {
        await apiMethods.addHolding({ 
            symbol: stock.symbol, 
            name: stock.name, 
            asset_type: stock.asset_type || 'stock' 
        })
        alert(`Successfully added ${stock.name}`)
      } catch (error) {
        alert('Failed to add: ' + error.message)
      }
  }
}

const handleRefreshDetail = () => {
    if(selectedStockSymbol.value) {
        loadDetailData(selectedStockSymbol.value)
        if (showKlineChart.value) {
            loadKlineData(selectedStockSymbol.value)
        }
    }
}

// Helpers
const getScoreColor = (score) => {
    if (!score) return 'text-text-secondary'
    if (score >= 80) return 'text-yellow-400' 
    if (score >= 65) return 'text-purple-400'
    if (score >= 50) return 'text-blue-400'
    return 'text-gray-500' 
}

const stripHtml = (html) => {
  if (!html) return ''
  const tmp = document.createElement("DIV");
  tmp.innerHTML = html;
  return tmp.textContent || tmp.innerText || "";
}

const getCurrentDateString = () => {
    const d = new Date()
    const year = d.getFullYear()
    const month = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
}

watch(showKlineChart, (newValue) => {
  if (newValue && selectedStockSymbol.value) {
    loadKlineData(selectedStockSymbol.value)
  }
})

onMounted(() => {
  loadSelections()
})
</script>

<style scoped>
/* Reuse styles from Dashboard (via global classes or scoped copies) */

/* Prose Container */
.prose-container {
  @apply rounded-lg border border-border-subtle bg-bg-card/50;
  @apply p-6 mx-auto my-4 shadow-lg;
}

.prose-container :deep(.prose) {
  @apply text-text-secondary text-sm leading-relaxed;
}

.prose-container :deep(.prose h1),
.prose-container :deep(.prose h2),
.prose-container :deep(.prose h3) {
  @apply text-text-primary font-semibold mt-3 mb-2;
}

.prose-container :deep(.prose strong) {
  @apply text-text-primary font-bold;
}

.prose-container :deep(.prose ul) {
  @apply list-disc list-inside space-y-1 my-2 text-text-secondary;
}

.prose-container :deep(.prose code) {
  @apply px-1.5 py-0.5 rounded bg-bg-elevated border border-border-subtle;
  @apply text-xs font-mono text-primary;
}

/* Indicator Card (in Kline chart) */
.indicator-card {
  @apply rounded-lg bg-bg-card border border-border-subtle;
  @apply hover:border-border-medium transition-colors duration-200;
}

/* Scrollbar refinement */
.scrollbar-thin::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
.scrollbar-thin::-webkit-scrollbar-track {
  background: transparent;
}
.scrollbar-thin::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
}
.scrollbar-thin::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.2);
}
</style>
