<template>
  <TransitionRoot appear :show="show" as="template">
    <Dialog as="div" @close="handleClose" class="relative z-50">
      <TransitionChild
        as="template"
        enter="duration-300 ease-out"
        enter-from="opacity-0"
        enter-to="opacity-100"
        leave="duration-200 ease-in"
        leave-from="opacity-100"
        leave-to="opacity-0"
      >
        <div class="fixed inset-0 bg-black/60 backdrop-blur-sm" />
      </TransitionChild>

      <div class="fixed inset-0 overflow-y-auto">
        <div class="flex min-h-full items-center justify-center p-4 text-center">
          <TransitionChild
            as="template"
            enter="duration-300 ease-out"
            enter-from="opacity-0 scale-95"
            enter-to="opacity-100 scale-100"
            leave="duration-200 ease-in"
            leave-from="opacity-100 scale-100"
            leave-to="opacity-0 scale-95"
          >
            <DialogPanel class="dialog-panel w-full max-w-md transform transition-all">
              <!-- Header -->
              <div class="flex items-center justify-between p-6 border-b border-border-subtle">
            <div class="flex items-center gap-3">
              <div class="w-10 h-10 rounded-lg bg-gradient-to-br from-primary to-purple-600 flex items-center justify-center shadow-glow-primary">
                <PlusIcon class="w-5 h-5 text-white" />
              </div>
              <div>
                <DialogTitle class="text-base font-semibold text-text-primary">添加持仓</DialogTitle>
                <p class="text-xs text-text-tertiary mt-0.5">添加新的股票到监控列表</p>
              </div>
            </div>
            <button @click="handleClose" class="btn-icon">
              <XMarkIcon class="w-5 h-5" />
            </button>
          </div>

          <!-- Form Content -->
          <form @submit.prevent="handleSubmit" class="p-6 space-y-5">
            <!-- 股票代码 -->
            <div class="form-field">
              <label for="symbol" class="form-label">
                股票代码 <span class="text-danger">*</span>
              </label>
              <div class="relative">
                <input
                  id="symbol"
                  v-model="form.symbol"
                  type="text"
                  class="input-base"
                  placeholder="如: 600519"
                  required
                  @input="handleSymbolInput"
                />
                <div class="absolute right-3 top-1/2 -translate-y-1/2">
                  <MagnifyingGlassIcon v-if="!searching" class="w-4 h-4 text-text-tertiary" />
                  <div v-else class="spinner w-4 h-4 border-2 border-border-subtle border-t-primary"></div>
                </div>
              </div>
              <!-- 搜索结果提示 -->
              <p v-if="stockHint" class="form-hint">
                <span class="text-primary">{{ stockHint }}</span>
              </p>
            </div>

            <!-- 股票名称 -->
            <div class="form-field">
              <label for="name" class="form-label">股票名称</label>
              <input
                id="name"
                v-model="form.name"
                type="text"
                class="input-base"
                placeholder="如: 贵州茅台"
              />
            </div>

            <!-- 成本价和持仓数量 - 两列布局 -->
            <div class="grid grid-cols-2 gap-4">
              <div class="form-field">
                <label for="cost_price" class="form-label">成本价</label>
                <div class="relative">
                  <input
                    id="cost_price"
                    v-model.number="form.cost_price"
                    type="number"
                    step="0.001"
                    class="input-base pl-8"
                    placeholder="0.000"
                  />
                  <span class="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary text-sm">¥</span>
                </div>
              </div>

              <div class="form-field">
                <label for="position_size" class="form-label">持仓数量</label>
                <input
                  id="position_size"
                  v-model.number="form.position_size"
                  type="number"
                  class="input-base"
                  placeholder="0"
                />
              </div>
            </div>

            <!-- 资产类型选择 -->
            <div class="form-field">
              <label class="form-label">资产类型</label>
              <div class="flex gap-2">
                <button
                  type="button"
                  @click="form.asset_type = 'stock'"
                  class="type-button"
                  :class="form.asset_type === 'stock' ? 'type-button-active' : 'type-button-inactive'"
                >
                  股票
                </button>
                <button
                  type="button"
                  @click="form.asset_type = 'etf'"
                  class="type-button"
                  :class="form.asset_type === 'etf' ? 'type-button-active' : 'type-button-inactive'"
                >
                  ETF
                </button>
              </div>
            </div>

            <!-- Action Buttons -->
            <div class="flex gap-3 pt-4">
              <button
                type="button"
                @click="handleClose"
                class="btn-secondary flex-1"
              >
                取消
              </button>
              <button
                type="submit"
                :disabled="submitting || !form.symbol"
                class="btn-primary flex-1 flex items-center justify-center gap-2"
              >
                <div v-if="submitting" class="spinner w-4 h-4 border-2 border-white/30 border-t-white"></div>
                <PlusIcon v-else class="w-4 h-4" />
                <span>{{ submitting ? '添加中...' : '确认添加' }}</span>
              </button>
            </div>
          </form>

              <!-- Footer note -->
              <div class="px-6 pb-6">
                <p class="text-xs text-text-tertiary flex items-center gap-2">
                  <InformationCircleIcon class="w-4 h-4" />
                  添加后将自动开始监控实时行情
                </p>
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </div>
    </Dialog>
  </TransitionRoot>
