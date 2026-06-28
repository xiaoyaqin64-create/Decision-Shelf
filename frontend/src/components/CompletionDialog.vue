<script setup lang="ts">
import { ref } from 'vue'

const props = defineProps<{ title: string; includeMinutes?: boolean; saving?: boolean }>()
const emit = defineEmits<{
  submit: [{ completed_at: string; rating: number | null; review: string | null; final_minutes?: number }]
  cancel: []
}>()

const now = new Date()
const completedAt = ref(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`)
const rating = ref<string>('')
const review = ref('')
const finalMinutes = ref<number | null>(null)
const error = ref('')

function submit() {
  const score = rating.value === '' ? null : Number(rating.value)
  if (!completedAt.value) { error.value = '请选择完成日期。'; return }
  if (score !== null && (!Number.isFinite(score) || score < 0 || score > 10 || Math.abs(score * 10 - Math.round(score * 10)) > 1e-8)) {
    error.value = '评分必须在 0～10 之间，最多保留一位小数。'
    return
  }
  emit('submit', {
    completed_at: completedAt.value,
    rating: score,
    review: review.value.trim() || null,
    ...(props.includeMinutes && finalMinutes.value ? { final_minutes: finalMinutes.value } : {}),
  })
}
</script>

<template>
  <div class="modal-backdrop completion-backdrop" @click.self="emit('cancel')">
    <section class="modal completion-dialog panel">
      <div class="modal-head"><div><p class="eyebrow">COMPLETE</p><h2>完成《{{ title }}》</h2></div><button class="icon" aria-label="关闭" @click="emit('cancel')">×</button></div>
      <p>把这一刻留在收藏馆里。评分和感想都可以稍后再补。</p>
      <p v-if="error" class="error-box">{{ error }}</p>
      <div class="completion-fields">
        <label>完成日期<input v-model="completedAt" type="date" /></label>
        <label>评分（满分 10）<input v-model="rating" type="number" min="0" max="10" step="0.1" placeholder="可留空" /></label>
        <label v-if="includeMinutes">最后一次投入（分钟）<input v-model.number="finalMinutes" type="number" min="1" placeholder="可留空" /></label>
      </div>
      <label>感想<textarea v-model="review" rows="4" placeholder="写下此刻最想记住的感受（可留空）" /></label>
      <div class="modal-actions"><button class="quiet" @click="emit('cancel')">取消</button><button :disabled="saving" @click="submit">{{ saving ? '正在保存…' : '收入收藏馆' }}</button></div>
    </section>
  </div>
</template>
