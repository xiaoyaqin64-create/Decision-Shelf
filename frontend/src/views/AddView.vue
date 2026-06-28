<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { api } from '../api'
import DraftForm from '../components/DraftForm.vue'
import type { CardDraft, Category, MetadataCandidate } from '../types'

const category = ref<Category>('movie')
const query = ref('')
const results = ref<MetadataCandidate[]>([])
const draft = ref<CardDraft | null>(null)
const loading = ref(false)
const message = ref('')
const error = ref('')
const config = ref<any>(null)
let timer: number | undefined

function blankDraft(cat: Category): CardDraft {
  return { category: cat, title: query.value, source: 'manual', external_id: null, description: '', image_url: null, duration_minutes: null, min_session_minutes: cat === 'book' ? 25 : null, tags: [], energy_level: 'medium', mood_fit: [], notes: '', priority: 3, extension: {} }
}

watch([query, category], () => {
  window.clearTimeout(timer)
  results.value = []
  error.value = ''
  if (category.value === 'game' || query.value.trim().length < 2) return
  timer = window.setTimeout(search, 350)
})

watch(category, (value) => { draft.value = null; if (value === 'game') draft.value = blankDraft(value) })

async function search() {
  loading.value = true
  try { results.value = (await api.metadataSearch(category.value, query.value.trim())).items } catch (e) { error.value = (e as Error).message } finally { loading.value = false }
}

async function choose(item: MetadataCandidate) {
  loading.value = true
  try { draft.value = await api.metadataDraft(category.value, item.external_id); results.value = [] } catch (e) { error.value = (e as Error).message } finally { loading.value = false }
}

async function enrich() {
  if (!draft.value) return
  loading.value = true
  try {
    const response = await api.enrich(draft.value)
    draft.value = response.draft
    message.value = response.warning ? `已保留原字段：${response.warning}` : 'DeepSeek 已补充适合场景与语义标签。'
  } catch (e) { error.value = (e as Error).message } finally { loading.value = false }
}

async function save() {
  if (!draft.value) return
  loading.value = true
  try { const card = await api.createCard(draft.value); message.value = `《${card.title}》已加入书架。`; draft.value = null; query.value = '' } catch (e) { error.value = (e as Error).message } finally { loading.value = false }
}

function manual() { draft.value = blankDraft(category.value); results.value = [] }
onMounted(async () => { try { config.value = await api.config() } catch { /* optional */ } })
</script>

<template>
  <section class="page narrow">
    <div class="hero"><div><p class="eyebrow">ADD TO SHELF</p><h1>把想看的，轻松放进来</h1><p>只输入标题，外部数据源负责事实信息，DeepSeek 负责“什么时候适合它”。</p></div></div>
    <div class="step-card panel">
      <div class="step-number">1</div><div class="step-content"><h2>选择类型并搜索</h2>
        <div class="segmented"><button v-for="item in [{k:'movie',v:'电影'},{k:'book',v:'书籍'},{k:'album',v:'专辑'},{k:'game',v:'游戏'}]" :key="item.k" :class="{active:category===item.k}" @click="category=item.k as Category">{{ item.v }}</button></div>
        <div class="search-box"><input v-model="query" :placeholder="category === 'game' ? '输入游戏标题后手动建卡' : '输入至少两个字符开始搜索'" /><span v-if="loading">搜索中…</span></div>
        <p v-if="config && category !== 'game' && !config.metadata[category]?.available" class="warning-box">{{ config.metadata[category]?.reason }}。你仍可手动建卡。</p>
        <button class="text-button" @click="manual">找不到？直接手动填写</button>
      </div>
    </div>

    <div v-if="results.length" class="results panel"><h2>选择正确的条目</h2><button v-for="item in results" :key="item.external_id" class="result-row" @click="choose(item)"><img v-if="item.image_url" :src="item.image_url" /><span class="mini-cover" v-else>无图</span><span><strong>{{ item.title }}</strong><small>{{ item.subtitle }}<template v-if="item.year"> · {{ item.year }}</template></small></span><b>选择 →</b></button></div>

    <div v-if="draft" class="step-card panel"><div class="step-number">2</div><div class="step-content"><div class="section-heading"><h2>确认并编辑卡片</h2><span v-if="draft.source !== 'manual'" class="verified">已匹配 {{ draft.source }}</span></div><DraftForm v-model="draft" /><div class="form-actions"><button class="quiet" :disabled="loading" @click="enrich">✨ AI 补充场景标签</button><button :disabled="loading || !draft.title" @click="save">保存到书架</button></div></div></div>
    <p v-if="message" class="success-box">{{ message }}</p><p v-if="error" class="error-box">{{ error }}</p>
  </section>
</template>
