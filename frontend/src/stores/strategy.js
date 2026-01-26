import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiMethods } from '@/utils/api'

export const useStrategyStore = defineStore('strategy', () => {
  // 状态
  const strategies = ref([])
  const selectedStrategy = ref(null)
  const loading = ref(false)

  // 方法
  const fetchStrategies = async () => {
    loading.value = true
    try {
      const data = await apiMethods.getStrategies()
      strategies.value = data
      return data
    } catch (error) {
      console.error('获取策略列表失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  const fetchStrategy = async (slug) => {
    loading.value = true
    try {
      const data = await apiMethods.getStrategy(slug)
      selectedStrategy.value = data
      return data
    } catch (error) {
      console.error('获取策略详情失败:', error)
      throw error
    } finally {
      loading.value = false
    }
  }

  const selectStrategy = (strategy) => {
    selectedStrategy.value = strategy
  }

  const updateTemplate = async (id, template) => {
    try {
      await apiMethods.updateStrategyTemplate(id, template)
      if (selectedStrategy.value && selectedStrategy.value.id === id) {
        selectedStrategy.value.template_content = template
      }
    } catch (error) {
      console.error('更新模板失败:', error)
      throw error
    }
  }

  const updateParam = async (id, key, value) => {
    try {
      await apiMethods.updateStrategyParam(id, key, value)
      if (selectedStrategy.value && selectedStrategy.value.id === id) {
        if (selectedStrategy.value.params) {
          selectedStrategy.value.params[key] = value
        }
      }
    } catch (error) {
      console.error('更新参数失败:', error)
      throw error
    }
  }

  return {
    strategies,
    selectedStrategy,
    loading,
    fetchStrategies,
    fetchStrategy,
    selectStrategy,
    updateTemplate,
    updateParam
  }
})
