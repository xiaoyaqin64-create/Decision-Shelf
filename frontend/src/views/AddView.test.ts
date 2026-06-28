import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import AddView from './AddView.vue'

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('AddView', () => {
  it('debounces metadata search until 350ms', async () => {
    vi.useFakeTimers()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = String(input)
      return {
        ok: true,
        json: async () => url === '/api/config'
          ? { deepseek: { available: true }, metadata: { movie: { available: true } } }
          : { items: [] },
      } as Response
    })
    const wrapper = mount(AddView, { global: { stubs: { DraftForm: true } } })
    await flushPromises()
    const search = wrapper.find('.search-box input')
    await search.setValue('盗梦空间')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(349)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(1)
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(String(fetchMock.mock.calls[1][0])).toContain('/api/metadata/movie/search')
  })
})
