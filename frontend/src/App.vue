<template>
  <div class="layout-shell">
    <!-- 左侧导航栏 -->
    <AppSidebar />

    <!-- 主内容区 -->
    <main class="main-content">
      <!-- 路由视图 (Dashboard/Screener etc) -->
      <router-view v-slot="{ Component }">
          <component :is="Component" />
      </router-view>
    </main>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useMarketStore } from '@/stores/market'
import AppSidebar from '@/components/AppSidebar.vue'

const marketStore = useMarketStore()

onMounted(() => {
  marketStore.fetchStatus()
})
</script>
