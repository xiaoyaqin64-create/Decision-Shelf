<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import CardTile from '../components/CardTile.vue'
import CompletedCollection from '../components/CompletedCollection.vue'
import CompletionDialog from '../components/CompletionDialog.vue'
import DraftForm from '../components/DraftForm.vue'
import type { Card, CardDraft, Category, TimeEntry } from '../types'
import { calculateShelfCapacity, cardSortTime, chunkItemsByWidth } from '../shelfLayout'

const route = useRoute()
const router = useRouter()
const categories: Category[] = ['movie', 'book', 'album', 'game']
const labels: Record<Category, string> = { movie: '电影', book: '书籍', album: '专辑', game: '游戏' }
const statusDefs = [
  { key: 'in_progress', label: '进行中', hint: '正在推进' },
  { key: 'todo', label: '待体验', hint: '等待合适的时刻' },
  { key: 'completed', label: '已完成', hint: '个人体验档案' },
] as const

const cards = ref<Card[]>([])
const loading = ref(true)
const error = ref('')
const notice = ref('')
const query = ref('')
const selected = ref<Card | null>(null)
const draft = ref<CardDraft | null>(null)
const showTrash = ref(false)
const enriching = ref(false)
const saving = ref(false)
const showCompletion = ref(false)
const completionSaving = ref(false)
const completionDate = ref('')
const completionRating = ref<number | string | null>(null)
const completionReview = ref('')
const timeEntries = ref<TimeEntry[]>([])
const totalMinutes = ref(0)
const timeMinutes = ref<number | null>(null)
const timeNote = ref('')
const expandedCardId = ref<string | null>(null)
const touchMode = ref(false)
const layoutRoot = ref<HTMLElement | null>(null)
const layoutWidth = ref(1000)
const capacity = ref(12)
const attemptedColors = new Set<string>()
let resizeObserver: ResizeObserver | undefined
let layerObserver: IntersectionObserver | undefined
let touchQuery: MediaQueryList | undefined

const category = computed<Category>(() => categories.includes(route.params.category as Category) ? route.params.category as Category : 'movie')
const categoryCards = computed(() => cards.value.filter(card => card.category === category.value))
const visibleCards = computed(() => categoryCards.value.filter(card => {
  const term = query.value.trim().toLowerCase()
  return !term || card.title.toLowerCase().includes(term) || card.tags.some(tag => tag.toLowerCase().includes(term))
}))
const trash = computed(() => categoryCards.value.filter(card => card.status === 'removed'))
const sections = computed(() => statusDefs.map(def => {
  const items = visibleCards.value
    .filter(card => card.status === def.key)
    .sort((a, b) => def.key === 'completed'
      ? cardSortTime(b, def.key).localeCompare(cardSortTime(a, def.key)) || a.id.localeCompare(b.id)
      : cardSortTime(a, def.key).localeCompare(cardSortTime(b, def.key)) || a.id.localeCompare(b.id))
  return { ...def, items, layers: chunkItemsByWidth(items, layoutWidth.value) }
}))

function recalc() {
  layoutWidth.value = layoutRoot.value?.clientWidth || 1000
  capacity.value = calculateShelfCapacity(layoutWidth.value)
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    cards.value = (await api.cards(`?category=${category.value}`)).items
    await nextTick()
    setupLayerObserver()
  } catch (reason) {
    error.value = (reason as Error).message
  } finally {
    loading.value = false
    await nextTick()
    setupLayerObserver()
  }
}

async function resolveColors(ids: string[]) {
  const pending = ids.filter(id => {
    const card = cards.value.find(item => item.id === id)
    return card && card.theme_color_source === 'pending' && !attemptedColors.has(id)
  })
  for (let index = 0; index < pending.length; index += 20) {
    const batch = pending.slice(index, index + 20)
    batch.forEach(id => attemptedColors.add(id))
    try {
      const result = await api.resolveThemeColors(batch)
      for (const item of result.items) {
        const card = cards.value.find(entry => entry.id === item.id)
        if (card) {
          card.theme_color = item.theme_color
          card.theme_color_source = item.source as Card['theme_color_source']
        }
      }
    } catch {
      // 分类备用色已经生效，取色失败不会影响书架。
    }
  }
}

function setupLayerObserver() {
  layerObserver?.disconnect()
  if (typeof IntersectionObserver === 'undefined') return
  layerObserver = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue
      const ids = (entry.target as HTMLElement).dataset.cardIds?.split(',').filter(Boolean) || []
      void resolveColors(ids)
    }
  }, { rootMargin: '180px' })
  document.querySelectorAll<HTMLElement>('.shelf-layer').forEach(element => layerObserver?.observe(element))
}

