<template>
  <div class="dashboard-card p-0 overflow-hidden border border-border-subtle/60 shadow-sm relative group">
    <!-- Header: Score & Rating & Refresh Button (Clickable to toggle) -->
    <div @click="toggleExpanded"
         class="px-4 py-3 border-b border-border-subtle bg-bg-elevated/30 flex items-center justify-between cursor-pointer hover:bg-bg-elevated/50 transition-colors">
      <div class="flex items-center gap-3">
        <!-- Toggle Icon -->
        <ChevronDownIcon
            class="w-4 h-4 text-text-tertiary transition-transform duration-200"
            :class="{ 'rotate-180': isExpanded }"
        />
        
        <div class="text-2xl font-bold font-mono" :class="getScoreColor(primaryScoreValue)">
          {{ primaryScoreValue ?? '--' }}<span class="text-sm font-normal text-text-tertiary ml-1">{{ primaryScoreLabel }}</span>
        </div>
        <div class="flex flex-col">
          <span class="font-bold text-sm flex items-center gap-1" :class="getScoreColor(primaryScoreValue)">
            {{ primaryScoreTag }}
          </span>
          <span class="text-[10px] tracking-widest text-text-tertiary opacity-80">{{ secondaryHeaderText }}</span>
        </div>
        <span v-if="metrics?.score_mode_label"
              class="hidden sm:inline-flex px-2 py-1 rounded-full border border-primary/20 bg-primary/10 text-[10px] font-semibold tracking-wide text-primary">
          {{ metrics?.score_mode_label }}
        </span>
      </div>
      
      <!-- Right: Date & Refresh Action -->
      <div class="flex items-center gap-2">
        <div class="text-[10px] text-text-tertiary bg-bg-elevated px-2 py-1 rounded">
          {{ metrics?.score_date || metrics?.date }}
        </div>
        <button v-if="showRefresh" @click.stop="$emit('refresh')" :disabled="loading"
                class="p-1.5 rounded hover:bg-bg-elevated text-text-tertiary hover:text-primary transition-colors"
                title="重新计算评分">
          <ArrowPathIcon class="w-3.5 h-3.5" :class="{ 'animate-spin': loading }" />
        </button>
      </div>
    </div>

        <div v-if="metrics?.score_mode_note"
         class="px-4 py-2 text-[11px] text-text-secondary border-b border-border-subtle bg-bg-elevated/20">
      {{ metrics?.score_mode_note }}
    </div>

    <!-- Score Details (Expandable) -->
    <div v-show="isExpanded" class="p-4 grid grid-cols-1 md:grid-cols-2 gap-8 bg-bg-card/20 transition-all duration-300">
      <!-- Left: Score Breakdown -->
      <div>
        <h4 class="text-xs font-bold text-text-tertiary uppercase tracking-wider mb-3 flex items-center gap-1">
          📊 评分明细
        </h4>
        <div class="space-y-3">
          <div v-for="(item, index) in metrics?.score_breakdown" :key="index" class="flex flex-col gap-1">
            <div class="flex justify-between text-xs">
              <span class="text-text-secondary font-medium">{{ item[0] }}</span>
              <span class="font-mono text-text-tertiary">{{ item[1] }}/{{ item[2] }}</span>
            </div>
            <div class="h-1.5 w-full bg-bg-elevated rounded-full overflow-hidden">
              <div class="h-full rounded-full transition-all duration-700 ease-out"
                  :style="getBarStyle(item[1], item[2])">
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Right: Key Signals -->
      <div>
        <div v-if="metrics?.entry_score || metrics?.holding_score" class="mb-5 p-3 rounded-lg border border-border-subtle bg-bg-elevated/40">
          <h4 class="text-xs font-bold text-text-tertiary uppercase tracking-wider mb-3 flex items-center gap-1">
            🎯 双评分
          </h4>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div class="rounded-lg border border-border-subtle bg-bg-card/40 p-3">
              <div class="text-[10px] uppercase tracking-wider text-text-tertiary mb-1">入场评分</div>
              <div class="flex items-end gap-2">
                <span class="text-xl font-bold font-mono" :class="getScoreColor(metrics?.entry_score)">{{ metrics?.entry_score ?? '--' }}</span>
                <span class="text-xs text-text-secondary">分</span>
              </div>
              <div class="mt-2 text-[11px] text-text-secondary leading-relaxed">
                {{ summarizeReasons(metrics?.entry_score_details, metrics?.entry_score, 'entry') || '用于候选筛选与排序' }}
              </div>
            </div>
            <div class="rounded-lg border border-border-subtle bg-bg-card/40 p-3">
              <div class="text-[10px] uppercase tracking-wider text-text-tertiary mb-1">持仓评分</div>
              <div class="flex items-end gap-2">
                <span class="text-xl font-bold font-mono" :class="getScoreColor(metrics?.holding_score)">{{ metrics?.holding_score ?? '--' }}</span>
                <span class="text-xs text-text-secondary">分</span>
                <span v-if="metrics?.holding_state_label" class="ml-auto text-[10px] px-2 py-0.5 rounded border border-border-subtle text-text-secondary">
                  {{ metrics?.holding_state_label }}
                </span>
              </div>
              <div class="mt-2 text-[11px] text-text-secondary leading-relaxed">
                {{ summarizeReasons(metrics?.holding_score_details, metrics?.holding_score, 'holding') || '用于持仓状态判断' }}
              </div>
            </div>
          </div>
        </div>

        <div v-if="metrics?.composite_score && primaryScoreMode !== 'legacy'" class="mb-5 rounded-lg border border-border-subtle bg-bg-elevated/20 px-3 py-2 text-[11px] text-text-secondary">
          旧评分参考：<span class="font-mono font-semibold" :class="getScoreColor(metrics?.composite_score)">{{ metrics?.composite_score }}</span>
          <span v-if="metrics?.rating" class="ml-2">{{ metrics?.rating }}</span>
        </div>

        <h4 class="text-xs font-bold text-text-tertiary uppercase tracking-wider mb-3 flex items-center gap-1">
          📈 核心技术信号
        </h4>
        <div class="grid grid-cols-1 gap-y-3 text-sm">
          <!-- Trend -->
          <div class="flex gap-3 items-center">
            <span class="text-text-tertiary w-10 shrink-0">趋势:</span>
            <span class="text-text-secondary">
              <span class="font-medium" :class="metrics?.ma_arrangement === '多头排列' ? 'text-up bg-up/10 px-1.5 py-0.5 rounded' : (metrics?.ma_arrangement === '空头排列' ? 'text-down bg-down/10 px-1.5 py-0.5 rounded' : 'text-text-secondary')">
                {{ metrics?.ma_arrangement || '震荡' }}
              </span>
              <span class="ml-2 text-text-tertiary opacity-80 text-xs">
                ({{ metrics?.trend_signal === '看涨' ? '>MA20' : '<MA20' }})
              </span>
            </span>
          </div>
          <!-- Pattern -->
          <div class="flex gap-3 items-center">
            <span class="text-text-tertiary w-10 shrink-0">形态:</span>
            <span class="text-text-secondary">
              <span v-if="metrics?.pattern_details && metrics?.pattern_details.length > 0" class="text-warning font-medium">
                {{ metrics?.pattern_details.join(', ').replace(/\(\+\d+\)|\(-\d+\)/g, '') }}
              </span>
              <span v-else class="text-text-tertiary italic opacity-60">无显著形态</span>
            </span>
          </div>
          <!-- Momentum -->
          <div class="flex gap-3 items-center">
            <span class="text-text-tertiary w-10 shrink-0">动量:</span>
            <div class="flex gap-3 text-text-secondary font-mono text-sm">
              <span class="px-1.5 py-0.5 bg-bg-elevated rounded border border-border-subtle">
                RSI: <span :class="getRsiColor(metrics?.rsi)" class="font-bold ml-1">{{ metrics?.rsi }}</span>
              </span>
              <span class="px-1.5 py-0.5 bg-bg-elevated rounded border border-border-subtle">
                量比: <span class="font-bold ml-1">{{ metrics?.volume_ratio }}</span>
              </span>
            </div>
          </div>
          <!-- Risk -->
          <div class="flex gap-3 items-center">
            <span class="text-text-tertiary w-10 shrink-0">止损:</span>
            <span class="text-text-primary font-mono font-bold">{{ metrics?.stop_loss_suggest || 'N/A' }}</span>
          </div>
        </div>
      </div>
    </div>
    
    <!-- Suggestion Footer -->
    <div v-if="metrics?.operation_suggestion && isExpanded" class="px-5 py-3 bg-primary/5 border-t border-primary/10 text-xs text-primary flex items-start gap-2.5">
      <span class="mt-0.5 text-base">💡</span>
      <span class="leading-relaxed font-medium">{{ metrics?.operation_suggestion }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import {
  ArrowPathIcon,
  ChevronDownIcon
} from '@heroicons/vue/24/outline'

const props = defineProps({
  metrics: {
    type: Object,
    default: null
  },
  loading: {
    type: Boolean,
    default: false
  },
  showRefresh: {
    type: Boolean,
    default: true
  },
  defaultExpanded: {
      type: Boolean,
      default: false
  },
  primaryScoreMode: {
      type: String,
      default: 'legacy'
  }
})

const emit = defineEmits(['refresh'])

const isExpanded = ref(props.defaultExpanded)

// Watch for prop changes to update local state if needed
watch(() => props.defaultExpanded, (newVal) => {
    isExpanded.value = newVal
})

const toggleExpanded = () => {
    isExpanded.value = !isExpanded.value
}

const primaryScoreValue = computed(() => {
    if (!props.metrics) return null
    if (props.primaryScoreMode === 'entry') return props.metrics.entry_score ?? props.metrics.composite_score
    if (props.primaryScoreMode === 'holding') return props.metrics.holding_score ?? props.metrics.composite_score
    return props.metrics.composite_score
})

const primaryScoreLabel = computed(() => {
    if (props.primaryScoreMode === 'entry') return '入场评分'
    if (props.primaryScoreMode === 'holding') return '持仓评分'
    return '旧评分'
})

const primaryScoreTag = computed(() => {
    if (props.primaryScoreMode === 'entry') return '候选排序'
    if (props.primaryScoreMode === 'holding') return props.metrics?.holding_state_label || '持仓状态'
    return props.metrics?.rating?.split(' ')[0] || '原评分方式'
})

const secondaryHeaderText = computed(() => {
    if (props.primaryScoreMode === 'entry') {
        return summarizeReasons(props.metrics?.entry_score_details, props.metrics?.entry_score, 'entry') || (props.metrics?.rating || '原评分方式')
    }
    if (props.primaryScoreMode === 'holding') {
        return summarizeReasons(props.metrics?.holding_score_details, props.metrics?.holding_score, 'holding') || (props.metrics?.rating || '原评分方式')
    }
    return props.metrics?.rating?.split(' ').slice(1).join(' ') || '🟢🟢🟢'
})

// Helpers
const getScoreColor = (score) => {
    if (!score) return 'text-text-secondary'
    if (score >= 80) return 'text-yellow-400' // Gold
    if (score >= 65) return 'text-purple-400' // Purple
    if (score >= 50) return 'text-blue-400'   // Blue
    return 'text-gray-500'                    // Gray
}

const getBarStyle = (current, max) => {
    if (!max || max <= 0) {
        return {
            width: '0%',
            backgroundColor: 'rgb(99 102 241 / 0.3)'
        }
    }
    const pct = current / max
    const opacity = 0.3 + (pct * 0.7)
    return {
        width: (pct * 100) + '%',
        backgroundColor: `rgb(99 102 241 / ${opacity})`
    }
}

const getRsiColor = (rsi) => {
    if (!rsi) return ''
    if (rsi > 70) return 'text-warning'
    if (rsi < 30) return 'text-success'
    return 'text-text-primary'
}

const NEGATIVE_REASON_KEYWORDS = [
    '跌破',
    '过大',
    '过深',
    '过热',
    '爆量',
    '下跌',
    '转弱',
    '失守',
    '诱多',
    '风险',
    '偏离',
    '承压',
    '贴近布林上轨',
]

const POSITIVE_REASON_KEYWORDS = [
    '站上',
    '上方',
    '未转空',
    '未恶化',
    '趋势延续',
    '止损参考',
    '支撑',
    '适中',
    '可承受',
    '可容忍',
    '正常整理',
    '金叉',
    '甜蜜区',
]

const isNegativeReason = (reason) => {
    if (!reason) return false
    return NEGATIVE_REASON_KEYWORDS.some(keyword => reason.includes(keyword))
}

const isPositiveReason = (reason) => {
    if (!reason) return false
    return POSITIVE_REASON_KEYWORDS.some(keyword => reason.includes(keyword))
}

const uniqueReasons = (reasons) => {
    const seen = new Set()
    return reasons.filter(reason => {
        if (!reason || seen.has(reason)) return false
        seen.add(reason)
        return true
    })
}

const summarizeReasons = (reasons, score, mode = 'entry') => {
    if (!reasons || !Array.isArray(reasons) || reasons.length === 0) return ''

    const normalized = uniqueReasons(reasons)
    const negativeReasons = normalized.filter(isNegativeReason)
    const positiveReasons = normalized.filter(isPositiveReason)
    const neutralReasons = normalized.filter(reason => !isNegativeReason(reason) && !isPositiveReason(reason))

    let selected = []

    if ((score ?? 0) < 40) {
        selected = [...negativeReasons, ...neutralReasons, ...positiveReasons].slice(0, 2)
    } else if ((score ?? 0) < 60) {
        const firstNegative = negativeReasons[0]
        const firstPositive = positiveReasons[0] || neutralReasons[0]
        selected = [firstNegative, firstPositive].filter(Boolean)
        if (selected.length < 2) {
            selected = [...selected, ...normalized.filter(reason => !selected.includes(reason))].slice(0, 2)
        }
    } else {
        selected = [...positiveReasons, ...neutralReasons, ...negativeReasons].slice(0, 2)
    }

    if (mode === 'holding' && (score ?? 0) < 55 && negativeReasons.length === 0 && selected.length > 0) {
        selected[0] = `偏弱但未破位: ${selected[0]}`
    }

    if (mode === 'entry' && (score ?? 0) < 40 && negativeReasons.length === 0 && selected.length > 0) {
        selected[0] = `入场性价比不足: ${selected[0]}`
    }

    return selected.join(' / ')
}

</script>
