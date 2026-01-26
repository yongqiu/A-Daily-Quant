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
                <PencilIcon class="w-5 h-5 text-white" />
              </div>
              <div>
                <DialogTitle class="text-base font-semibold text-text-primary">编辑持仓</DialogTitle>
                <p class="text-xs text-text-tertiary mt-0.5">修改持仓成本或数量</p>
              </div>
            </div>
            <button @click="handleClose" class="btn-icon">
              <XMarkIcon class="w-5 h-5" />
            </button>
          </div>

          <!-- Form Content -->
          <form @submit.prevent="handleSubmit" class="p-6 space-y-5">
            <!-- 股票信息 (只读) -->
            <div class="form-field">
              <label class="form-label">股票</label>
              <div class="p-3 bg-bg-elevated rounded-lg border border-border-subtle flex justify-between items-center">
                  <span class="font-bold text-text-primary">{{ holdingToEdit?.name }}</span>
                  <span class="font-mono text-xs text-text-tertiary">{{ holdingToEdit?.symbol }}</span>
              </div>
            </div>

            <!-- 成本价和持仓数量 - 两列布局 -->
            <div class="grid grid-cols-2 gap-4">
              <div class="form-field">
                <label for="edit_cost_price" class="form-label">成本价</label>
                <div class="relative">
                  <input
                    id="edit_cost_price"
                    v-model.number="form.cost_price"
                    type="number"
                    step="0.01"
                    class="input-base pl-8"
                    placeholder="0.00"
                  />
                  <span class="absolute left-3 top-1/2 -translate-y-1/2 text-text-tertiary text-sm">¥</span>
                </div>
              </div>

              <div class="form-field">
                <label for="edit_position_size" class="form-label">持仓数量</label>
                <input
                  id="edit_position_size"
                  v-model.number="form.position_size"
                  type="number"
                  class="input-base"
                  placeholder="0"
                />
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
                :disabled="submitting"
                class="btn-primary flex-1 flex items-center justify-center gap-2"
              >
                <div v-if="submitting" class="spinner w-4 h-4 border-2 border-white/30 border-t-white"></div>
                <PencilIcon v-else class="w-4 h-4" />
                <span>{{ submitting ? '保存中...' : '保存修改' }}</span>
              </button>
            </div>
          </form>
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
import { PencilIcon, XMarkIcon } from '@heroicons/vue/24/outline'
import { apiMethods } from '@/utils/api'

const props = defineProps({
  show: {
    type: Boolean,
    default: false
  },
  holding: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['update:show', 'updated'])

const holdingToEdit = ref(null)
const form = ref({
  cost_price: 0,
  position_size: 0
})

const submitting = ref(false)

const handleClose = () => {
  emit('update:show', false)
}

const handleSubmit = async () => {
  if (!holdingToEdit.value) return

  submitting.value = true

  try {
    // 确保数据类型正确，避免空字符串导致的 400 错误
    const payload = {
      cost_price: typeof form.value.cost_price === 'number' ? form.value.cost_price : Number(form.value.cost_price) || 0,
      position_size: typeof form.value.position_size === 'number' ? form.value.position_size : Number(form.value.position_size) || 0
    }

    await apiMethods.updateHolding(holdingToEdit.value.symbol, payload)
    emit('updated')
    handleClose()
  } catch (error) {
    console.error('更新持仓失败:', error)
    alert('更新失败: ' + (error.message || '未知错误'))
  } finally {
    submitting.value = false
  }
}

// 监听 holding 变化，同步到 form
watch(() => props.holding, (newVal) => {
  if (newVal) {
    holdingToEdit.value = newVal
    form.value = {
      cost_price: newVal.cost_price || 0,
      position_size: newVal.position_size || 0
    }
  }
}, { immediate: true })
</script>

<style scoped>
/* Copied styles from AddHoldingModal for consistency */
.dialog-panel {
  @apply bg-bg-card rounded-xl border border-border-subtle shadow-card-elevated;
  @apply overflow-hidden;
  position: relative;
}

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

.form-field {
  @apply space-y-2;
}

.form-label {
  @apply block text-sm font-medium text-text-secondary;
}

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