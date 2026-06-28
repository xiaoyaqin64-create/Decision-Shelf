import type { Card, CardDraft, CardImportPreview, CardImportResult, DecisionResponse, MetadataCandidate, Taxonomy, TimeEntry } from './types'

export class ApiError extends Error {
  code: string
  retryable: boolean

  constructor(message: string, code = 'request_failed', retryable = false) {
    super(message)
    this.code = code
    this.retryable = retryable
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new ApiError(body.message ?? `请求失败（${response.status}）`, body.code, body.retryable)
  }
  return body as T
}

export const api = {
  config: () => request<any>('/api/config'),
  taxonomy: () => request<Taxonomy>('/api/taxonomy'),
  cards: (params = '') => request<{ items: Card[] }>(`/api/cards${params}`),
  resolveThemeColors: (cardIds: string[]) => request<{items:Array<{id:string;theme_color:string;source:string;resolved:boolean}>}>('/api/cards/theme-colors/resolve', { method: 'POST', body: JSON.stringify({ card_ids: cardIds }) }),
  createCard: (draft: CardDraft) => request<Card>('/api/cards', { method: 'POST', body: JSON.stringify(draft) }),
  previewCardImport: (filename: string, content: string) => request<CardImportPreview>('/api/cards/import/preview', { method: 'POST', body: JSON.stringify({ filename, content }) }),
  importCards: (items: Array<{ row_number: number; draft: CardDraft }>) => request<CardImportResult>('/api/cards/import', { method: 'POST', body: JSON.stringify({ items }) }),
  updateCard: (id: string, patch: Partial<Card>) => request<Card>(`/api/cards/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  enrichCard: (id: string) => request<{ draft: CardDraft; source: string; warning: string | null; retried: boolean }>(`/api/cards/${id}/enrich`, { method: 'POST' }),
  recycleCard: (id: string) => request<Card>(`/api/cards/${id}`, { method: 'DELETE' }),
  restoreCard: (id: string) => request<Card>(`/api/cards/${id}/restore`, { method: 'POST' }),
  permanentDeleteCard: (id: string) => request<{ok:boolean}>(`/api/cards/${id}/permanent`, { method: 'DELETE' }),
  timeEntries: (id: string) => request<{items: TimeEntry[]; total_minutes: number}>(`/api/cards/${id}/time-entries`),
  addTimeEntry: (id: string, minutes: number, note = '') => request<{item:TimeEntry;total_minutes:number}>(`/api/cards/${id}/time-entries`, { method: 'POST', body: JSON.stringify({minutes,note}) }),
  deleteTimeEntry: (id: number) => request<{ok:boolean}>(`/api/time-entries/${id}`, { method: 'DELETE' }),
  action: (id: string, action: string, extra: Record<string, unknown> = {}) => request<Card>(`/api/cards/${id}/actions`, { method: 'POST', body: JSON.stringify({ action, ...extra }) }),
  metadataSearch: (category: string, query: string) => request<{ items: MetadataCandidate[] }>(`/api/metadata/${category}/search?q=${encodeURIComponent(query)}`),
  metadataDraft: (category: string, id: string) => request<CardDraft>(`/api/metadata/${category}/draft?source_id=${encodeURIComponent(id)}`),
  enrich: (draft: CardDraft) => request<{ draft: CardDraft; source: string; warning: string | null }>('/api/metadata/enrich', { method: 'POST', body: JSON.stringify({ draft }) }),
  decide: (payload: Record<string, unknown>) => request<DecisionResponse>('/api/decisions', { method: 'POST', body: JSON.stringify(payload) }),
  resolveExploration: (id: string, payload: Record<string, unknown>) => request<{ action: string; card: Card | null }>(`/api/exploration/${id}/resolve`, { method: 'POST', body: JSON.stringify(payload) }),
  history: () => request<{ items: any[] }>('/api/history'),
  preferences: () => request<{ items: any[] }>('/api/preferences'),
  resetPreferences: () => request<{ ok: boolean }>('/api/preferences', { method: 'DELETE' }),
}
