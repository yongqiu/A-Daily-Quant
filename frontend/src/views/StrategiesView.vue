<template>
  <div class="h-screen flex flex-col bg-bg-pattern-grid overflow-hidden">
    <!-- Header -->
    <div class="h-16 border-b border-border-subtle flex items-center justify-between px-6 bg-bg-elevated/80 backdrop-blur-sm">
      <div>
        <h1 class="text-sm font-semibold uppercase tracking-wider text-text-primary flex items-center gap-2">
          <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-purple to-primary flex items-center justify-center shadow-glow-purple">
            <CpuChipIcon class="w-4 h-4 text-white" />
          </div>
          Strategy Configuration
        </h1>
        <p class="text-[10px] text-text-tertiary mt-1 flex items-center gap-1.5">
          <span class="w-1 h-1 rounded-full bg-purple animate-pulse"></span>
          AI Strategy Templates & Parameters
        </p>
      </div>
    </div>

    <!-- Main Content -->
    <div class="flex-1 flex gap-6 overflow-hidden p-6">
      <!-- Sidebar: Strategy List -->
      <div class="w-80 flex-shrink-0 flex flex-col">
        <div class="mb-4">
          <h2 class="text-xs font-semibold uppercase tracking-wider text-text-tertiary">策略列表</h2>
          <p class="text-[10px] text-text-tertiary mt-1">选择策略进行配置</p>
        </div>

        <div class="flex-1 overflow-y-auto scrollbar-thin pr-2 space-y-2">
          <div v-for="s in strategyStore.strategies" :key="s.id"
               @click="selectStrategy(s)"
               class="strategy-card group p-4 rounded-xl cursor-pointer transition-all duration-200 border"
               :class="selectedStrategyId === s.id
                 ? 'bg-primary/10 border-primary/50'
                 : 'bg-bg-card border-border-subtle hover:border-border-medium hover:bg-bg-cardHover'">
            <div class="flex items-start justify-between mb-3">
              <div class="flex-1">
                <div class="font-semibold text-text-primary text-sm">{{ s.name }}</div>
                <span class="badge badge-primary mt-2 font-mono text-[10px]">{{ s.slug }}</span>
              </div>
              <div class="w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ml-2"
                   :class="selectedStrategyId === s.id ? 'bg-primary shadow-glow-primary' : 'bg-bg-elevated'">
                <DocumentTextIcon class="w-4 h-4" :class="selectedStrategyId === s.id ? 'text-white' : 'text-text-tertiary'" />
              </div>
            </div>
            <p class="text-xs text-text-tertiary line-clamp-2">{{ s.description }}</p>
          </div>
        </div>
      </div>

      <!-- Main Editor -->
      <div v-if="strategyStore.selectedStrategy" class="flex-1 flex flex-col min-w-0">
        <div class="dashboard-card flex-1 flex flex-col overflow-hidden">
          <!-- Tabs -->
          <div class="flex border-b border-border-subtle">
            <button @click="activeTab = 'prompt'"
                    class="flex-1 py-3 text-xs font-semibold uppercase tracking-wider border-b-2 transition-all duration-200 relative"
                    :class="activeTab === 'prompt' ? 'border-primary text-primary' : 'border-transparent text-text-tertiary hover:text-text-secondary'">
              <span v-if="activeTab === 'prompt'" class="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-primary via-cyan to-primary opacity-50"></span>
              <span class="flex items-center justify-center gap-2">
                <PencilIcon class="w-4 h-4" />
                Prompt 模板
              </span>
            </button>
            <button @click="activeTab = 'params'"
                    class="flex-1 py-3 text-xs font-semibold uppercase tracking-wider border-b-2 transition-all duration-200 relative"
                    :class="activeTab === 'params' ? 'border-primary text-primary' : 'border-transparent text-text-tertiary hover:text-text-secondary'">
              <span v-if="activeTab === 'params'" class="absolute bottom-0 left-0 right-0 h-0.5 bg-gradient-to-r from-primary via-cyan to-primary opacity-50"></span>
              <span class="flex items-center justify-center gap-2">
                <AdjustmentsHorizontalIcon class="w-4 h-4" />
                参数配置
              </span>
            </button>
          </div>

          <!-- Prompt Editor -->
          <div v-if="activeTab === 'prompt'" class="flex-grow flex flex-col min-h-0">
            <div class="p-6 flex-grow">
              <div class="relative h-full">
                <textarea
                  v-model="strategyStore.selectedStrategy.template_content"
                  class="code-editor w-full h-full resize-none"
                  placeholder="输入 Prompt 模板...支持使用 {variable} 格式的占位符"></textarea>
                <!-- Editor glow effect -->
                <div class="absolute inset-0 pointer-events-none rounded-lg border border-primary/0 transition-colors duration-200 group-hover:border-primary/10"></div>
              </div>
            </div>
            <div class="p-5 border-t border-border-subtle flex justify-between items-center bg-bg-elevated/30">
              <div class="flex items-center gap-2 text-[10px] text-text-tertiary">
                <InformationCircleIcon class="w-3.5 h-3.5" />
                <span>支持使用 {variable} 格式的占位符</span>
              </div>
              <button @click="saveTemplate" :disabled="saving" class="btn-primary flex items-center gap-2">
                <div v-if="saving" class="spinner w-4 h-4 border-2 border-white/30 border-t-white"></div>
                <CheckIcon v-else class="w-4 h-4" />
                <span>{{ saving ? '保存中...' : '保存模板' }}</span>
              </button>
            </div>
          </div>

          <!-- Parameters Editor -->
          <div v-if="activeTab === 'params'" class="flex-grow overflow-y-auto p-6">
            <div v-if="!strategyStore.selectedStrategy.params || Object.keys(strategyStore.selectedStrategy.params).length === 0"
                 class="flex flex-col items-center justify-center py-20">
              <div class="w-16 h-16 rounded-xl bg-bg-elevated flex items-center justify-center mb-4">
                <CubeIcon class="w-8 h-8 text-text-tertiary" />
              </div>
              <div class="text-sm font-medium text-text-secondary mb-1">暂无参数</div>
              <div class="text-xs text-text-tertiary">此策略没有可配置的参数</div>
            </div>
            <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div v-for="(val, key) in strategyStore.selectedStrategy.params" :key="key"
                   class="param-card">
                <label class="block text-xs font-medium mb-3 text-text-tertiary uppercase tracking-wide">{{ key }}</label>
                <div class="flex gap-2">
                  <input
                    v-model="strategyStore.selectedStrategy.params[key]"
                    type="text"
                    class="input-base font-mono text-sm flex-1">
                  <button
                    @click="saveParam(key, strategyStore.selectedStrategy.params[key])"
                    :disabled="savingParam === key"
                    class="btn-secondary px-3 py-2 text-xs whitespace-nowrap">
                    {{ savingParam === key ? '保存中...' : '保存' }}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Empty State -->
      <div v-else class="flex-1 flex flex-col items-center justify-center dashboard-card p-12">
        <div class="w-20 h-20 rounded-xl bg-bg-elevated flex items-center justify-center mb-6">
          <CpuChipIcon class="w-10 h-10 text-text-tertiary" />
        </div>
        <div class="text-base font-semibold text-text-primary mb-2">选择一个策略</div>
        <div class="text-sm text-text-tertiary">请从左侧列表选择一个策略进行配置</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useStrategyStore } from '@/stores/strategy'