async function open(card: Card) {
  expandedCardId.value = null
  selected.value = card
  draft.value = { ...card, tags: [...card.tags], mood_fit: [...card.mood_fit], extension: { ...card.extension } }
  notice.value = ''
  error.value = ''
  completionDate.value = card.completed_at?.slice(0, 10) || ''
  completionRating.value = card.rating
  completionReview.value = card.review || ''
  if (['book', 'game'].includes(card.category)) {
    const data = await api.timeEntries(card.id)
    timeEntries.value = data.items
    totalMinutes.value = data.total_minutes
  }
}

async function expand(card: Card) {
  expandedCardId.value = card.id
  await nextTick()
  document.querySelector<HTMLElement>(`[data-card-id="${card.id}"]`)
    ?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest', inline: 'nearest' })
}

function collapseExpanded(event: Event) {
  const target = event.target as HTMLElement
  if (!target.closest('.book-spine')) expandedCardId.value = null
}

function handleAndroidBack(event: Event) {
  const detail = (event as CustomEvent<{ handled: boolean }>).detail
  if (showCompletion.value) {
    showCompletion.value = false
    detail.handled = true
  } else if (selected.value) {
    close()
    detail.handled = true
  } else if (expandedCardId.value) {
    expandedCardId.value = null
    detail.handled = true
  }
}

function close() {
  selected.value = null
  draft.value = null
  timeEntries.value = []
  notice.value = ''
  showCompletion.value = false
}

function formatCompletionDate(value: string | null) {
  if (!value) return '日期未记录'
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value)
  return Number.isNaN(date.getTime()) ? value.slice(0, 10) : date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
}

function descriptionProvenance(card: Card) {
  const provenance = card.extension?.description_provenance as Record<string, unknown> | undefined
  if (!provenance) return ''
  if (provenance.mode === 'external') return `外部来源 · ${provenance.source}`
  if (provenance.mode === 'evidence') return 'AI 辅助 · 有依据'
  if (provenance.mode === 'unverified') return 'AI 辅助 · 未核验'
  return ''
}

async function save() {
  if (!selected.value || !draft.value || saving.value) return
  const cardId = selected.value.id
  const scrollY = window.scrollY
  saving.value = true
  error.value = ''
  try {
    const saved = await api.updateCard(cardId, { ...draft.value, status: selected.value.status })
    const index = cards.value.findIndex(card => card.id === cardId)
    if (index >= 0) cards.value.splice(index, 1, saved)
    close()
    await nextTick()
    window.requestAnimationFrame(() => window.requestAnimationFrame(() => {
      window.scrollTo({ top: scrollY, left: 0, behavior: 'auto' })
    }))
  } catch (reason) {
    error.value = (reason as Error).message
  } finally {
    saving.value = false
  }
}

async function saveCompleted() {
  if (!selected.value || !draft.value || saving.value || !completionDate.value) return
  saving.value = true
  error.value = ''
  try {
    const score = completionRating.value === '' || completionRating.value === null ? null : Number(completionRating.value)
    await api.updateCompletion(selected.value.id, {
      completed_at: completionDate.value,
      rating: score,
      review: completionReview.value.trim() || null,
    })
    draft.value.extension = { ...draft.value.extension }
    delete draft.value.extension.completed_at_inferred
    const saved = await api.updateCard(selected.value.id, { ...draft.value, status: 'completed' })
    const index = cards.value.findIndex(card => card.id === saved.id)
    if (index >= 0) cards.value.splice(index, 1, saved)
    close()
  } catch (reason) {
    error.value = (reason as Error).message
  } finally {
    saving.value = false
  }
}

async function enrich() {
  if (!selected.value) return
  enriching.value = true
  error.value = ''
  try {
    const result = await api.enrichCard(selected.value.id)
    draft.value = result.draft
    notice.value = result.warning
      ? `${result.description_source ? '简介已补充；' : ''}AI 标签补全未完成：${result.warning}`
      : `${result.description_source?.startsWith('external:') ? '已从外部来源补充简介' : result.description_source === 'deepseek:evidence' ? 'AI 已生成有依据的简介草稿' : result.description_source === 'deepseek:unverified' ? 'AI 已生成未核验的保守简介草稿' : 'AI 已生成补全草稿'}${result.retried ? '（纠正重试后成功）' : ''}，检查并保存后生效。`
  } catch (reason) {
    error.value = (reason as Error).message
  } finally {
    enriching.value = false
  }
}

async function action(name: string) {
  if (!selected.value) return
  if (name === 'complete') {
    showCompletion.value = true
    return
  }
  const extra: Record<string, unknown> = {}
  selected.value = await api.action(selected.value.id, name, extra)
  await load()
}

