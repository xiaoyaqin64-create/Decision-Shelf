import { describe, expect, it } from 'vitest'
import { chunkItemsByWidth, DESKTOP_EXPANDED_WIDTH, DESKTOP_SPINE_WIDTHS, spineWidthForId } from './shelfLayout'

describe('shelf layout', () => {
  it('uses only the four stable desktop spine widths', () => {
    const ids = Array.from({ length: 80 }, (_, index) => `card-${index}`)
    const firstPass = ids.map(id => spineWidthForId(id))
    const secondPass = ids.map(id => spineWidthForId(id))
    expect(firstPass).toEqual(secondPass)
    expect(new Set(firstPass)).toEqual(new Set(DESKTOP_SPINE_WIDTHS))
  })

  it('creates a new layer when the next variable-width spine exceeds the safe area', () => {
    const width = 1148
    const available = width - 64 - (DESKTOP_EXPANDED_WIDTH - Math.min(...DESKTOP_SPINE_WIDTHS))
    const items: Array<{ id: string }> = []
    let used = 0
    for (let index = 0; index < 100; index += 1) {
      const item = { id: `boundary-${index}` }
      const itemWidth = spineWidthForId(item.id)
      if (items.length && used + itemWidth > available) {
        const layers = chunkItemsByWidth([...items, item], width)
        expect(layers).toHaveLength(2)
        expect(layers[0]).toEqual(items)
        expect(layers[1]).toEqual([item])
        return
      }
      items.push(item)
      used += itemWidth
    }
    throw new Error('没有构造出容量边界')
  })

  it('keeps every item exactly once and reserves room for expansion', () => {
    const items = Array.from({ length: 53 }, (_, index) => ({ id: `card-${index}` }))
    for (const width of [390, 720, 1280]) {
      const layers = chunkItemsByWidth(items, width)
      expect(layers.flat()).toEqual(items)
      if (width > 700) {
        for (const layer of layers) {
          const collapsed = layer.reduce((sum, item) => sum + spineWidthForId(item.id), 0)
          const largestExpansion = Math.max(...layer.map(item => DESKTOP_EXPANDED_WIDTH - spineWidthForId(item.id)))
          expect(collapsed + largestExpansion).toBeLessThanOrEqual(width - 64)
        }
      }
    }
  })
})