</template>

<script setup>
import { ref, watch } from 'vue'
import {
  TransitionRoot,
  TransitionChild,
  Dialog,
  DialogPanel,
  DialogTitle,
} from '@headlessui/vue'
import { PlusIcon, XMarkIcon, MagnifyingGlassIcon, InformationCircleIcon } from '@heroicons/vue/24/outline'
import { apiMethods } from '@/utils/api'

const props = defineProps({
  show: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:show', 'added'])

const form = ref({
  symbol: '',
  name: '',
  cost_price: 0,
  position_size: 0,
  asset_type: 'stock'
})

const submitting = ref(false)
const searching = ref(false)
const stockHint = ref('')

const handleClose = () => {
  emit('update:show', false)
  // 重置表单
  form.value = {
    symbol: '',
    name: '',
    cost_price: 0,
    position_size: 0,
    asset_type: 'stock'
  }
  stockHint.value = ''
}

const handleSymbolInput = async () => {
  if (form.value.symbol.length >= 4) {
    searching.value = true
    try {
      const result = await apiMethods.searchStock(form.value.symbol)
      if (result.status === 'success' && result.data?.name) {
        form.value.name = result.data.name
        stockHint.value = `找到: ${result.data.name}`
      }
    } catch (error) {
      // Ignore search errors
    } finally {
      searching.value = false
    }
  } else {
    stockHint.value = ''
  }
}

const handleSubmit = async () => {
  submitting.value = true

  try {
    await apiMethods.addHolding(form.value)
    emit('added')
    handleClose()
  } catch (error) {
    console.error('添加持仓失败:', error)
    // 这里可以使用更好的错误提示，暂时用alert
    alert('添加失败: ' + (error.message || '未知错误'))
  } finally {
    submitting.value = false
  }
}

// 监听显示状态，重置表单
watch(() => props.show, (newVal) => {
  if (newVal) {
    form.value = {
      symbol: '',
      name: '',
      cost_price: 0,
      position_size: 0,
      asset_type: 'stock'
    }
    stockHint.value = ''
  }
})
</script>

<style scoped>
/* Dialog Panel */
.dialog-panel {
  @apply bg-bg-card rounded-xl border border-border-subtle shadow-card-elevated;
  @apply overflow-hidden;
  position: relative;
}

/* Dialog glow effect */
.dialog-panel::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 1px;
  background: linear-gradient(90deg,
    transparent 0%,
    rgba(99, 102, 241, 0.5) 50%,
    transparent 100%);
}

/* Form Field */
.form-field {
  @apply space-y-2;
}

.form-label {
  @apply block text-sm font-medium text-text-secondary;
}

.form-hint {
  @apply text-xs text-text-tertiary mt-1;
}

/* Type Toggle Buttons */
.type-button {
  @apply flex-1 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200;
  @apply border border-border-subtle;
}

.type-button-inactive {
  @apply bg-bg-elevated text-text-tertiary hover:text-text-secondary hover:bg-white/5;
}

.type-button-active {
  @apply bg-primary/20 text-primary border-primary/50;
  @apply shadow-glow-primary;
}

/* Input focus glow animation */
@keyframes input-focus-glow {
  0% {
    box-shadow: 0 0 0 0 rgba(99, 102, 241, 0);
  }
  100% {
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
  }
}

.input-base:focus {
  animation: input-focus-glow 0.2s ease-out forwards;
}
</style>
