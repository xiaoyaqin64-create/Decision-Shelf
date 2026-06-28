<script setup lang="ts">
import { computed, ref } from 'vue'
import { api } from '../api'
import type { CardDraft, CardImportPreview, CardImportPreviewRow, CardImportResult, MetadataCandidate } from '../types'

type MatchState = 'skipped' | 'idle' | 'loading' | 'pending' | 'manual' | 'selected' | 'error'
type ImportRow = CardImportPreviewRow & {
  candidates: MetadataCandidate[]
  matchState: MatchState
  matchMessage: string
  selectedDraft: CardDraft | null
}

const props = defineProps<{ config?: any }>()
const MAX_BYTES = 256 * 1024
const rows = ref<ImportRow[]>([])
const summary = ref<CardImportPreview['summary'] | null>(null)
const warnings = ref<string[]>([])
const filename = ref('')
const loading = ref(false)
const matching = ref(false)
const importing = ref(false)
const error = ref('')
const result = ref<CardImportResult | null>(null)
let runId = 0

const importableRows = computed(() => rows.value.filter((row) => row.status === 'valid' && row.draft))
const unresolvedRows = computed(() => importableRows.value.filter((row) => ['idle', 'loading', 'pending'].includes(row.matchState)))
const canImport = computed(() => importableRows.value.length > 0 && unresolvedRows.value.length === 0 && !importing.value && !result.value)
const matchedCount = computed(() => importableRows.value.filter((row) => !['idle', 'loading'].includes(row.matchState)).length)

function downloadTemplate() {
  const header = '分类,标题,总时长（分钟）,最小单次投入（分钟）,标签,精力要求,适合场景,优先级,简介,备注,图片 URL\r\n'
  const url = URL.createObjectURL(new Blob([`\ufeff${header}`], { type: 'text/csv;charset=utf-8' }))
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'Decision-Shelf-批量导入模板.csv'
  anchor.click()
  URL.revokeObjectURL(url)
}

function providerAvailable(category: string) {
  return category !== 'game' && props.config?.metadata?.[category]?.available !== false
}

function initializeRows(preview: CardImportPreview) {
  rows.value = preview.rows.map((row) => ({
    ...row,
    candidates: [],
    matchState: row.status !== 'valid' ? 'skipped' : (providerAvailable(row.draft!.category) ? 'idle' : 'manual'),
    matchMessage: row.status === 'valid' && !providerAvailable(row.draft!.category)
      ? (row.draft!.category === 'game' ? '游戏暂不支持外部匹配，将按原文导入。' : '外部数据源不可用，将按原文导入。')
      : '',
    selectedDraft: row.status === 'valid' && !providerAvailable(row.draft!.category) ? row.draft : null,
  }))
}

async function selectFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  error.value = ''
  result.value = null
  if (!file.name.toLowerCase().endsWith('.csv')) { error.value = '请选择 .csv 文件。'; return }
  if (file.size > MAX_BYTES) { error.value = 'CSV 文件不能超过 256 KB。'; return }
  loading.value = true
  runId += 1
  try {
    let content: string
    try {
      content = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer())
    } catch {
      throw new Error('CSV 必须使用 UTF-8 或 UTF-8 BOM 编码。')
    }
    const preview = await api.previewCardImport(file.name, content)
    filename.value = file.name
    summary.value = preview.summary
    warnings.value = preview.warnings
    initializeRows(preview)
    await startMatching()
  } catch (e) {
    error.value = (e as Error).message
    rows.value = []
    summary.value = null
  } finally {
    loading.value = false
    input.value = ''
  }
}

async function startMatching() {
  const currentRun = ++runId
  const targets = rows.value.filter((row) => row.matchState === 'idle' && row.draft)
  if (!targets.length) return
  matching.value = true
  let cursor = 0
  async function worker() {
    while (cursor < targets.length && currentRun === runId) {
      const row = targets[cursor++]
      row.matchState = 'loading'
      try {
        const response = await api.metadataSearch(row.draft!.category, row.draft!.title)
        if (currentRun !== runId) return
        row.candidates = response.items.slice(0, 3)
        if (row.candidates.length) {
          row.matchState = 'pending'
          row.matchMessage = '请选择正确候选，或按 CSV 原文导入。'
        } else {
          row.matchState = 'manual'
          row.selectedDraft = row.draft
          row.matchMessage = '没有找到候选，将按原文导入。'
        }
      } catch (e) {
        if (currentRun !== runId) return
        row.matchState = 'error'
        row.selectedDraft = row.draft
        row.matchMessage = `匹配失败，将按原文导入：${(e as Error).message}`
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(3, targets.length) }, () => worker()))
  if (currentRun === runId) matching.value = false
}

function stopMatching() {
  runId += 1
  matching.value = false
  for (const row of rows.value) {
    if (row.status === 'valid' && ['idle', 'loading'].includes(row.matchState)) {
      row.matchState = 'manual'
      row.selectedDraft = row.draft
      row.matchMessage = '已停止匹配，将按原文导入。'
    }
  }
}

function useManual(row: ImportRow) {
  row.selectedDraft = row.draft
  row.matchState = 'manual'
  row.matchMessage = '将按 CSV 原文导入。'
}