async function complete(payload: { completed_at: string; rating: number | null; review: string | null; final_minutes?: number }) {
  if (!selected.value) return
  completionSaving.value = true
  error.value = ''
  try {
    await api.action(selected.value.id, 'complete', payload)
    showCompletion.value = false
    close()
    await load()
  } catch (reason) {
    error.value = (reason as Error).message
  } finally {
    completionSaving.value = false
  }
}

async function recycle() {
  if (!selected.value) return
  await api.recycleCard(selected.value.id)
  await load()
  close()
}

async function restore(card: Card) {
  await api.restoreCard(card.id)
  await load()
}

async function permanent(card: Card) {
  if (confirm(`永久删除《${card.title}》？此操作不可撤销。`)) {
    await api.permanentDeleteCard(card.id)
    await load()
  }
}

async function addTime() {
  if (!selected.value || !timeMinutes.value) return
  const result = await api.addTimeEntry(selected.value.id, timeMinutes.value, timeNote.value)
  timeEntries.value = [result.item, ...timeEntries.value]
  totalMinutes.value = result.total_minutes
  timeMinutes.value = null
  timeNote.value = ''
}

async function removeTime(id: number) {
  await api.deleteTimeEntry(id)
  if (selected.value) {
    const result = await api.timeEntries(selected.value.id)
    timeEntries.value = result.items
    totalMinutes.value = result.total_minutes
  }
}

watch(() => route.params.category, () => {
  attemptedColors.clear()
  showTrash.value = false
  query.value = ''
  expandedCardId.value = null
  void load()
}, { immediate: true })
watch([layoutWidth, query], async () => { await nextTick(); setupLayerObserver() })
onMounted(() => {
  resizeObserver = new ResizeObserver(recalc)
  if (layoutRoot.value) resizeObserver.observe(layoutRoot.value)
  recalc()
  if (typeof window.matchMedia === 'function') {
    touchQuery = window.matchMedia('(hover: none), (pointer: coarse)')
    touchMode.value = Boolean(touchQuery.matches)
  }
  window.addEventListener('decision-shelf-back', handleAndroidBack)
})
onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  layerObserver?.disconnect()
  window.removeEventListener('decision-shelf-back', handleAndroidBack)
})
</script>

