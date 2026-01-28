<template>
  <div class="grid grid-cols-12 h-screen overflow-hidden bg-bg-pattern-grid">

    <!-- Left Column: Market Watch (Responsive Width) -->
    <div class="flex flex-col h-full border-r border-border-subtle bg-bg-elevated/50 backdrop-blur-sm transition-all duration-300"
         :class="selectedStockSymbol ? 'hidden lg:flex col-span-12 lg:col-span-3 xl:col-span-3' : 'col-span-12'">
      <!-- Header -->
      <div class="px-4 py-3 border-b border-border-subtle flex items-center justify-between bg-bg-elevated/80">
        <div class="flex items-center gap-2">
          <div class="w-2 h-2 rounded-full bg-cyan animate-pulse"></div>
          <h2 class="text-xs font-semibold uppercase tracking-wider text-text-tertiary">自选 / 持仓</h2>
        </div>
        <button @click.stop="showAddHoldingModal = true" class="btn-icon group relative" style="z-index: 50;" title="添加自选">
          <PlusIcon class="w-4 h-4" />
          <span class="absolute inset-0 rounded-lg bg-primary/10 scale-0 group-hover:scale-100 transition-transform duration-200"></span>
        </button>
      </div>

      <!-- Market Index Card -->
      <div class="p-3 border-b border-border-subtle bg-bg-card/50">
        <div class="dashboard-card p-3 group cursor-pointer transition-all duration-200">
          <div class="flex items-center justify-between">
            <div>
              <div class="text-[10px] text-text-tertiary mb-1">{{ marketStore.marketState.index.name || '指数' }}</div>
              <div class="digit-display-md text-text-primary">
                {{ marketStore.marketState.index.price?.toFixed(2) || '----.--' }}
              </div>
            </div>
            <div class="text-right">
              <span class="badge" :class="(marketStore.marketState.index.change_pct || 0) >= 0 ? 'badge-up' : 'badge-down'">
                {{ (marketStore.marketState.index.change_pct || 0) >= 0 ? '+' : '' }}{{ marketStore.marketState.index.change_pct?.toFixed(2) }}%
              </span>
            </div>
          </div>
          <!-- 微型进度条 -->
          <div class="mt-2 h-1 bg-bg-elevated rounded-full overflow-hidden">
            <div class="h-full bg-gradient-to-r from-primary to-cyan transition-all duration-500"
                 :style="{ width: Math.abs(marketStore.marketState.index.change_pct || 0) * 5 + '%' }">
            </div>
          </div>
        </div>
      </div>

      <!-- Watchlist (Scrollable) -->
      <div class="overflow-y-auto scrollbar-thin min-h-0 flex-auto h-10">
        <div class="flex flex-col">
           <!-- Empty State -->
           <div v-if="marketStore.marketState.stocks.length === 0" class="p-8 text-center">
             <div class="w-12 h-12 mx-auto mb-3 rounded-full bg-bg-elevated flex items-center justify-center">
               <FunnelIcon class="w-6 h-6 text-text-tertiary" />
             </div>
             <p class="text-sm text-text-tertiary mb-2">暂无自选股</p>
             <button @click="showAddHoldingModal = true" class="text-sm text-primary hover:text-primary/80 transition-colors">
               添加股票
             </button>
           </div>

           <!-- List Items (Responsive) -->
           <div v-if="!selectedStockSymbol" class="hidden md:flex px-4 py-2 border-b border-border-subtle bg-bg-elevated text-xs font-semibold text-text-tertiary">
              <div class="w-16 text-center">类型</div>
              <div class="w-24">代码</div>
              <div class="w-32">名称</div>
              <div class="w-16 text-center">状态</div>
              <div class="w-24 text-right">价格</div>
              <div class="w-24 text-right">涨跌幅</div>
              <div class="w-24 text-right">成本/盈亏</div>
              <div class="w-16 text-right">评分</div>
              <div class="w-16 text-right">量比</div>
              <div class="w-16"></div>
           </div>

           <div v-for="stock in marketStore.marketState.stocks" :key="stock.symbol"
                @click="selectStock(stock)"
                class="stock-list-item group border-b border-border-subtle cursor-pointer transition-all duration-200 relative hover:bg-white/5"
                :class="selectedStockSymbol === stock.symbol ? 'bg-primary/5 border-l-2 border-l-primary pl-[14px] px-4 py-3' : (selectedStockSymbol ? 'px-4 py-3' : 'px-4 py-3 md:py-2')">

                <!-- Conditional Layout based on Selection Mode -->
                
                <!-- 1. Compact Mode (Sidebar) -->
                <template v-if="selectedStockSymbol">
                    <div class="flex justify-between items-center mb-1.5">
                      <div class="flex items-center gap-2">
                        <span class="font-mono font-bold text-base text-text-primary">{{ stock.symbol }}</span>
                         <!-- Asset Type Tag -->
                         <span class="px-1 py-[1px] rounded text-[10px] border font-medium"
                               :class="stock.asset_type === 'etf' ? 'bg-purple-500/20 text-purple-400 border-purple-500/30' : 'bg-blue-500/20 text-blue-400 border-blue-500/30'">
                            {{ stock.asset_type === 'etf' ? 'ETF' : '个股' }}
                         </span>
                         <span v-if="stock.position_size > 0" class="px-1 py-[1px] rounded text-[10px] bg-primary/20 text-primary border border-primary/30 font-medium">持</span>
                      </div>
                      <span class="digit-display-md" :class="stock.change_pct >= 0 ? 'text-up' : 'text-down'">
                        {{ stock.price ? stock.price.toFixed(2) : '----' }}
                      </span>
                    </div>

                    <div class="flex justify-between items-center mb-1">
                      <span class="text-sm text-text-secondary truncate max-w-[120px]">{{ stock.name }}</span>
                      <span class="text-sm font-mono font-bold" :class="stock.change_pct >= 0 ? 'text-up' : 'text-down'">
                        {{ stock.change_pct >= 0 ? '+' : '' }}{{ stock.change_pct?.toFixed(2) }}%
                      </span>
                    </div>

                    <div class="flex justify-between items-center text-xs text-text-tertiary mt-1">
                        <div class="flex items-center gap-2">
                            <!-- Score -->
                            <span v-if="stock.composite_score" class="font-mono font-bold" :class="getScoreColor(stock.composite_score)">
                                {{ stock.composite_score }}分
                            </span>
                             <span v-else class="text-text-tertiary opacity-50 text-[10px]">-</span>
                        </div>
                        
                        <!-- Profit % -->
                        <span v-if="stock.cost_price > 0 && stock.price" class="font-mono" :class="((stock.price - stock.cost_price)/stock.cost_price) >= 0 ? 'text-up' : 'text-down'">
                           盈亏: {{ (((stock.price - stock.cost_price)/stock.cost_price)*100).toFixed(2) }}%
                        </span>
                    </div>
                </template>

                <!-- 2. Wide Mode (Full List) -->
                <template v-else>
                     <!-- Mobile/Compact View (<768px) - reusing compact logic but slightly different -->
                     <div class="md:hidden">
                        <div class="flex justify-between items-center mb-1">
                           <div class="flex items-center gap-2">
                             <span class="font-bold text-text-primary text-base">{{ stock.name }}</span>
                             <span class="font-mono text-xs text-text-tertiary">{{ stock.symbol }}</span>
                             <!-- Asset Type Tag -->
                             <span class="px-1 py-[1px] rounded text-[9px] border font-medium"
                                  :class="stock.asset_type === 'etf' ? 'bg-purple-500/20 text-purple-400 border-purple-500/30' : 'bg-blue-500/20 text-blue-400 border-blue-500/30'">
                                {{ stock.asset_type === 'etf' ? 'ETF' : '个股' }}
                             </span>
                             <span v-if="stock.position_size > 0" class="px-1.5 py-0.5 rounded text-[10px] bg-primary/20 text-primary border border-primary/30">持仓</span>
                           </div>
                           <span class="digit-display-md" :class="stock.change_pct >= 0 ? 'text-up' : 'text-down'">
                             {{ stock.price ? stock.price.toFixed(2) : '----' }}
                           </span>
                        </div>
                        <div class="flex justify-between items-center text-xs">
                           <div class="flex flex-col gap-0.5 text-text-tertiary">
                               <span>
                                   <span v-if="stock.composite_score" class="font-bold mr-2" :class="getScoreColor(stock.composite_score)">{{ stock.composite_score }}分</span>
                                   成本: {{ stock.cost_price > 0 ? stock.cost_price.toFixed(2) : '--' }}
                               </span>
                               <span v-if="stock.cost_price > 0 && stock.price" class="font-mono" :class="((stock.price - stock.cost_price)/stock.cost_price) >= 0 ? 'text-up' : 'text-down'">
                                   盈亏: {{ (((stock.price - stock.cost_price)/stock.cost_price)*100).toFixed(2) }}%
                               </span>
                           </div>
                           <span class="font-mono text-base font-bold" :class="stock.change_pct >= 0 ? 'text-up' : 'text-down'">
                             {{ stock.change_pct >= 0 ? '+' : '' }}{{ stock.change_pct?.toFixed(2) }}%
                           </span>
                        </div>
                     </div>

                     <!-- Desktop View (Grid Like) -->
                     <div class="hidden md:flex items-center text-base h-10">
                         <!-- Type Column -->
                         <div class="w-16 flex justify-center">
                            <span class="text-[10px] w-fit px-1.5 py-0.5 rounded border font-medium"
                                  :class="stock.asset_type === 'etf' ? 'bg-purple-500/10 text-purple-400 border-purple-500/30' : 'bg-blue-500/10 text-blue-400 border-blue-500/30'">
                                {{ stock.asset_type === 'etf' ? 'ETF' : '个股' }}
                            </span>
                         </div>

                         <!-- Symbol -->
                         <div class="w-24 font-mono text-text-secondary font-bold pl-2">
                             {{ stock.symbol }}
                         </div>
                         
                         <!-- Name -->
                         <div class="w-32 flex items-center pr-2">
                             <span class="text-text-primary font-medium truncate text-base hover:text-primary cursor-pointer" title="点击查看详情">{{ stock.name }}</span>
                         </div>
                         
                         <!-- Position Status -->
                         <div class="w-16 flex justify-center">
                            <span v-if="stock.position_size > 0" class="w-fit px-1.5 py-[1px] rounded text-[10px] bg-primary/20 text-primary border border-primary/30">持仓</span>
                            <span v-else class="text-text-tertiary/20 text-[10px]">-</span>
                         </div>
                         
                         <!-- Price -->
                         <div class="w-24 text-right font-mono text-lg font-medium pr-1" :class="stock.change_pct >= 0 ? 'text-up' : 'text-down'">
                             {{ stock.price ? stock.price.toFixed(2) : '----' }}
                         </div>
                         
                         <!-- Change % -->
                         <div class="w-24 text-right font-mono text-base font-bold pr-1" :class="stock.change_pct >= 0 ? 'text-up' : 'text-down'">
                             {{ stock.change_pct >= 0 ? '+' : '' }}{{ stock.change_pct?.toFixed(2) }}%
                         </div>
                         
                         <!-- Cost & PnL -->
                         <div class="w-24 text-right flex flex-col justify-center pr-1">
                             <span class="font-mono text-text-secondary text-sm">{{ stock.cost_price > 0 ? stock.cost_price.toFixed(2) : '--' }}</span>
                             <span v-if="stock.cost_price > 0 && stock.price" class="text-[10px] font-mono"
                                   :class="((stock.price - stock.cost_price)/stock.cost_price) >= 0 ? 'text-up' : 'text-down'">
                                 {{ (((stock.price - stock.cost_price)/stock.cost_price)*100).toFixed(2) }}%
                             </span>
                         </div>
                         
                         <!-- Score -->
                         <div class="w-16 text-right pr-2">
                             <span v-if="stock.composite_score" class="font-mono font-bold text-lg" :class="getScoreColor(stock.composite_score)">
                                 {{ stock.composite_score }}
                             </span>
                             <span v-else class="text-text-tertiary text-sm">--</span>
                         </div>
                         
                         <!-- Volume Ratio -->
                         <div class="w-16 text-right font-mono text-base" :class="stock.volume_ratio > 2 ? 'text-warning' : 'text-text-secondary'">
                             {{ stock.volume_ratio ? stock.volume_ratio.toFixed(2) : '--' }}
                         </div>
                         
                         <!-- Actions -->
                         <div class="w-16 flex justify-end gap-1 relative" style="z-index: 20;">
                             <button @click.stop="openEditModal(stock)" class="p-1.5 hover:bg-white/10 rounded text-text-tertiary hover:text-primary transition-colors" title="编辑">
                                <PencilIcon class="w-4 h-4" />
                             </button>
                             <button @click.stop="confirmRemove(stock)" class="p-1.5 hover:bg-white/10 rounded text-text-tertiary hover:text-danger transition-colors" title="移除">
                                <TrashIcon class="w-4 h-4" />
                             </button>
                         </div>
                     </div>
                </template>

                <!-- Hover Actions (Sidebar Mode only) -->
                <div v-if="selectedStockSymbol" class="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 flex gap-1 bg-bg-card/90 rounded border border-border-subtle shadow-sm p-0.5" style="z-index: 30;">
                   <button @click.stop="openEditModal(stock)" class="p-1 hover:bg-white/10 rounded text-text-tertiary hover:text-primary transition-colors" title="编辑持仓">
                      <PencilIcon class="w-3 h-3" />
                   </button>
                   <button @click.stop="confirmRemove(stock)" class="p-1 hover:bg-white/10 rounded text-text-tertiary hover:text-danger transition-colors" title="移除">
                      <TrashIcon class="w-3 h-3" />
                   </button>
                </div>

                <!-- Active glow effect -->
                <div v-if="selectedStockSymbol === stock.symbol" class="absolute left-0 top-0 bottom-0 w-0.5 bg-gradient-to-b from-primary via-cyan to-primary opacity-50"></div>
           </div>
        </div>
      </div>
    </div>


    <!-- Middle Column: Content Area (Width: 75%) -->
    <div v-if="selectedStockSymbol" class="col-span-12 lg:col-span-9 xl:col-span-9 flex flex-col h-full bg-bg/50 backdrop-blur-sm relative overflow-hidden transition-all duration-300">
       <!-- Toolbar -->
       <div class="h-12 border-b border-border-subtle flex items-center justify-between px-4 bg-bg-elevated/80 backdrop-blur-sm">
          <div class="flex items-center gap-3">
             <button @click="selectedStockSymbol = null" class="btn-icon mr-1" title="关闭详情">
                <XMarkIcon class="w-5 h-5 text-text-tertiary hover:text-text-primary" />
             </button>
             <span class="font-bold text-text-primary text-sm">{{ selectedStockName }}</span>
             <span class="text-xs font-mono text-text-tertiary px-2 py-0.5 rounded bg-bg-elevated border border-border-subtle">{{ selectedStockSymbol || '---' }}</span>
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
             <button @click="handleRefresh" :disabled="marketStore.refreshing" class="btn-icon" title="刷新">
                <ArrowPathIcon class="w-4 h-4" :class="{ 'animate-spin': marketStore.refreshing }" />
             </button>
          </div>
       </div>

       <!-- Kline Chart Area -->
       <div v-if="showKlineChart && selectedStockSymbol" class="flex-1 relative bg-bg-card/30">
          <div ref="chartContainer" class="absolute inset-0 w-full h-full"></div>
          <div class="absolute inset-0 pointer-events-none bg-grid opacity-30"></div>

          <!-- Timeframes -->
          <div class="absolute top-3 left-4 flex gap-1" style="z-index: 10;">
             <button @click="changePeriod('daily')"
                     class="px-2 py-1 text-xs font-medium rounded transition-colors"
                     :class="selectedPeriod === 'daily' ? 'bg-primary/20 text-primary border border-primary/30' : 'text-text-tertiary hover:text-text-secondary hover:bg-white/5'"
                     title="日线">日</button>
             <button @click="changePeriod('weekly')"
                     class="px-2 py-1 text-xs font-medium rounded transition-colors"
                     :class="selectedPeriod === 'weekly' ? 'bg-primary/20 text-primary border border-primary/30' : 'text-text-tertiary hover:text-text-secondary hover:bg-white/5'"
                     title="周线">周</button>
             <button @click="changePeriod('monthly')"
                     class="px-2 py-1 text-xs font-medium rounded transition-colors"
                     :class="selectedPeriod === 'monthly' ? 'bg-primary/20 text-primary border border-primary/30' : 'text-text-tertiary hover:text-text-secondary hover:bg-white/5'"
                     title="月线">月</button>
          </div>

          <!-- Technical Indicators Panel -->
          <div class="absolute bottom-0 left-0 right-0 h-32 border-t border-border-subtle bg-bg-elevated/80 backdrop-blur-sm p-3">
             <h3 class="text-xs font-semibold uppercase tracking-wider text-text-tertiary mb-2 flex items-center gap-2">
               <span class="w-1.5 h-1.5 rounded-full bg-cyan"></span>
               技术指标 (日线参考)
             </h3>
             <div class="grid grid-cols-3 gap-2">
                 <div class="indicator-card p-2">
                   <span class="text-[9px] text-text-tertiary uppercase tracking-wide">MA20 趋势</span>
                   <span class="text-xs font-bold mt-0.5 block" :class="scoreResult?.trend_signal?.includes('多头') ? 'text-up' : (scoreResult?.trend_signal?.includes('空头') ? 'text-down' : 'text-text-primary')">
                     {{ scoreResult?.trend_signal || '---' }}
                   </span>
                 </div>
                 <div class="indicator-card p-2">
                   <span class="text-[9px] text-text-tertiary uppercase tracking-wide">RSI (14)</span>
                   <span class="text-xs font-bold mt-0.5 block" :class="scoreResult?.rsi > 70 ? 'text-warning' : (scoreResult?.rsi < 30 ? 'text-up' : 'text-text-primary')">
                     {{ scoreResult?.rsi || '--' }}
                   </span>
                 </div>
                 <div class="indicator-card p-2">
                   <span class="text-[9px] text-text-tertiary uppercase tracking-wide">量比</span>
                   <span class="text-xs font-bold font-mono text-text-primary mt-0.5 block">
                     {{ scoreResult?.volume_ratio || '--' }}
                   </span>
                 </div>
             </div>
          </div>
       </div>

       <!-- Analysis Report Area (Default View) -->
              <!-- Analysis Report Area (Default View) -->
       <div v-else class="flex-1 bg-bg/30 min-h-0 overflow-hidden flex flex-col">
          
          <!-- 1. Top Section: Score Result (评分结果置顶) -->
          <div class="flex-shrink-0 px-4 pt-4 pb-2">
             <!-- Case A: 已有评分结果 -->
             <StockScoreCard
                 v-if="scoreResult"
                 :metrics="scoreResult"
                 :loading="calculatingScore"
                 :default-expanded="isScoreExpanded"
                 @refresh="runScoreCalculation"
             />

             <!-- Case B: 暂无评分 (显示计算按钮) -->
             <div v-else class="dashboard-card p-6 flex flex-col items-center justify-center border-dashed border-2 border-border-subtle bg-transparent">
                  <div class="text-text-tertiary mb-3 text-sm">暂无评分数据</div>
                  <button @click="runScoreCalculation"
                          :disabled="calculatingScore"
                          class="px-4 py-2 rounded-lg bg-primary/10 text-primary border border-primary/30 hover:bg-primary/20 transition-all flex items-center gap-2 text-sm font-medium">
                      <BoltIcon v-if="!calculatingScore" class="w-4 h-4" />
                      <div v-else class="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin"></div>
                      {{ calculatingScore ? '正在计算...' : '开始技术评分' }}
                  </button>
             </div>
          </div>

          <!-- 2. Middle Section: Sticky Tabs (Tab栏) -->
          <div class="flex-shrink-0 px-4 pt-2 border-b border-border-subtle bg-bg/95 backdrop-blur z-10 sticky top-0">
               <div class="flex items-center justify-between mb-0">
                   <div class="flex items-center gap-6">
                       <button @click="switchTab('multi_agent')"
                               class="pb-3 px-1 text-sm font-medium border-b-2 transition-colors relative"
                               :class="activeAnalyzerTab === 'multi_agent' ? 'text-primary border-primary' : 'text-text-tertiary border-transparent hover:text-text-secondary'">
                         多空辩论
                         <span v-if="activeAnalyzerTab === 'multi_agent' && (analyzing || loadingAnalysis)" class="absolute top-1 right-[-6px] w-1.5 h-1.5 rounded-full bg-primary animate-pulse"></span>
                       </button>
                       <button @click="switchTab('single_expert')"
                               class="pb-3 px-1 text-sm font-medium border-b-2 transition-colors relative"
                               :class="activeAnalyzerTab === 'single_expert' ? 'text-primary border-primary' : 'text-text-tertiary border-transparent hover:text-text-secondary'">
                         专家诊断
                         <span v-if="activeAnalyzerTab === 'single_expert' && (analyzing || loadingAnalysis)" class="absolute top-1 right-[-6px] w-1.5 h-1.5 rounded-full bg-primary animate-pulse"></span>
                       </button>
                   </div>
                   
                   <!-- Date Selector -->
                   <div class="pb-2">
                        <select v-model="selectedAnalysisDate" @change="loadAnalysisHistory"
                                class="bg-bg-elevated border border-border-subtle rounded text-xs text-text-secondary px-2 py-1.5 outline-none focus:border-primary">
                            <option :value="getCurrentDateString()">今日 ({{ getCurrentDateString() }})</option>
                            <option v-for="date in availableAnalysisDates" :key="date" :value="date">{{ date }}</option>
                        </select>
                   </div>
                </div>
          </div>

          <!-- 3. Bottom Section: Content & Actions (分析报告区域) -->
          <div class="flex-1 overflow-y-auto min-h-0 bg-bg/30 p-4">
             <div class="prose-container h-full mt-0 flex flex-col w-full">
                 
                 <!-- Action Button Area inside the Tab Content -->
                 <div class="flex-shrink-0 mb-4 flex justify-between items-center border-b border-border-subtle pb-3">
                    <h3 class="text-sm font-bold text-text-primary m-0 flex items-center gap-2">
                        <span class="w-1.5 h-4 bg-primary rounded-full"></span>
                        {{ activeAnalyzerTab === 'multi_agent' ? 'AI多空辩论分析报告' : 'AI专家诊断报告' }}
                    </h3>
                    
                    <button @click="runAIAnalysis" :disabled="analyzing || loadingAnalysis" 
                            class="btn-primary flex items-center gap-2 text-xs py-1.5 px-3 shadow-md transition-all duration-200">
                        <SparklesIcon v-if="!analyzing && !loadingAnalysis" class="w-3.5 h-3.5 group-hover:animate-pulse" />
                        <span v-else class="w-3.5 h-3.5 rounded-full border-2 border-primary/30 border-t-primary animate-spin"></span>
                        {{ analyzing ? '正在生成分析...' : (loadingAnalysis ? '加载中...' : '生成最新分析') }}
                    </button>
                 </div>

                 <!-- Analysis Progress (if running) -->
                 <div v-if="analysisProgress && analyzing" class="mb-4 p-3 rounded bg-bg-elevated/50 border border-border-subtle">
                   <div class="flex items-center gap-2 text-xs font-mono text-primary">
                     <span class="animate-pulse">▶</span>
                     <span class="truncate">{{ analysisProgress }}</span>
                   </div>
                 </div>

                 <!-- Loading State -->
                 <div v-if="loadingAnalysis" class="flex-1 flex flex-col items-center justify-center py-12 text-text-tertiary gap-3">
                   <div class="w-8 h-8 rounded-full border-2 border-border-subtle border-t-primary animate-spin"></div>
                   <span class="text-sm">正在加载历史报告...</span>
                 </div>

                 <!-- Analysis Result -->
                 <div v-else-if="analysisResult" class="flex-1 pb-5">
                   <div class="prose max-w-none" v-html="analysisResult"></div>
                 </div>

                 <!-- Empty State -->
                 <div v-else class="flex-1 flex flex-col items-center justify-center text-text-tertiary py-12 opacity-60">
                     <SparklesIcon class="w-10 h-10 mb-2 opacity-50" />
                     <span class="text-sm">暂无分析内容</span>
                     <span class="text-xs mt-1">点击右上角按钮生成分析报告</span>
                 </div>
             </div>
          </div>
       </div>

    </div>


  </div>

  <AddHoldingModal v-model:show="showAddHoldingModal" @added="handleHoldingAdded" />
  <EditHoldingModal v-model:show="showEditHoldingModal" :holding="stockToEdit" @updated="handleHoldingUpdated" />
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import { useMarketStore } from '@/stores/market'
import { apiMethods } from '@/utils/api'
import { useKlineChart } from '@/composables/useKlineChart'
import AddHoldingModal from '@/components/AddHoldingModal.vue'
import EditHoldingModal from '@/components/EditHoldingModal.vue'
import StockScoreCard from '@/components/StockScoreCard.vue'
import { marked } from 'marked'
import {
  PlusIcon,
  ArrowPathIcon,
  SparklesIcon,
  DocumentTextIcon,
  FunnelIcon,
  PencilIcon,
  TrashIcon,
  XMarkIcon,
  BeakerIcon,
  BoltIcon,
} from '@heroicons/vue/24/outline'

