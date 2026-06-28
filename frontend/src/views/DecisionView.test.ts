import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import DecisionView from './DecisionView.vue'

afterEach(() => vi.restoreAllMocks())

describe('DecisionView', () => {
  it('sends shelf_first by default and renders a single shelf result', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => ({
      ok: true,
      json: async () => String(input).includes('/api/taxonomy') ? ({ genres: { movie:['科幻'], book:[], album:[], game:[] }, scenes:['灵感'] }) : ({
        session_id: 1,
        scope: 'shelf_first',
        shelf_recommendation: {
          card_id: 'movie_a', title: '测试电影', category: 'movie', total_score: 88,
          fit_score: 82, scores: {}, adjustments: {}, explanation: '现在很适合。',
        },
        exploration_suggestions: [], eligible_count: 5, top_fit_score: 82,
        fallback_reason: null, exploration_error: null, warnings: [],
      }),
    } as Response))
    const wrapper = mount(DecisionView, {
      global: { stubs: { DraftForm: true } },
    })
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    const init = fetchMock.mock.calls.find(call => String(call[0]).includes('/api/decisions'))?.[1] as RequestInit
    expect(JSON.parse(String(init.body)).scope).toBe('shelf_first')
    expect(wrapper.text()).toContain('测试电影')
    expect(wrapper.findAll('.primary-recommendation')).toHaveLength(1)
  })
})
