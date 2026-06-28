<script setup lang="ts">
import { computed } from 'vue'
import type { Card } from '../types'
import { spineWidthForId } from '../shelfLayout'

const props = defineProps<{ card: Card }>()
const emit = defineEmits<{ open: [Card] }>()
const statuses: Record<string, string> = { todo: '待体验', in_progress: '进行中', completed: '已完成', removed: '回收站' }
const categoryColors: Record<string, string> = {
  movie: '#583039',
  book: '#345248',
  album: '#4B406A',
  game: '#2D5862',
}
const categoryMarks: Record<string, string> = { movie: '影', book: '书', album: '乐', game: '游' }
const categoryColor = computed(() => categoryColors[props.card.category] ?? categoryColors.movie)
const accentColor = computed(() => props.card.theme_color || categoryColor.value)
const numericSpineWidth = computed(() => spineWidthForId(props.card.id))
const spineWidth = computed(() => `${numericSpineWidth.value}px`)
const toneClass = computed(() => `tone-${(numericSpineWidth.value - 52) / 4}`)
const completedDate = computed(() => {
  if (!props.card.completed_at) return '日期未记录'
  const value = props.card.completed_at
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value)
  return Number.isNaN(date.getTime()) ? value.slice(0, 10) : date.toLocaleDateString('zh-CN')
})
const ratingText = computed(() => props.card.rating === null ? '未评分' : `${props.card.rating.toFixed(1)}/10`)
</script>

<template>
  <article
    class="book-spine"
    :class="[`spine-${card.category}`, `status-${card.status}`, toneClass]"
    :style="{'--theme-color':categoryColor,'--accent-color':accentColor,'--spine-width':spineWidth}"
    role="button"
    :aria-label="`打开《${card.title}》`"
    tabindex="0"
    @click="emit('open',card)"
    @keydown.enter="emit('open',card)"
  >
    <div class="spine-surface" />
    <span class="spine-title">{{ card.title }}</span>
    <span class="spine-mark" aria-hidden="true">{{ categoryMarks[card.category] }}</span>
    <span v-if="card.is_prioritized" class="spine-priority" title="近期优先" aria-label="近期优先" />
    <div class="spine-expanded">
      <div class="expanded-poster-frame">
        <img v-if="card.image_url" class="expanded-poster" :src="card.image_url" :alt="`${card.title}海报`" loading="lazy" />
        <span v-else class="expanded-poster-placeholder">{{ card.title.slice(0,2) }}</span>
      </div>
      <div v-if="card.status === 'completed'" class="expanded-copy completed-spine-copy">
        <p>已完成 · {{ completedDate }}</p>
        <h3>{{ card.title }}</h3>
        <div class="completed-score">{{ ratingText }}</div>
        <small>{{ card.review || '暂无感想' }}</small>
        <b>查看完成档案 →</b>
      </div>
      <div v-else class="expanded-copy">
        <p>{{ statuses[card.status] }}</p>
        <h3>{{ card.title }}</h3>
        <div class="expanded-tags"><span v-for="tag in [...card.tags,...card.mood_fit].slice(0,3)" :key="tag">{{ tag }}</span></div>
        <small>{{ card.description || card.notes || '暂无简介，可在编辑中使用 AI 补充。' }}</small>
        <b>点击编辑 →</b>
      </div>
    </div>
  </article>
</template>
