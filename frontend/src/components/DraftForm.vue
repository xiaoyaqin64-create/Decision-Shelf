<script setup lang="ts">
import { computed } from 'vue'
import type { CardDraft, Category, Energy } from '../types'

const props = defineProps<{ modelValue: CardDraft }>()
const emit = defineEmits<{ 'update:modelValue': [CardDraft] }>()
const draft = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

function setField<K extends keyof CardDraft>(key: K, value: CardDraft[K]) {
  draft.value = { ...draft.value, [key]: value }
}

function split(value: string) {
  return value.split(/[,，、]/).map((v) => v.trim()).filter(Boolean)
}
</script>

<template>
  <div class="draft-form">
    <label>标题<input :value="draft.title" @input="setField('title', ($event.target as HTMLInputElement).value)" /></label>
    <div class="form-grid">
      <label>分类
        <select :value="draft.category" @change="setField('category', ($event.target as HTMLSelectElement).value as Category)">
          <option value="movie">电影</option><option value="book">书籍</option><option value="album">专辑</option><option value="game">游戏</option>
        </select>
      </label>
      <label>精力要求
        <select :value="draft.energy_level" @change="setField('energy_level', ($event.target as HTMLSelectElement).value as Energy)">
          <option value="low">低</option><option value="medium">中等</option><option value="high">高</option>
        </select>
      </label>
      <label>总时长（分钟）<input type="number" min="1" :value="draft.duration_minutes ?? ''" @input="setField('duration_minutes', Number(($event.target as HTMLInputElement).value) || null)" /></label>
      <label v-if="draft.category === 'book' || draft.category === 'game'">最小单次投入<input type="number" min="1" :value="draft.min_session_minutes ?? ''" @input="setField('min_session_minutes', Number(($event.target as HTMLInputElement).value) || null)" /></label>
      <label>优先级<input type="number" min="1" max="5" :value="draft.priority" @input="setField('priority', Number(($event.target as HTMLInputElement).value))" /></label>
    </div>
    <label>标签<input :value="draft.tags.join('、')" @input="setField('tags', split(($event.target as HTMLInputElement).value))" /></label>
    <label>适合场景<input :value="draft.mood_fit.join('、')" @input="setField('mood_fit', split(($event.target as HTMLInputElement).value))" /></label>
    <label>简介<textarea rows="4" :value="draft.description" @input="setField('description', ($event.target as HTMLTextAreaElement).value)" /></label>
    <label>备注<textarea rows="2" :value="draft.notes" @input="setField('notes', ($event.target as HTMLTextAreaElement).value)" /></label>
    <label>图片 URL<input :value="draft.image_url ?? ''" @input="setField('image_url', ($event.target as HTMLInputElement).value || null)" /></label>
  </div>
</template>
