<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from './api'

const config = ref<any>(null)
onMounted(async () => {
  try { config.value = await api.config() } catch { /* status is optional */ }
})
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <RouterLink to="/shelf/movie" class="brand">
        <span class="brand-mark">DS</span>
        <span><strong>Decision Shelf</strong><small>把空闲时间还给真正想做的事</small></span>
      </RouterLink>
      <nav>
        <RouterLink v-for="item in [{k:'movie',v:'电影'},{k:'book',v:'书籍'},{k:'album',v:'专辑'},{k:'game',v:'游戏'}]" :key="item.k" :to="`/shelf/${item.k}`">{{ item.v }}</RouterLink>
        <RouterLink to="/add">加入内容</RouterLink>
        <RouterLink to="/decide" class="decision-link">帮我决定</RouterLink>
        <RouterLink to="/history">历史</RouterLink>
      </nav>
    </header>
    <div v-if="config && !config.deepseek.available" class="status-banner">
      DeepSeek 尚未配置：书架功能可用，AI 探索暂不可用。
    </div>
    <main><RouterView /></main>
  </div>
</template>