const marketStore = useMarketStore()

// State
const selectedStockSymbol = ref(null)
const showKlineChart = ref(false)
const selectedPeriod = ref('daily') // New: Chart Period
const analyzing = ref(false)
const calculatingScore = ref(false)
const scoreResult = ref(null) // Stores the metrics result
const isScoreExpanded = ref(false)
const analysisProgress = ref('')
const analysisResult = ref('')
const showAddHoldingModal = ref(false)
const showEditHoldingModal = ref(false)
const stockToEdit = ref(null)
const loadingAnalysis = ref(false)
const activeAnalyzerTab = ref('multi_agent') // 'multi_agent' or 'single_expert'
const availableAnalysisDates = ref([])
const selectedAnalysisDate = ref(null)

// Computed
const selectedStock = computed(() => {
    return marketStore.marketState.stocks.find(s => s.symbol === selectedStockSymbol.value)
})
const selectedStockName = computed(() => selectedStock.value?.name || '---')

// Chart
const chartContainer = ref(null)
const { loadKlineData } = useKlineChart(chartContainer, selectedStockSymbol)

// Change Period Action
const changePeriod = (period) => {
    selectedPeriod.value = period
    if (selectedStockSymbol.value) {
        loadKlineData(selectedStockSymbol.value, period)
    }
}

