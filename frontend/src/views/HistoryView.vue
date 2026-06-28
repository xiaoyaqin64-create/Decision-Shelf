<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

const history = ref<any[]>([])
const preferences = ref<any[]>([])
const loading = ref(true)
const error = ref('')

async function load() {
  loading.value = true
  try { history.value = (await api.history()).items; preferences.value = (await api.preferences()).items } catch (e) { error.value = (e as Error).message } finally { loading.value = false }
}
async function reset() { if (window.confirm('确定重置所有长期偏好权重？历史不会删除。')) { await api.resetPreferences(); await load() } }
const scopeLabel: Record<string,string> = { shelf_only:'只从书架', shelf_first:'书架优先', free:'自由探索' }
onMounted(load)
</script>

<template>
  <section class="page">
    <div class="hero compact"><div><p class="eyebrow">MEMORY</p><h1>决策历史与偏好</h1><p>系统如何逐渐理解你，应该始终看得见，也随时可以重置。</p></div></div>
    <p v-if="error" class="error-box">{{ error }}</p><p v-if="loading" class="empty-state">正在读取历史…</p>
    <div v-else class="history-layout">
      <section><h2>最近的决定</h2><div v-if="!history.length" class="empty-shelf">还没有历史记录。</div><article v-for="item in history" :key="item.id" class="history-item panel"><div class="history-time"><strong>#{{ item.id }}</strong><span>{{ new Date(item.created_at).toLocaleString('zh-CN') }}</span></div><p class="eyebrow">{{ scopeLabel[item.decision_scope] || '书架决策' }} · {{ item.available_minutes }} 分钟 · {{ item.energy_level }} 精力</p><h3>{{ item.primary_title || (item.exploration_suggestions?.length ? '探索新内容' : '没有符合条件的内容') }}</h3><p v-if="item.free_text">“{{ item.free_text }}”</p><div v-if="item.exploration_suggestions?.length" class="history-explore"><span v-for="suggestion in item.exploration_suggestions" :key="suggestion.id">{{ suggestion.draft.title }} · {{ suggestion.resolution }}</span></div><div v-for="action in item.interactions" :key="action.id" class="history-action">{{ action.action }} · {{ action.card_title }} <template v-if="action.rating">· {{ action.rating }} 星</template><small v-if="action.review">{{ action.review }}</small></div></article></section>
      <aside class="preference-panel panel"><div class="section-heading"><h2>长期偏好</h2><button class="text-button" @click="reset">重置</button></div><p>来自开始、完成和评分的轻量权重。</p><div v-if="preferences.length" class="preference-list"><div v-for="item in preferences" :key="`${item.key_type}-${item.key}`"><span>{{ item.key }}</span><b :class="{negative:item.weight<0}">{{ item.weight>0?'+':'' }}{{ item.weight.toFixed(2) }}</b></div></div><p v-else>还没有足够反馈。</p></aside>
    </div>
  </section>
</template>