function mergeDraft(external: CardDraft, csvDraft: CardDraft, provided: Array<keyof CardDraft>): CardDraft {
  const merged: CardDraft = { ...external, source: external.source, external_id: external.external_id }
  for (const field of provided) {
    if (field !== 'source' && field !== 'external_id' && field !== 'extension') {
      ;(merged as any)[field] = csvDraft[field]
    }
  }
  return merged
}

async function chooseCandidate(row: ImportRow, candidate: MetadataCandidate) {
  row.matchState = 'loading'
  row.matchMessage = '正在读取候选详情…'
  try {
    const external = await api.metadataDraft(row.draft!.category, candidate.external_id)
    row.selectedDraft = mergeDraft(external, row.draft!, row.provided_fields)
    row.matchState = 'selected'
    row.matchMessage = `已匹配：${candidate.title}${candidate.subtitle ? ` · ${candidate.subtitle}` : ''}`
  } catch (e) {
    row.matchState = 'pending'
    row.matchMessage = `候选详情读取失败：${(e as Error).message}`
  }
}

async function commitImport() {
  if (!canImport.value) return
  importing.value = true
  error.value = ''
  try {
    result.value = await api.importCards(importableRows.value.map((row) => ({
      row_number: row.row_number,
      draft: row.selectedDraft || row.draft!,
    })))
  } catch (e) {
    error.value = (e as Error).message
  } finally {
    importing.value = false
  }
}
</script>

<template>
  <div class="batch-import">
    <div class="step-card panel">
      <div class="step-number">1</div>
      <div class="step-content">
        <h2>准备 CSV 文件</h2>
        <p>分类和标题为必填，一次最多 50 条。请使用 UTF-8 CSV。</p>
        <div class="form-actions import-file-actions">
          <button class="quiet" type="button" @click="downloadTemplate">下载 CSV 模板</button>
          <label class="file-button" :class="{ disabled: loading }">
            {{ loading ? '正在解析…' : '选择 CSV 文件' }}
            <input type="file" accept=".csv,text/csv" :disabled="loading" @change="selectFile" />
          </label>
        </div>
        <small v-if="filename">当前文件：{{ filename }}</small>
      </div>
    </div>

    <p v-if="error" class="error-box">{{ error }}</p>
    <template v-if="summary">
      <div class="import-summary panel">
        <strong>共 {{ summary.total }} 条</strong>
        <span>可导入 {{ summary.valid }}</span>
        <span>重复 {{ summary.duplicate }}</span>
        <span>错误 {{ summary.invalid }}</span>
      </div>
      <p v-for="warning in warnings" :key="warning" class="warning-box">{{ warning }}</p>

      <div class="section-heading import-heading">
        <div><h2>预览并确认</h2><p>外部资料只补充 CSV 中没有填写的字段。</p></div>
        <div v-if="matching" class="match-progress">
          <span>正在匹配 {{ matchedCount }}/{{ importableRows.length }}</span>
          <button class="text-button" type="button" @click="stopMatching">停止并按原文处理</button>
        </div>
      </div>

      <article v-for="row in rows" :key="row.row_number" class="import-row panel" :class="`is-${row.status}`">
        <div class="import-row-title">
          <span class="row-number">第 {{ row.row_number }} 行</span>
          <strong v-if="row.draft">《{{ row.draft.title }}》</strong>
          <span v-if="row.draft">{{ { movie: '电影', book: '书籍', album: '专辑', game: '游戏' }[row.draft.category] }}</span>
        </div>
        <p v-for="item in row.errors" :key="item" :class="row.status === 'invalid' ? 'row-error' : 'row-warning'">{{ item }}</p>
        <template v-if="row.status === 'valid'">
          <p v-if="row.matchMessage" class="match-message">{{ row.matchMessage }}</p>
          <div v-if="row.matchState === 'loading'" class="match-loading">正在匹配…</div>
          <div v-if="row.candidates.length && ['pending', 'selected', 'manual'].includes(row.matchState)" class="candidate-list">
            <button v-for="candidate in row.candidates" :key="candidate.external_id" type="button" class="candidate-option" @click="chooseCandidate(row, candidate)">
              <img v-if="candidate.image_url" :src="candidate.image_url" alt="" />
              <span><strong>{{ candidate.title }}</strong><small>{{ candidate.subtitle }}<template v-if="candidate.year"> · {{ candidate.year }}</template></small></span>
            </button>
            <button type="button" class="candidate-option manual-option" @click="useManual(row)">按 CSV 原文导入</button>
          </div>
        </template>
      </article>

      <div class="form-actions import-submit">
        <span v-if="unresolvedRows.length">还有 {{ unresolvedRows.length }} 条等待匹配或确认</span>
        <button :disabled="!canImport" type="button" @click="commitImport">{{ importing ? '正在导入…' : `导入 ${importableRows.length} 张卡片` }}</button>
      </div>
    </template>

    <div v-if="result" class="success-box import-result">
      <strong>批量导入完成</strong>
      <span>新增 {{ result.summary.created }} 张，跳过 {{ result.summary.skipped }} 张，失败 {{ result.summary.failed }} 张。</span>
      <RouterLink to="/shelf/movie">查看书架 →</RouterLink>
    </div>
  </div>
</template>
