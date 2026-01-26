<template>
  <aside class="flex flex-col w-[60px] bg-bg-elevated border-r border-border-subtle h-full z-20">
    <!-- Logo Area - 科技感发光效果 -->
    <div class="h-14 flex items-center justify-center border-b border-border-subtle mb-2">
      <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-primary to-purple-600 flex items-center justify-center shadow-glow-primary relative overflow-hidden group">
        <!-- 扫描线动画 -->
        <div class="absolute inset-0 bg-gradient-to-b from-white/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300"></div>
        <svg class="w-5 h-5 text-white relative z-10" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
        </svg>
      </div>
    </div>

    <!-- Navigation -->
    <nav class="flex-1 flex flex-col items-center gap-2 py-2">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        class="nav-item group relative"
      >
        <div class="w-10 h-10 flex items-center justify-center rounded-lg transition-all duration-200">
          <component :is="item.icon" class="w-5 h-5 transition-all duration-200" />

          <!-- Active indicator glow -->
          <span class="absolute inset-0 rounded-lg bg-primary/10 opacity-0 group-[.active]:opacity-100 transition-opacity duration-200"></span>
          <!-- Active indicator border -->
          <span class="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-primary rounded-r-full opacity-0 group-[.active]:opacity-100 transition-opacity duration-200"></span>
        </div>

        <!-- Tooltip -->
        <span class="nav-tooltip">
          {{ item.label }}
        </span>
      </router-link>
    </nav>

    <!-- Bottom Actions -->
    <div class="p-2 border-t border-border-subtle flex flex-col gap-2 items-center">
        <!-- Monitor Status Toggle -->
        <button
            @click="marketStore.toggleMonitor"
            class="w-10 h-10 flex items-center justify-center rounded-lg transition-all duration-200 group relative"
            :class="marketStore.isMonitoring ? 'text-up hover:bg-up/10' : 'text-text-tertiary hover:text-text-secondary hover:bg-white/5'"
            title="监控开关"
        >
             <!-- 监控中状态 - 发光效果 -->
             <svg v-if="marketStore.isMonitoring" class="w-5 h-5 animate-pulse-slow" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5.636 18.364a9 9 0 010-12.728m12.728 0a9 9 0 010 12.728m-9.9-2.829a5 5 0 010-7.07m7.072 0a5 5 0 010 7.07M13 12a1 1 0 11-2 0 1 1 0 012 0z" />
             </svg>
             <!-- 监控关闭状态 -->
             <svg v-else class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 5.636a9 9 0 010 12.728m0 0l-2.829-2.829m2.829 2.829L21 21M15.536 8.464a5 5 0 010 7.072m0 0l-2.829-2.829m-4.243 2.829a4.978 4.978 0 01-1.414-2.83m-1.414 5.658a9 9 0 01-2.167-9.238m7.824 2.167a1 1 0 111.414 1.414m-1.414-1.414L3 3" />
             </svg>

             <!-- Status indicator dot -->
             <span class="absolute bottom-1 right-1 w-1.5 h-1.5 rounded-full transition-all duration-200"
                   :class="marketStore.isMonitoring ? 'bg-up shadow-glow-success' : 'bg-text-tertiary'">
             </span>
        </button>
    </div>
  </aside>
</template>

<script setup>
import { useMarketStore } from '@/stores/market'
import {
  HomeIcon,
  FunnelIcon,
  CpuChipIcon
} from '@heroicons/vue/24/outline'

const marketStore = useMarketStore()

const navItems = [
  { path: '/', label: '监控台', icon: HomeIcon },
  { path: '/screener', label: '选股器', icon: FunnelIcon },
  { path: '/strategies', label: '策略配置', icon: CpuChipIcon },
]
</script>

<style scoped>
/* 导航项样式 */
.nav-item {
  @apply text-text-tertiary hover:text-text-secondary;
}

.nav-item.router-link-active {
  @apply text-primary;
}

.nav-item .icon {
  @apply relative z-10;
}

.nav-item.router-link-active .icon {
  filter: drop-shadow(0 0 8px rgba(99, 102, 241, 0.4));
}

/* Tooltip样式 */
.nav-tooltip {
  @apply absolute left-full ml-3 px-2 py-1 bg-bg-card border border-border-subtle rounded text-xs text-text-primary;
  @apply opacity-0 group-hover:opacity-100 transition-opacity duration-200 whitespace-nowrap z-50 pointer-events-none;
  @apply shadow-card;
  backdrop-filter: blur(8px);
}

.nav-tooltip::before {
  content: '';
  position: absolute;
  left: -4px;
  top: 50%;
  transform: translateY(-50%);
  width: 0;
  height: 0;
  border-top: 4px solid transparent;
  border-bottom: 4px solid transparent;
  border-right: 4px solid theme('colors.border.subtle');
}

/* 脉冲动画 */
@keyframes pulse-slow {
  0%, 100% {
    opacity: 1;
    filter: drop-shadow(0 0 4px rgba(34, 197, 94, 0.4));
  }
  50% {
    opacity: 0.7;
    filter: drop-shadow(0 0 8px rgba(34, 197, 94, 0.6));
  }
}

.animate-pulse-slow {
  animation: pulse-slow 2s ease-in-out infinite;
}
</style>
