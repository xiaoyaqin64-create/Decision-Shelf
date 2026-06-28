<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import DraftForm from '../components/DraftForm.vue'
import type { CardDraft, Category, DecisionResponse, ExplorationSuggestion, Taxonomy } from '../types'

const loading = ref(false)
const error = ref('')
const result = ref<DecisionResponse | null>(null)
const editing = ref<ExplorationSuggestion | null>(null)
const editedDraft = ref<CardDraft | null>(null)
const categories = ref<Category[]>(['movie', 'book', 'album', 'game'])
const genrePreferences = ref<string[]>([])
const moods = ref<string[]>([])
const customGenre = ref('')
const taxonomy = ref<Taxonomy>({genres:{movie:[],book:[],album:[],game:[]},scenes:[]})
const form = ref({ available_minutes: 120, energy_level: 'medium', scope: 'shelf_first', free_text: '' })
const categoryOptions = [{k:'movie',v:'电影'},{k:'book',v:'书籍'},{k:'album',v:'专辑'},{k:'game',v:'游戏'}]
const genreGroups = computed(()=>categories.value.map(category=>({category,label:categoryOptions.find(i=>i.k===category)?.v,tags:taxonomy.value.genres?.[category] ?? []})))

function toggle<T>(array: T[], value: T) { const i = array.indexOf(value); i >= 0 ? array.splice(i, 1) : array.push(value) }

async function decide() {
  if (!categories.value.length) { error.value = '至少选择一个内容类型。'; return }
  loading.value = true; error.value = ''; result.value = null
  try {
    const custom = customGenre.value.split(/[,，、]/).map(v=>v.trim()).filter(Boolean)
    result.value = await api.decide({ ...form.value, categories: categories.value, genre_preferences: [...genrePreferences.value,...custom], moods: moods.value })
  } catch (e) { error.value = (e as Error).message } finally { loading.value = false }
}

async function shelfAction(action: string) {
  if (!result.value?.shelf_recommendation) return
  const extra: Record<string, unknown> = { session_id: result.value.session_id }
  if (action === 'complete') { const rating = window.prompt('评分 1～5'); const review = window.prompt('感想'); if (rating) extra.rating = Number(rating); if (review) extra.review = review }
  await api.action(result.value.shelf_recommendation.card_id, action, extra)
  await decide()
}

function openEdit(item: ExplorationSuggestion) { editing.value = item; editedDraft.value = JSON.parse(JSON.stringify(item.draft)) }

async function resolve(item: ExplorationSuggestion, action: 'add'|'start'|'complete'|'dismiss', draft?: CardDraft) {
  try {
    await api.resolveExploration(item.id, { action, draft, confirmed: item.verified || Boolean(draft) })
    item.resolution = action === 'dismiss' ? 'dismissed' : action === 'start' ? 'started' : 'added'
    editing.value = null; editedDraft.value = null
  } catch (e) { error.value = (e as Error).message }
}
onMounted(async()=>{try{const loaded=await api.taxonomy();if(loaded?.genres&&Array.isArray(loaded.scenes))taxonomy.value=loaded}catch{/* API 向后兼容 */}})
</script>