// Poll Interval
let pollInterval = null

// Helper
const getCurrentDateString = () => {
    const d = new Date()
    const year = d.getFullYear()
    const month = String(d.getMonth() + 1).padStart(2, '0')
    const day = String(d.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
}

// Actions
const selectStock = (stock) => {
  selectedStockSymbol.value = stock.symbol
  // Reset date selection to today/latest when switching stock
  selectedAnalysisDate.value = getCurrentDateString()
  // Reset states
  scoreResult.value = null
  analysisResult.value = ''
  
  loadAnalysisDates(stock.symbol)
  loadLatestAnalysis(stock.symbol)
  loadStockMetrics(stock.symbol, getCurrentDateString())
}

const openEditModal = (stock) => {
    stockToEdit.value = stock
    showEditHoldingModal.value = true
}

const confirmRemove = async (stock) => {
    if(confirm(`确定要移除 ${stock.name} (${stock.symbol}) 吗？`)) {
        try {
            await apiMethods.deleteHolding(stock.symbol)
            await marketStore.fetchStatus()
            // If removed stock was selected, select first available or null
            if (selectedStockSymbol.value === stock.symbol) {
                selectedStockSymbol.value = null
                analysisResult.value = ''
            }
        } catch (e) {
            alert('移除失败: ' + e.message)
        }
    }
}

const switchTab = (tab) => {
  if (activeAnalyzerTab.value === tab) return
  activeAnalyzerTab.value = tab
  if (selectedStockSymbol.value) {
    // Reload dates for new tab mode as well (though currently shared)
    loadAnalysisDates(selectedStockSymbol.value)
    // Reload analysis
    if (selectedAnalysisDate.value === getCurrentDateString()) {
         loadLatestAnalysis(selectedStockSymbol.value)
    } else {
         loadAnalysisHistory()
    }
  }
}

const loadAnalysisDates = async (symbol) => {
    if (!symbol) return
    try {
        const response = await apiMethods.getAnalysisDates(symbol, activeAnalyzerTab.value)
        if (response.status === 'success') {
            // Filter out today's date if present to avoid duplicate with "Today" option
            // or just keep all and handle in UI
            availableAnalysisDates.value = response.dates.filter(d => d !== getCurrentDateString())
        } else {
            availableAnalysisDates.value = []
        }
    } catch (e) {
        console.error('Failed to load dates', e)
    }
}

const loadAnalysisHistory = async () => {
    if (!selectedStockSymbol.value || !selectedAnalysisDate.value) return
    
    // If selected today, use getLatestAnalysis logic
    // Also load metrics for that date
    loadStockMetrics(selectedStockSymbol.value, selectedAnalysisDate.value)

    if (selectedAnalysisDate.value === getCurrentDateString()) {
        loadLatestAnalysis(selectedStockSymbol.value)
        return
    }

    loadingAnalysis.value = true
    analysisResult.value = ''
    try {
        const response = await apiMethods.getAnalysisHistory(selectedStockSymbol.value, selectedAnalysisDate.value, activeAnalyzerTab.value)
         if (response.status === 'success' && response.data?.html) {
          analysisResult.value = marked.parse(response.data.html)
        } else {
          analysisResult.value = `<div class="p-4 text-center text-text-tertiary">暂无 ${selectedAnalysisDate.value} 的分析报告</div>`
        }
    } catch (error) {
        console.error('History load failed:', error)
         analysisResult.value = `<div class="p-4 text-center text-danger">加载失败: ${error.message}</div>`
    } finally {
        loadingAnalysis.value = false
    }
}

// Load latest analysis from database
const loadLatestAnalysis = async (symbol) => {
  if (!symbol) return

  loadingAnalysis.value = true
  analysisResult.value = ''

  try {
    const response = await apiMethods.getLatestAnalysis(symbol, activeAnalyzerTab.value)

    if (response.status === 'success' && response.data?.html) {
      analysisResult.value = marked.parse(response.data.html)
    } else if (response.status === 'no_data') {
      // No analysis available yet, keep empty
      analysisResult.value = ''
    } else if (response.status === 'not_found') {
      analysisResult.value = ''
    }
  } catch (error) {
    console.error('Failed to load latest analysis:', error)
    analysisResult.value = ''
  } finally {
    loadingAnalysis.value = false
  }
}

const getScoreColor = (score) => {
    // 新配色方案：避开红绿，使用 金-紫-蓝-灰 体系
    if (!score) return 'text-text-secondary'
    if (score >= 80) return 'text-yellow-400' // Gold - 极佳/强力推荐
    if (score >= 65) return 'text-purple-400' // Purple - 良好/优质
    if (score >= 50) return 'text-blue-400'   // Blue - 一般/中性
    return 'text-gray-500'                    // Gray - 较弱
}

const loadStockMetrics = async (symbol, date) => {
    if (!symbol) return
    try {
        const response = await apiMethods.getStockMetrics(symbol, date)
        if (response.status === 'success') {
            scoreResult.value = response.data
        } else {
             // Keep previous or clear? Clearing is safer to avoid confusion
             // But if we just switched dates and no data, we should clear
             scoreResult.value = null
        }
    } catch (e) {
        // Silently fail or log
        console.error('Failed to load metrics:', e)
        scoreResult.value = null
    }
}

const handleRefresh = async () => {
    await marketStore.refreshRealtime()
    if(selectedStockSymbol.value) {
        // Reload chart data
        loadKlineData(selectedStockSymbol.value)
    }
}

// Score Calculation (Phase 1)
const runScoreCalculation = async () => {
    if (!selectedStockSymbol.value || calculatingScore.value) return
    
    calculatingScore.value = true
    try {
        const res = await apiMethods.calculateStockScore(selectedStockSymbol.value)
        if (res.status === 'success') {
            scoreResult.value = res.data
        }
    } catch (e) {
        console.error("Score calc failed", e)
        alert("计算失败: " + e.message)
    } finally {
        calculatingScore.value = false
        // Refresh metrics from DB to ensure consistency
        loadStockMetrics(selectedStockSymbol.value, getCurrentDateString())
    }
}

// AI Analysis
const runAIAnalysis = async () => {
  if (!selectedStockSymbol.value || analyzing.value) return

  analyzing.value = true
  analysisProgress.value = 'Initializing'
  // Don't clear result immediately if we want to show loading overlay, but usually better UX to clear or dim
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
          // Reload from database to ensure we have the latest saved version
          setTimeout(() => {
              loadAnalysisDates(selectedStockSymbol.value)
              loadLatestAnalysis(selectedStockSymbol.value)
          }, 500)
        }
      },
      (error) => {
        console.error('Analysis failed:', error)
        analysisResult.value = `<div class="p-3 rounded-lg bg-danger/10 border border-danger/30 text-danger text-xs">分析失败: ${error.message}</div>`
        analyzing.value = false
      }
    )
  } catch (error) {
    console.error('Analysis failed:', error)
    analyzing.value = false
  }
}

