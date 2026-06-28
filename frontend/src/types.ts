export type Category = 'movie' | 'book' | 'album' | 'game'
export type Energy = 'low' | 'medium' | 'high'

export interface CardDraft {
  category: Category
  title: string
  source: string
  external_id: string | null
  description: string
  image_url: string | null
  theme_color?: string | null
  theme_color_source?: 'pending' | 'extracted' | 'fallback'
  duration_minutes: number | null
  min_session_minutes: number | null
  tags: string[]
  energy_level: Energy
  mood_fit: string[]
  notes: string
  priority: number
  extension: Record<string, unknown>
}

export interface Card extends CardDraft {
  id: string
  status: 'todo' | 'in_progress' | 'completed' | 'removed'
  is_prioritized: boolean
  created_at: string | null
  updated_at: string | null
  last_recommended_at: string | null
  completed_at: string | null
  rating: number | null
  review: string | null
}

export interface MetadataCandidate {
  source: string
  external_id: string
  category: Category
  title: string
  subtitle: string
  year: number | null
  creators: string[]
  image_url: string | null
  description: string
}

export interface ScoredCandidate {
  card_id: string
  title: string
  category: Category
  total_score: number
  fit_score: number
  scores: Record<string, number>
  adjustments: Record<string, number>
  explanation: string
}

export interface ExplorationSuggestion {
  id: string
  session_id: number
  draft: CardDraft
  verified: boolean
  fit_score: number
  reason: string
  resolution: string
  resolved_card_id: string | null
  is_best: boolean
}

export interface Taxonomy { genres: Record<Category, string[]>; scenes: string[] }
export interface TimeEntry { id: number; card_id: string; minutes: number; note: string; recorded_at: string }

export interface CardImportPreviewRow {
  row_number: number
  raw: Record<string, string>
  draft: CardDraft | null
  provided_fields: Array<keyof CardDraft>
  status: 'valid' | 'duplicate' | 'invalid'
  errors: string[]
  existing_card: Pick<Card, 'id' | 'title' | 'category' | 'status'> | null
}

export interface CardImportPreview {
  rows: CardImportPreviewRow[]
  summary: { total: number; valid: number; duplicate: number; invalid: number }
  warnings: string[]
}

export interface CardImportResult {
  items: Array<{
    row_number: number
    status: 'created' | 'skipped_duplicate' | 'failed'
    card: Card | null
    message: string
  }>
  summary: { created: number; skipped: number; failed: number }
}

export interface DecisionResponse {
  session_id: number
  scope: 'shelf_only' | 'shelf_first' | 'free'
  shelf_recommendation: ScoredCandidate | null
  exploration_suggestions: ExplorationSuggestion[]
  eligible_count: number
  top_fit_score: number | null
  fallback_reason: string | null
  exploration_error: string | null
  warnings: string[]
}
