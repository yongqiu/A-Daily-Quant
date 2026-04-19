<template>
  <div v-if="plan" class="mb-6 bg-bg-elevated border border-border-subtle rounded-lg overflow-hidden shadow-sm">
    <!-- Header -->
    <div class="px-4 py-3 border-b border-border-subtle bg-bg-card/50 flex items-center justify-between">
      <h3 class="font-bold text-text-primary flex items-center gap-2 text-sm">
        <span class="w-1.5 h-4 bg-primary rounded-full"></span>
        <span>交易执行计划 (Action Plan)</span>
      </h3>
      <div v-if="plan.risk_rating" class="flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-medium border"
           :class="getRiskColor(plan.risk_rating)">
        <span class="opacity-70">风险等级:</span>
        <span>{{ plan.risk_rating }}</span>
      </div>
    </div>

    <!-- Content Grid -->
    <div class="p-4 grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
      
      <!-- Key Price Levels -->
      <div class="space-y-3">
        <div class="grid grid-cols-2 gap-3">
           <div class="p-2.5 rounded bg-bg/50 border border-border-subtle">
             <div class="text-xs text-text-tertiary mb-1">💰 低吸参考 (Buy Dip)</div>
             <div class="font-mono font-bold text-text-primary">{{ plan.buy_dip_price || '--' }}</div>
           </div>
           <div class="p-2.5 rounded bg-bg/50 border border-border-subtle">
             <div class="text-xs text-text-tertiary mb-1">🚫 最高追涨 (Max Price)</div>
             <div class="font-mono font-bold text-text-secondary">{{ plan.buy_price_max || '--' }}</div>
           </div>
        </div>

        <div class="grid grid-cols-2 gap-3">
           <div class="p-2.5 rounded bg-danger/5 border border-danger/20 relative overflow-hidden">
             <div class="absolute right-0 top-0 p-1 text-danger/10"><svg class="w-6 h-6" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"></path></svg></div>
             <div class="text-xs text-text-tertiary mb-1">🛡 严格止损 (Stop Loss)</div>
             <div class="font-mono font-bold text-danger">{{ plan.stop_loss_price || '--' }}</div>
           </div>
           <div class="p-2.5 rounded bg-up/5 border border-up/20 relative overflow-hidden">
             <div class="absolute right-0 top-0 p-1 text-up/10"><svg class="w-6 h-6" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"></path></svg></div>
             <div class="text-xs text-text-tertiary mb-1">🎯 止盈目标 (Target)</div>
             <div class="font-mono font-bold text-up">{{ plan.take_profit_target || '--' }}</div>
           </div>
        </div>
      </div>

      <!-- Trigger Condition -->
      <div class="flex flex-col">
        <div class="flex-1 p-3 rounded bg-primary/5 border border-primary/20 flex flex-col justify-center">
           <div class="flex items-start gap-2 mb-1">
             <span class="mt-0.5 text-primary"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg></span>
             <span class="text-xs font-bold text-primary uppercase tracking-wide">🚀 买入触发条件 (Trigger)</span>
           </div>
           <div class="pl-6 text-sm text-text-primary leading-relaxed">
             {{ plan.buy_trigger || '暂无明确触发条件' }}
           </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
defineProps({
  plan: {
    type: Object,
    required: true,
    default: () => ({})
  }
})

const getRiskColor = (riskRating) => {
  if (!riskRating) return 'bg-gray-500/10 text-gray-400 border-gray-500/30'
  if (riskRating.includes('低')) return 'bg-green-500/10 text-green-400 border-green-500/30'
  if (riskRating.includes('高')) return 'bg-red-500/10 text-red-400 border-red-500/30'
  return 'bg-yellow-500/10 text-yellow-400 border-yellow-500/30' // 中
}
</script>