<template>
  <section ref="layoutRoot" class="page category-library" @click="collapseExpanded">
    <header class="library-heading">
      <div><p class="eyebrow">{{ category.toUpperCase() }} LIBRARY</p><h1>{{ labels[category] }}书架</h1><p>每一层从左到右生长。停在书脊上，让它为你展开。</p></div>
      <RouterLink to="/add" class="button primary">＋ 加入新内容</RouterLink>
    </header>
    <nav class="mobile-category-tabs" aria-label="书架分类">
      <RouterLink v-for="item in categories" :key="item" :to="`/shelf/${item}`">{{ labels[item] }}</RouterLink>
    </nav>
    <div class="library-toolbar panel">
      <input v-model="query" placeholder="搜索当前书架的标题或标签" />
      <span>{{ visibleCards.filter(card=>card.status!=='removed').length }} 张内容 · 每层约 {{ capacity }} 张</span>
      <button class="quiet" @click="showTrash=!showTrash">回收站 {{ trash.length }}</button>
    </div>
    <p v-if="error && !selected" class="error-box">{{ error }}</p>
    <p v-if="loading" class="empty-state">正在整理{{ labels[category] }}书架…</p>
    <main v-else class="status-shelves">
      <section v-for="section in sections" :key="section.key" class="status-shelf" :class="`shelf-${section.key}`">
        <div class="status-heading"><div><p>{{ section.hint }}</p><h2>{{ section.label }}</h2></div><span>{{ section.items.length }} 张<template v-if="section.key !== 'completed' || category === 'book'"> · {{ section.layers.length }} 层</template></span></div>
        <CompletedCollection v-if="section.key === 'completed' && category !== 'book' && section.items.length" :category="category" :cards="section.items" @open="open" />
        <div v-else-if="section.layers.length" class="shelf-layers">
          <div v-for="(layer,layerIndex) in section.layers" :key="`${section.key}-${layerIndex}-${layoutWidth}`" class="shelf-layer" :data-card-ids="layer.map(card=>card.id).join(',')">
            <div class="shelf-carcass" aria-hidden="true"><span class="shelf-back" /><span class="shelf-post shelf-post-left" /><span class="shelf-post shelf-post-right" /></div>
            <span class="layer-number">{{ String(layerIndex+1).padStart(2,'0') }}</span>
            <div class="spine-strip"><CardTile v-for="card in layer" :key="card.id" :data-card-id="card.id" :card="card" :touch-mode="touchMode" :expanded="expandedCardId===card.id" @expand="expand" @open="open" /></div>
            <div class="shelf-rail" aria-hidden="true" />
          </div>
        </div>
        <button v-else class="empty-layer" @click="router.push('/add')">这一部分还空着，放点内容进来 →</button>
      </section>
    </main>
    <section v-if="showTrash" class="trash-panel panel">
      <div class="section-heading"><h2>{{ labels[category] }}回收站</h2><button class="icon" @click="showTrash=false">×</button></div>
      <div v-for="card in trash" :key="card.id" class="trash-row"><span>{{ card.title }}</span><div><button class="quiet" @click="restore(card)">恢复</button><button class="danger" @click="permanent(card)">永久删除</button></div></div>
      <p v-if="!trash.length">回收站是空的。</p>
    </section>
  </section>

  <div v-if="selected&&draft" class="modal-backdrop" @click.self="close">
    <section class="modal edit-card-modal panel">
      <div class="modal-head"><div><p class="eyebrow">{{ selected.status === 'completed' ? `${labels[selected.category]}完成档案` : `编辑${labels[selected.category]}卡片` }}</p><h2>《{{ selected.title }}》</h2></div><button class="icon" aria-label="关闭" @click="close">×</button></div>
      <p v-if="notice" class="success-box">{{ notice }}</p><p v-if="error" class="error-box">{{ error }}</p>
      <template v-if="selected.status === 'completed'">
        <div class="completion-hero">
          <div class="completion-cover"><img v-if="selected.image_url" :src="selected.image_url" :alt="`${selected.title}封面`" /><span v-else>{{ selected.title.slice(0, 2) }}</span></div>
          <div class="completion-record">
            <p class="eyebrow">完成于 {{ formatCompletionDate(selected.completed_at) }} <span v-if="selected.extension.completed_at_inferred">· 推定日期</span></p>
            <strong>{{ selected.rating === null ? '未评分' : `${selected.rating.toFixed(1)}/10` }}</strong>
            <blockquote>{{ selected.review || '暂无感想' }}</blockquote>
          </div>
        </div>
        <div class="completion-edit-grid">
          <label>完成日期<input v-model="completionDate" type="date" /></label>
          <label>评分（满分 10）<input v-model.number="completionRating" type="number" min="0" max="10" step="0.1" placeholder="未评分" /></label>
        </div>
        <label>感想<textarea v-model="completionReview" rows="4" placeholder="暂无感想" /></label>
        <details class="completed-source-details">
          <summary>查看资料与编辑</summary>
          <p v-if="descriptionProvenance(selected)" class="description-provenance">{{ descriptionProvenance(selected) }}</p>
          <div class="edit-quick-actions"><button class="quiet" :disabled="enriching" @click="enrich">{{ enriching?'AI 正在补充…':'AI 智能补充' }}</button></div>
          <DraftForm v-model="draft" />
        </details>
      </template>
      <template v-else>
        <div class="edit-quick-actions"><button v-if="selected.status!=='in_progress'" @click="action('start')">开始</button><button @click="action('complete')">完成 / 已体验</button><button class="quiet" @click="action('prioritize')">近期优先</button><button class="quiet" :disabled="enriching" @click="enrich">{{ enriching?'AI 正在补充…':'AI 智能补充' }}</button></div>
        <p v-if="descriptionProvenance(selected)" class="description-provenance">{{ descriptionProvenance(selected) }}</p>
        <DraftForm v-model="draft" />
        <label class="status-editor">卡片状态<select v-model="selected.status"><option value="todo">待体验</option><option value="in_progress">进行中</option></select></label>
      </template>
      <section v-if="['book','game'].includes(selected.category)" class="time-panel">
        <h3>投入时间 · 累计 {{ totalMinutes }} 分钟</h3>
        <div class="time-input"><input v-model.number="timeMinutes" type="number" min="1" placeholder="本次分钟数" /><input v-model="timeNote" placeholder="备注（可选）" /><button @click="addTime">记录</button></div>
        <div v-for="entry in timeEntries" :key="entry.id" class="time-entry"><span>{{ entry.minutes }} 分钟 · {{ entry.note||'无备注' }}</span><button class="text-button" @click="removeTime(entry.id)">删除</button></div>
      </section>
      <div class="modal-actions"><button class="danger" @click="recycle">移入回收站</button><button class="quiet" @click="close">取消</button><button :disabled="saving" @click="selected.status === 'completed' ? saveCompleted() : save()">{{ saving?'正在保存…':selected.status === 'completed'?'保存完成档案':'保存修改' }}</button></div>
    </section>
  </div>
  <CompletionDialog v-if="showCompletion&&selected" :title="selected.title" :include-minutes="['book','game'].includes(selected.category)" :saving="completionSaving" @cancel="showCompletion=false" @submit="complete" />
</template>