const handleHoldingAdded = async () => {
    await marketStore.fetchStatus()
}

const handleHoldingUpdated = async () => {
    await marketStore.fetchStatus()
    // Force refresh selected stock if needed
    if(selectedStockSymbol.value) {
         // Maybe refresh chart indicators
    }
}

// Lifecycle
onMounted(() => {
  marketStore.fetchStatus()
  // Force refresh to ensure latest data on load even if monitoring is off
  marketStore.refreshRealtime()

  // Removed auto-selection to support full list view by default
  // setTimeout(() => {
  //    if (marketStore.marketState.stocks.length > 0 && !selectedStockSymbol.value) {
  //       selectStock(marketStore.marketState.stocks[0])
  //     }
  // }, 500)

})

onUnmounted(() => {
  stopPolling()
})

// Polling Logic
const startPolling = () => {
  stopPolling()
  // Check immediately
  if (marketStore.isMonitoring) {
      marketStore.fetchStatus()
      pollInterval = setInterval(() => {
        marketStore.fetchStatus()
      }, 5000)
  } else {
      // If not monitoring, just fetch once to ensure sync, usually handled by toggle
      // Or poll very slowly (e.g. 30s) just to check connection/updates from other tabs
      // But user requested to stop it, so let's check marketStore IsMonitoring change
  }
}

