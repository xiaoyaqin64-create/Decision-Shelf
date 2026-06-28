<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import CardTile from '../components/CardTile.vue'
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
const timeEntries = ref<TimeEntry[]>([])
const totalMinutes = ref(0)
const timeMinutes = ref<number | null>(null)
const timeNote = ref('')
const layoutRoot = ref<HTMLElement | null>(null)
const layoutWidth = ref(1000)
const capacity = ref(12)
const attemptedColors = new Set<string>()
let resizeObserver: ResizeObserver | undefined
let layerObserver: IntersectionObserver | undefined

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
    .sort((a, b) => cardSortTime(a, def.key).localeCompare(cardSortTime(b, def.key)) || a.id.localeCompare(b.id))
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
  selected.value = card
  draft.value = { ...card, tags: [...card.tags], mood_fit: [...card.mood_fit], extension: { ...card.extension } }
  notice.value = ''
  error.value = ''
  if (['book', 'game'].includes(card.category)) {
    const data = await api.timeEntries(card.id)
    timeEntries.value = data.items
    totalMinutes.value = data.total_minutes
  }
}

function close() {
  selected.value = null
  draft.value = null
  timeEntries.value = []
  notice.value = ''
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

async function enrich() {
  if (!selected.value) return
  enriching.value = true
  error.value = ''
  try {
    const result = await api.enrichCard(selected.value.id)
    draft.value = result.draft
    notice.value = result.warning
      ? `AI 补全未完成：${result.warning}`
      : `AI 已生成补全草稿${result.retried ? '（纠正重试后成功）' : ''}，保存后生效。`
  } catch (reason) {
    error.value = (reason as Error).message
  } finally {
    enriching.value = false
  }
}

async function action(name: string) {
  if (!selected.value) return
  const extra: Record<string, unknown> = {}
  if (name === 'complete') {
    if (['book', 'game'].includes(selected.value.category)) {
      const minutes = prompt('最后一次投入了多少分钟？（可留空）')
      if (minutes) extra.final_minutes = Number(minutes)
    }
    const rating = prompt('评分 1～5（可留空）')
    const review = prompt('写一句感想（可留空）')
    if (rating) extra.rating = Number(rating)
    if (review) extra.review = review
  }
  selected.value = await api.action(selected.value.id, name, extra)
  await load()
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
  void load()
}, { immediate: true })
watch([layoutWidth, query], async () => { await nextTick(); setupLayerObserver() })
onMounted(() => {
  resizeObserver = new ResizeObserver(recalc)
  if (layoutRoot.value) resizeObserver.observe(layoutRoot.value)
  recalc()
})
onBeforeUnmount(() => { resizeObserver?.disconnect(); layerObserver?.disconnect() })
</script>

<template>
  <section ref="layoutRoot" class="page category-library">
    <header class="library-heading">
      <div><p class="eyebrow">{{ category.toUpperCase() }} LIBRARY</p><h1>{{ labels[category] }}书架</h1><p>每一层从左到右生长。停在书脊上，让它为你展开。</p></div>
      <RouterLink to="/add" class="button primary">＋ 加入新内容</RouterLink>
    </header>
    <div class="library-toolbar panel">
      <input v-model="query" placeholder="搜索当前书架的标题或标签" />
      <span>{{ visibleCards.filter(card=>card.status!=='removed').length }} 张内容 · 每层约 {{ capacity }} 张</span>
      <button class="quiet" @click="showTrash=!showTrash">回收站 {{ trash.length }}</button>
    </div>
    <p v-if="error && !selected" class="error-box">{{ error }}</p>
    <p v-if="loading" class="empty-state">正在整理{{ labels[category] }}书架…</p>
    <main v-else class="status-shelves">
      <section v-for="section in sections" :key="section.key" class="status-shelf" :class="`shelf-${section.key}`">
        <div class="status-heading"><div><p>{{ section.hint }}</p><h2>{{ section.label }}</h2></div><span>{{ section.items.length }} 张 · {{ section.layers.length }} 层</span></div>
        <div v-if="section.layers.length" class="shelf-layers">
          <div v-for="(layer,layerIndex) in section.layers" :key="`${section.key}-${layerIndex}-${layoutWidth}`" class="shelf-layer" :data-card-ids="layer.map(card=>card.id).join(',')">
            <div class="shelf-carcass" aria-hidden="true"><span class="shelf-back" /><span class="shelf-post shelf-post-left" /><span class="shelf-post shelf-post-right" /></div>
            <span class="layer-number">{{ String(layerIndex+1).padStart(2,'0') }}</span>
            <div class="spine-strip"><CardTile v-for="card in layer" :key="card.id" :card="card" @open="open" /></div>
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
      <div class="modal-head"><div><p class="eyebrow">编辑{{ labels[selected.category] }}卡片</p><h2>《{{ selected.title }}》</h2></div><button class="icon" aria-label="关闭" @click="close">×</button></div>
      <p v-if="notice" class="success-box">{{ notice }}</p><p v-if="error" class="error-box">{{ error }}</p>
      <div class="edit-quick-actions"><button v-if="selected.status!=='in_progress'&&selected.status!=='completed'" @click="action('start')">开始</button><button v-if="selected.status!=='completed'" @click="action('complete')">完成 / 已体验</button><button class="quiet" @click="action('prioritize')">近期优先</button><button class="quiet" :disabled="enriching" @click="enrich">{{ enriching?'AI 正在补充…':'AI 智能补充' }}</button></div>
      <DraftForm v-model="draft" />
      <label class="status-editor">卡片状态<select v-model="selected.status"><option value="todo">待体验</option><option value="in_progress">进行中</option><option value="completed">已完成</option></select></label>
      <section v-if="['book','game'].includes(selected.category)" class="time-panel">
        <h3>投入时间 · 累计 {{ totalMinutes }} 分钟</h3>
        <div class="time-input"><input v-model.number="timeMinutes" type="number" min="1" placeholder="本次分钟数" /><input v-model="timeNote" placeholder="备注（可选）" /><button @click="addTime">记录</button></div>
        <div v-for="entry in timeEntries" :key="entry.id" class="time-entry"><span>{{ entry.minutes }} 分钟 · {{ entry.note||'无备注' }}</span><button class="text-button" @click="removeTime(entry.id)">删除</button></div>
      </section>
      <div class="modal-actions"><button class="danger" @click="recycle">移入回收站</button><button class="quiet" @click="close">取消</button><button :disabled="saving" @click="save">{{ saving?'正在保存…':'保存修改' }}</button></div>
    </section>
  </div>
</template>
