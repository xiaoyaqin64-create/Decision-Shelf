import type { Card } from './types'

export const DESKTOP_SPINE_WIDTHS = [52, 56, 60, 64] as const
export const MOBILE_SPINE_WIDTH = 48
export const DESKTOP_EXPANDED_WIDTH = 400

function stableHash(value: string): number {
  let hash = 2166136261
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 16777619)
  }
  return hash >>> 0
}

export function spineWidthForId(id: string, mobile = false): number {
  if (mobile) return MOBILE_SPINE_WIDTH
  return DESKTOP_SPINE_WIDTHS[stableHash(id) % DESKTOP_SPINE_WIDTHS.length]
}

function availableCollapsedWidth(width: number, mobile: boolean): number {
  const horizontalSafety = mobile ? 32 : 64
  const expansionReserve = mobile ? 0 : DESKTOP_EXPANDED_WIDTH - Math.min(...DESKTOP_SPINE_WIDTHS)
  return Math.max(1, Math.max(0, width) - horizontalSafety - expansionReserve)
}

export function calculateShelfCapacity(width: number): number {
  const mobile = width <= 700
  const nominalWidth = mobile ? MOBILE_SPINE_WIDTH : 56
  return Math.max(1, Math.floor(availableCollapsedWidth(width, mobile) / nominalWidth))
}

export function chunkItemsByWidth<T extends { id: string }>(items: T[], width: number): T[][] {
  if (!items.length) return []
  const mobile = width <= 700
  const available = availableCollapsedWidth(width, mobile)
  const layers: T[][] = []
  let layer: T[] = []
  let used = 0

  for (const item of items) {
    const itemWidth = spineWidthForId(item.id, mobile)
    if (layer.length && used + itemWidth > available) {
      layers.push(layer)
      layer = []
      used = 0
    }
    layer.push(item)
    used += itemWidth
  }
  if (layer.length) layers.push(layer)
  return layers
}

export function chunkItems<T>(items: T[], capacity: number): T[][] {
  const size = Math.max(1, Math.floor(capacity))
  const layers: T[][] = []
  for (let index = 0; index < items.length; index += size) layers.push(items.slice(index, index + size))
  return layers
}

export function cardSortTime(card: Card, status: string): string {
  if (status === 'completed') return card.completed_at || card.updated_at || card.created_at || ''
  if (status === 'in_progress') return card.updated_at || card.created_at || ''
  return card.created_at || ''
}
