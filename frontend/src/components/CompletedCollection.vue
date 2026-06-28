<script setup lang="ts">
import type { Card, Category } from '../types'

defineProps<{ category: Category; cards: Card[] }>()
const emit = defineEmits<{ open: [Card] }>()

function dateText(value: string | null) {
  if (!value) return '日期未记录'
  const date = new Date(value.length === 10 ? `${value}T00:00:00` : value)
  return Number.isNaN(date.getTime()) ? value.slice(0, 10) : date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'short', day: 'numeric' })
}

function ratingText(value: number | null) {
  return value === null ? '未评分' : `${value.toFixed(1)}/10`
}
</script>

<template>
  <div class="completed-collection" :class="`completed-${category}`">
    <template v-if="category === 'movie'">
      <button v-for="card in cards" :key="card.id" class="movie-archive completed-artifact" @click="emit('open', card)">
        <div class="movie-poster"><img v-if="card.image_url" :src="card.image_url" :alt="`${card.title}海报`" /><span v-else>{{ card.title.slice(0, 2) }}</span><b>{{ ratingText(card.rating) }}</b></div>
        <div class="artifact-copy"><h3 class="artifact-title">{{ card.title }}</h3><time>{{ dateText(card.completed_at) }}</time><p>{{ card.review || '暂无感想' }}</p></div>
      </button>
    </template>

    <template v-else-if="category === 'album'">
      <button v-for="card in cards" :key="card.id" class="album-archive completed-artifact" @click="emit('open', card)">
        <div class="artifact-visual">
          <div class="vinyl-stage"><span class="vinyl-disc"><i /></span><span class="album-sleeve"><img v-if="card.image_url" :src="card.image_url" :alt="`${card.title}封面`" /><i v-else>{{ card.title.slice(0, 2) }}</i></span></div>
          <h3 class="artifact-title">{{ card.title }}</h3>
        </div>
        <div class="artifact-copy"><strong>{{ ratingText(card.rating) }}</strong><time>{{ dateText(card.completed_at) }}</time><p>{{ card.review || '暂无感想' }}</p></div>
      </button>
    </template>

    <template v-else>
      <button v-for="card in cards" :key="card.id" class="game-archive completed-artifact" @click="emit('open', card)">
        <div class="artifact-visual">
          <div class="game-disc"><span class="disc-rainbow" /><span class="disc-label"><img v-if="card.image_url" :src="card.image_url" :alt="`${card.title}封面`" /><i v-else>{{ card.title.slice(0, 2) }}</i></span></div>
          <h3 class="artifact-title">{{ card.title }}</h3>
        </div>
        <div class="artifact-copy"><strong>{{ ratingText(card.rating) }}</strong><time>{{ dateText(card.completed_at) }}</time><p>{{ card.review || '暂无感想' }}</p></div>
      </button>
    </template>
  </div>
</template>