const stopPolling = () => {
  if (pollInterval) {
    clearInterval(pollInterval)
    pollInterval = null
  }
}

// Watch monitoring state to toggle polling
watch(() => marketStore.isMonitoring, (newVal) => {
  if (newVal) {
    startPolling()
  } else {
    stopPolling()
  }
}, { immediate: true })

// Removed auto-selection watch
// watch(() => marketStore.marketState.stocks, (stocks) => {
//   if (stocks.length > 0 && !selectedStockSymbol.value) {
//     selectStock(stocks[0])
//   }
// })

import { nextTick } from 'vue' // Start of file imports, but adding here for context in replace block if needed or just replace watch

watch(showKlineChart, async (newValue) => {
  if (newValue && selectedStockSymbol.value) {
    // Wait for DOM to render the chart container v-if
    await nextTick()
    loadKlineData(selectedStockSymbol.value, selectedPeriod.value)
  }
})
</script>

<style scoped>
/* Stock List Item */
.stock-list-item {
  position: relative;
  overflow: hidden;
}

.stock-list-item::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(99, 102, 241, 0.03), transparent);
  transform: translateX(-100%);
  transition: transform 0.5s ease;
}

.stock-list-item:hover::before {
  transform: translateX(100%);
}

/* Indicator Card (in Kline chart) */
.indicator-card {
  @apply rounded-lg bg-bg-card border border-border-subtle;
  @apply hover:border-border-medium transition-colors duration-200;
}

