import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ShelfView from './ShelfView.vue'
import type { Card } from '../types'

class ResizeObserverStub { observe() {} disconnect() {} }
class IntersectionObserverStub { constructor(_callback: IntersectionObserverCallback) {} observe() {} disconnect() {} }

const card: Card = {
  id: 'movie-1', category: 'movie', title: '独立电影', status: 'todo', duration_minutes: 90, min_session_minutes: null,
  tags: ['科幻'], energy_level: 'medium', mood_fit: ['沉浸'], source: 'manual', external_id: null, description: '简介', image_url: '/poster.jpg',
  theme_color: '#334455', theme_color_source: 'fallback', notes: '', priority: 3, is_prioritized: false, extension: {}, created_at: '2026-01-01',
  updated_at: '2026-01-01', last_recommended_at: null, completed_at: null, rating: null, review: null,
}

function makeRouter() {
  return createRouter({ history: createMemoryHistory(), routes: [{ path: '/shelf/:category', component: ShelfView }, { path: '/add', component: { template: '<div />' } }] })
}

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('ShelfView', () => {
  it('expands on first touch, collapses outside, and opens details on second touch', async () => {
    vi.stubGlobal('ResizeObserver', ResizeObserverStub)
    vi.stubGlobal('IntersectionObserver', IntersectionObserverStub)
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true, addEventListener() {}, removeEventListener() {} })))
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({ ok: true, json: async () => ({ items: [card] }) } as Response)
    const router = makeRouter(); await router.push('/shelf/movie'); await router.isReady()
    const wrapper = mount(ShelfView, { global: { plugins: [router], stubs: { DraftForm: true } } })
    await flushPromises()
    const spine = wrapper.find('.book-spine')
    await spine.trigger('click')
    expect(spine.classes()).toContain('is-expanded')
    expect(wrapper.find('.edit-card-modal').exists()).toBe(false)
    await wrapper.find('.library-heading').trigger('click')
    expect(spine.classes()).not.toContain('is-expanded')
    await spine.trigger('click')
    await spine.trigger('click')
    await flushPromises()
    expect(wrapper.find('.edit-card-modal').exists()).toBe(true)
  })

  it('renders an independent category as hardcover spines on complete shelf layers', async () => {
    vi.stubGlobal('ResizeObserver', ResizeObserverStub)
    vi.stubGlobal('IntersectionObserver', IntersectionObserverStub)
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({ ok: true, json: async () => ({ items: [card] }) } as Response)
    const router = makeRouter()
    await router.push('/shelf/movie'); await router.isReady()
    const wrapper = mount(ShelfView, { global: { plugins: [router], stubs: { DraftForm: true } } })
    await flushPromises()
    expect(String(fetchMock.mock.calls[0][0])).toBe('/api/cards?category=movie')
    expect(wrapper.text()).toContain('电影书架')
    expect(wrapper.find('.shelf-track').exists()).toBe(false)
    expect(wrapper.find('.shelf-carcass').exists()).toBe(true)
    expect(wrapper.find('.shelf-back').exists()).toBe(true)
    expect(wrapper.findAll('.shelf-post')).toHaveLength(2)
    expect(wrapper.find('.spine-mark').text()).toBe('影')
    expect(wrapper.find('.expanded-poster').attributes('src')).toBe('/poster.jpg')
    await wrapper.find('.book-spine').trigger('click')
    await flushPromises()
    expect(wrapper.find('.edit-card-modal').exists()).toBe(true)
    expect(wrapper.find('.detail-drawer').exists()).toBe(false)
  })

  it('saves locally without reloading the list and restores the exact viewport', async () => {
    vi.stubGlobal('ResizeObserver', ResizeObserverStub)
    vi.stubGlobal('IntersectionObserver', IntersectionObserverStub)
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { callback(0); return 1 })
    Object.defineProperty(window, 'scrollY', { configurable: true, value: 420 })
    const scrollTo = vi.spyOn(window, 'scrollTo').mockImplementation(() => undefined)
    const saved = { ...card, title: '保存后的电影', updated_at: '2026-06-28' }
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, init) => ({
      ok: true,
      json: async () => init?.method === 'PATCH' ? saved : { items: [card] },
    } as Response))
    const router = makeRouter()
    await router.push('/shelf/movie'); await router.isReady()
    const wrapper = mount(ShelfView, { global: { plugins: [router], stubs: { DraftForm: true } } })
    await flushPromises()
    await wrapper.find('.book-spine').trigger('click')
    await wrapper.find('.modal-actions button:last-child').trigger('click')
    await flushPromises()
    expect(fetchMock.mock.calls.filter(call => String(call[0]).includes('/api/cards?category=movie'))).toHaveLength(1)
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'PATCH')).toHaveLength(1)
    expect(wrapper.find('.edit-card-modal').exists()).toBe(false)
    expect(wrapper.text()).toContain('保存后的电影')
    expect(scrollTo).toHaveBeenCalledWith({ top: 420, left: 0, behavior: 'auto' })
  })

  it('renders completed movies newest first and opens completion-first details', async () => {
    vi.stubGlobal('ResizeObserver', ResizeObserverStub)
    vi.stubGlobal('IntersectionObserver', IntersectionObserverStub)
    const completed = [
      { ...card, id: 'older', title: '较早完成', status: 'completed' as const, completed_at: '2026-05-01', rating: 7.5, review: '旧感想' },
      { ...card, id: 'newer', title: '最近完成', status: 'completed' as const, completed_at: '2026-06-20', rating: 9.3, review: '新感想', extension: { completed_at_inferred: true } },
    ]
    vi.spyOn(globalThis, 'fetch').mockResolvedValue({ ok: true, json: async () => ({ items: completed }) } as Response)
    const router = makeRouter(); await router.push('/shelf/movie'); await router.isReady()
    const wrapper = mount(ShelfView, { global: { plugins: [router], stubs: { DraftForm: true } } })
    await flushPromises()
    const artifacts = wrapper.findAll('.movie-archive')
    expect(artifacts).toHaveLength(2)
    expect(artifacts[0].text()).toContain('最近完成')
    await artifacts[0].trigger('click'); await flushPromises()
    expect(wrapper.find('.completion-hero').text()).toContain('9.3/10')
    expect(wrapper.find('.completion-hero').text()).toContain('推定日期')
    expect(wrapper.find('.completed-source-details').exists()).toBe(true)
  })
})