<template>
  <section class="page narrow decision-page">
    <div class="hero"><div><p class="eyebrow">DECIDE NOW</p><h1>现在，做什么最合适？</h1><p>给出此刻的边界。书架与 AI 会把选择缩到你真正能开始的那一个。</p></div></div>
    <form class="decision-form panel" @submit.prevent="decide">
      <fieldset><legend><span>01</span> 我现在有多少时间？</legend><div class="choice-row"><button v-for="item in [{m:30,t:'30 分钟'},{m:60,t:'1 小时'},{m:120,t:'2 小时'},{m:240,t:'半天'},{m:480,t:'一整天'}]" :key="item.m" type="button" :class="{selected:form.available_minutes===item.m}" @click="form.available_minutes=item.m">{{ item.t }}</button></div></fieldset>
      <fieldset><legend><span>02</span> 我现在的精力？</legend><div class="choice-row"><button type="button" :class="{selected:form.energy_level==='low'}" @click="form.energy_level='low'">很累，只想轻松</button><button type="button" :class="{selected:form.energy_level==='medium'}" @click="form.energy_level='medium'">还行，可以投入</button><button type="button" :class="{selected:form.energy_level==='high'}" @click="form.energy_level='high'">清醒，想挑战一下</button></div></fieldset>
      <fieldset><legend><span>03</span> 内容类型</legend><div class="choice-row"><button v-for="item in categoryOptions" :key="item.k" type="button" :class="{selected:categories.includes(item.k as Category)}" @click="toggle(categories,item.k as Category)">{{ item.v }}</button></div></fieldset>
      <fieldset><legend><span>04</span> 推荐范围</legend><div class="scope-grid"><label :class="{selected:form.scope==='shelf_only'}"><input v-model="form.scope" type="radio" value="shelf_only" /><strong>只从书架里选</strong><small>只处理已经收藏的内容</small></label><label :class="{selected:form.scope==='shelf_first'}"><input v-model="form.scope" type="radio" value="shelf_first" /><strong>优先书架，不够时探索</strong><small>候选少或匹配低时，让 AI 补充</small></label><label :class="{selected:form.scope==='free'}"><input v-model="form.scope" type="radio" value="free" /><strong>完全自由推荐</strong><small>探索书架之外的新内容</small></label></div></fieldset>
      <fieldset><legend><span>05</span> 想体验什么类型？</legend><div v-for="group in genreGroups" :key="group.category" class="taxonomy-group"><small>{{ group.label }}</small><div class="choice-row"><button v-for="item in group.tags" :key="`${group.category}-${item}`" type="button" :class="{selected:genrePreferences.includes(item)}" @click="toggle(genrePreferences,item)">{{ item }}</button></div></div><input v-model="customGenre" placeholder="也可输入自定义标签，用顿号分隔" /></fieldset>
      <fieldset><legend><span>06</span> 此刻想获得什么？</legend><div class="choice-row"><button v-for="item in taxonomy.scenes" :key="item" type="button" :class="{selected:moods.includes(item)}" @click="toggle(moods,item)">{{ item }}</button></div><textarea v-model="form.free_text" rows="3" placeholder="也可以描述得更具体：今晚有点累，但想找些有制作灵感的东西……" /></fieldset>
      <button class="decision-submit" :disabled="loading">{{ loading ? '正在理解此刻…' : '给我一个决定' }} →</button>
    </form>
    <p v-if="error" class="error-box">{{ error }}</p>

    <section v-if="result" class="decision-results">
      <div v-if="result.shelf_recommendation" class="recommendation primary-recommendation"><p class="eyebrow">来自我的书架</p><div class="score-ring">{{ Math.round(result.shelf_recommendation.fit_score) }}</div><h2>{{ result.shelf_recommendation.title }}</h2><p>{{ result.shelf_recommendation.explanation }}</p><small>综合 {{ result.shelf_recommendation.total_score }} 分 · 当前有 {{ result.eligible_count }} 张可选</small><div class="recommend-actions"><button @click="shelfAction('start')">现在开始</button><button class="quiet" @click="shelfAction('not-today')">今天不想</button><button class="quiet" @click="shelfAction('skip')">换下次</button></div></div>
      <div v-if="result.fallback_reason" class="explore-intro"><p class="eyebrow">书架之外</p><h2>{{ result.fallback_reason === 'low_count' ? '书架候选有点少，看看新的可能' : '现有内容和此刻不够匹配' }}</h2></div>
      <div v-if="result.exploration_error" class="warning-box">AI 探索暂不可用：{{ result.exploration_error }}</div>
      <p v-if="result.exploration_suggestions.length&&result.exploration_suggestions[0].fit_score<60" class="warning-box">当前没有高度匹配的探索内容，以下仍是完整候选集中相对最合适的结果。</p>
      <div class="explore-grid"><article v-for="item in result.exploration_suggestions" :key="item.id" class="explore-card" :class="{best:item.is_best}"><img v-if="item.draft.image_url" :src="item.draft.image_url" /><div><p class="eyebrow">{{ item.is_best?'最佳探索推荐':(item.verified ? `已由 ${item.draft.source} 验证` : 'AI 建议 · 未验证') }}</p><span class="fit-badge">匹配 {{ Math.round(item.fit_score) }}</span><h3>{{ item.draft.title }}</h3><p>{{ item.reason }}</p><div class="tag-row"><span v-for="tag in item.draft.tags.slice(0,3)" :key="tag">{{ tag }}</span></div><div v-if="item.resolution==='pending'" class="card-actions"><button @click="openEdit(item)">确认 / 编辑</button><button v-if="item.verified" class="quiet" @click="resolve(item,'add')">加入书架</button><button v-if="item.verified" class="quiet" @click="resolve(item,'complete')">已经看过 / 完成</button><button class="text-button" @click="resolve(item,'dismiss')">暂时忽略</button></div><p v-else class="resolved">已处理：{{ item.resolution }}</p></div></article></div>
      <p v-for="warning in result.warnings" :key="warning" class="subtle-warning">{{ warning }}</p>
    </section>
  </section>

  <div v-if="editing && editedDraft" class="modal-backdrop" @click.self="editing=null"><section class="modal panel"><div class="modal-head"><h2>确认《{{ editing.draft.title }}》</h2><button class="icon" @click="editing=null">×</button></div><p v-if="!editing.verified" class="warning-box">游戏尚未接入外部验证，请确认标题和时长后再继续。</p><DraftForm v-model="editedDraft" /><div class="modal-actions"><button class="quiet" @click="editing=null">取消</button><button class="quiet" @click="resolve(editing,'add',editedDraft)">加入书架</button><button class="quiet" @click="resolve(editing,'complete',editedDraft)">已经完成</button><button @click="resolve(editing,'start',editedDraft)">立即开始</button></div></section></div>
</template>