/* Prose Content - 分析报告样式 */
.prose-content {
  @apply rounded-lg border border-border-subtle bg-bg-card/50;
  @apply p-4;
  /* 确保内容不会被截断 */
  min-height: 0;
}

.prose-content :deep(.prose) {
  @apply text-text-secondary text-sm leading-relaxed max-w-none;
  /* 确保内部内容可以正常换行和滚动 */
  word-wrap: break-word;
  overflow-wrap: break-word;
}

/* 标题样式 */
.prose-content :deep(.prose h1),
.prose-content :deep(.prose h2),
.prose-content :deep(.prose h3),
.prose-content :deep(.prose h4) {
  @apply text-text-primary font-semibold mt-4 mb-2;
}

.prose-content :deep(.prose h1) {
  @apply text-xl font-bold;
}

.prose-content :deep(.prose h2) {
  @apply text-lg font-bold;
}

.prose-content :deep(.prose h3) {
  @apply text-base font-semibold;
}

/* 段落样式 */
.prose-content :deep(.prose p) {
  @apply mb-3 leading-relaxed;
}

/* 强调文本 */
.prose-content :deep(.prose strong),
.prose-content :deep(.prose b) {
  @apply text-text-primary font-bold;
}

/* 列表样式 */
.prose-content :deep(.prose ul),
.prose-content :deep(.prose ol) {
  @apply list-disc list-inside space-y-1 my-2 text-text-secondary;
  padding-left: 0.5rem;
}