import {
  CpuChipIcon,
  DocumentTextIcon,
  PencilIcon,
  AdjustmentsHorizontalIcon,
  InformationCircleIcon,
  CheckIcon,
  CubeIcon
} from '@heroicons/vue/24/outline'

const strategyStore = useStrategyStore()

const activeTab = ref('prompt')
const saving = ref(false)
const savingParam = ref(null)

const selectedStrategyId = computed(() => strategyStore.selectedStrategy?.id)

const selectStrategy = async (strategy) => {
  await strategyStore.fetchStrategy(strategy.slug)
}

const saveTemplate = async () => {
  if (!strategyStore.selectedStrategy) return

  saving.value = true
  try {
    await strategyStore.updateTemplate(
      strategyStore.selectedStrategy.id,
      strategyStore.selectedStrategy.template_content
    )
    alert('模板保存成功！')
  } catch (error) {
    console.error('保存模板失败:', error)
    alert('保存失败: ' + (error.message || '未知错误'))
  } finally {
    saving.value = false
  }
}

const saveParam = async (key, value) => {
  if (!strategyStore.selectedStrategy) return

  savingParam.value = key
  try {
    await strategyStore.updateParam(
      strategyStore.selectedStrategy.id,
      key,
      value
    )
  } catch (error) {
    console.error('保存参数失败:', error)
    alert('保存失败: ' + (error.message || '未知错误'))
  } finally {
    savingParam.value = null
  }
}

onMounted(() => {
  strategyStore.fetchStrategies()
})
</script>

<style scoped>
/* Strategy Card */
.strategy-card {
  @apply transition-all duration-200;
}

.strategy-card:hover {
  @apply shadow-card-hover;
}

/* Parameter Card */
.param-card {
  @apply p-4 rounded-lg bg-bg-card border border-border-subtle;
  @apply hover:border-border-medium transition-all duration-200;
}

/* Code Editor */
.code-editor {
  @apply w-full h-full bg-bg-elevated border border-border-subtle rounded-lg;
  @apply p-4 text-sm font-mono text-text-secondary;
  @apply focus:border-primary/50 focus:ring-2 focus:ring-primary/20 outline-none;
  @apply resize-none;
  font-family: 'JetBrains Mono', 'Menlo', 'Monaco', 'Courier New', monospace;
  line-height: 1.6;
}

/* Line clamp utility */
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
