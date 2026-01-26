import { onMounted, onUnmounted, watch, nextTick, ref } from 'vue'
import * as echarts from 'echarts'

export function useKlineChart(containerRef, selectedSymbol) {
  const chart = ref(null)
  const loading = ref(false)

  const initChart = () => {
    if (!containerRef.value) return

    // Prevent duplicate init
    if (chart.value) return

    chart.value = echarts.init(containerRef.value)

    window.addEventListener('resize', handleResize)
  }

  const handleResize = () => {
    if (chart.value) {
      chart.value.resize()
    }
  }

  const renderChart = (data) => {
    // Try to init if not exists (handling v-if case)
    if (!chart.value) initChart()

    if (!chart.value) return

    const option = {
      backgroundColor: 'transparent',
      animation: false,
      legend: {
        data: ['K线', '成交量'],
        textStyle: { color: '#A0B4C8' },
        top: 0
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross' },
        backgroundColor: 'rgba(13, 21, 38, 0.95)',
        borderColor: 'rgba(255, 255, 255, 0.1)',
        textStyle: { color: '#F0F4F8' }
      },
      grid: [
        { left: '8%', right: '8%', top: '15%', height: '55%' },
        { left: '8%', right: '8%', top: '75%', height: '15%' }
      ],
      xAxis: [
        {
          type: 'category',
          data: data.dates,
          scale: true,
          boundaryGap: false,
          axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
          splitLine: { show: false },
          min: 'dataMin',
          max: 'dataMax'
        },
        {
          type: 'category',
          gridIndex: 1,
          data: data.dates,
          scale: true,
          boundaryGap: false,
          axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
          axisTick: { show: false },
          splitLine: { show: false },
          axisLabel: { show: false },
          min: 'dataMin',
          max: 'dataMax'
        }
      ],
      yAxis: [
        {
          scale: true,
          splitArea: { show: false },
          axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
          splitLine: { lineStyle: { color: 'rgba(255,255,255,0.05)' } }
        },
        {
          scale: true,
          gridIndex: 1,
          splitNumber: 2,
          axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
          axisTick: { show: false },
          splitLine: { show: false },
          axisLabel: { show: false }
        }
      ],
      dataZoom: [
        { type: 'inside', xAxisIndex: [0, 1], start: 50, end: 100 },
        { show: false, xAxisIndex: [0, 1], type: 'slider', top: '85%', start: 50, end: 100 }
      ],
      series: [
        {
          name: 'K线',
          type: 'candlestick',
          data: data.values,
          itemStyle: {
            color: '#26A69A',
            color0: '#EF5350',
            borderColor: '#26A69A',
            borderColor0: '#EF5350'
          }
        },
        {
          name: '成交量',
          type: 'bar',
          xAxisIndex: 1,
          yAxisIndex: 1,
          data: data.volumes,
          itemStyle: {
            color: (params) => {
              const idx = params.dataIndex
              if (idx === 0) return 'rgba(38, 166, 154, 0.5)'
              return data.values[idx][1] >= data.values[idx][0]
                ? 'rgba(38, 166, 154, 0.5)'
                : 'rgba(239, 83, 80, 0.5)'
            }
          }
        }
      ]
    }

    chart.value.setOption(option, true)
  }

  const loadKlineData = async (symbol) => {
    if (!symbol) return

    loading.value = true
    try {
      const response = await fetch(`/api/kline/${symbol}`)
      const data = await response.json()

      if (data.status === 'success') {
        await nextTick()
        renderChart(data)
      }
    } catch (error) {
      console.error('加载K线数据失败:', error)
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    initChart()
  })

  onUnmounted(() => {
    window.removeEventListener('resize', handleResize)
    if (chart.value) {
      chart.value.dispose()
    }
  })

  watch(selectedSymbol, (newSymbol) => {
    if (newSymbol) {
      loadKlineData(newSymbol)
    }
  }, { immediate: true })

  return {
    chart,
    loading,
    loadKlineData,
    renderChart
  }
}