.prose-content :deep(.prose li) {
  @apply mb-1;
}

/* 代码样式 */
.prose-content :deep(.prose code) {
  @apply px-1.5 py-0.5 rounded bg-bg-elevated border border-border-subtle;
  @apply text-xs font-mono text-primary;
  word-break: break-word;
}

.prose-content :deep(.prose pre) {
  @apply p-3 rounded-lg bg-bg-elevated border border-border-subtle overflow-x-auto;
  @apply my-3;
}

.prose-content :deep(.prose pre code) {
  @apply bg-transparent border-none p-0 text-text-secondary;
}

/* 表格样式 */
.prose-content :deep(.prose table) {
  @apply w-full my-3 border-collapse text-sm;
}

.prose-content :deep(.prose th),
.prose-content :deep(.prose td) {
  @apply px-3 py-2 border border-border-subtle;
}

.prose-content :deep(.prose th) {
  @apply bg-bg-elevated/50 font-semibold text-text-tertiary text-left;
}

.prose-content :deep(.prose tr:hover) {
  @apply bg-white/[0.02];
}

/* 链接样式 */
.prose-content :deep(.prose a) {
  @apply text-primary hover:text-primary/80 hover:underline transition-colors;
}

/* 引用样式 */
.prose-content :deep(.prose blockquote) {
  @apply pl-3 border-l-2 border-border-medium my-3;
  @apply text-text-tertiary italic;
}

/* 分隔线 */
.prose-content :deep(.prose hr) {
  @apply my-4 border-t border-border-subtle;
}

/* Prose Container - 用于分析结果区域 */
.prose-container {
  @apply rounded-lg border border-border-subtle bg-bg-card/50;
  @apply p-6 mx-auto my-4 w-full shadow-lg;
}

.prose-container :deep(.prose) {
  @apply text-text-secondary text-sm leading-relaxed;
}

.prose-container :deep(.prose h1),
.prose-container :deep(.prose h2),
.prose-container :deep(.prose h3) {
  @apply text-text-primary font-semibold mt-3 mb-2;
}

.prose-container :deep(.prose p) {
  @apply mb-2;
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
</style>
