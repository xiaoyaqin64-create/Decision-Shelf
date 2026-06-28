import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import BatchImport from './BatchImport.vue'

afterEach(() => vi.restoreAllMocks())

function response(body: unknown): Response {
  return { ok: true, json: async () => body } as Response
}

function csvFile(content: string) {
  const file = new File([content], 'cards.csv', { type: 'text/csv' })
  Object.defineProperty(file, 'arrayBuffer', {
    value: async () => new TextEncoder().encode(content).buffer,
  })
  return file
}

async function upload(wrapper: ReturnType<typeof mount>, file: File) {
  const input = wrapper.find<HTMLInputElement>('input[type="file"]')
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
  await flushPromises()
}

describe('BatchImport', () => {
  it('previews, confirms an external candidate and imports with CSV values preserved', async () => {
    const calls: Array<{ url: string; body?: any }> = []
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      calls.push({ url, body: init?.body ? JSON.parse(String(init.body)) : undefined })
      if (url === '/api/cards/import/preview') return response({
        rows: [{
          row_number: 2,
          raw: { 分类: '电影', 标题: 'CSV 标题', 标签: '自定义' },
          draft: {
            category: 'movie', title: 'CSV 标题', source: 'manual', external_id: null,
            description: '', image_url: null, duration_minutes: null, min_session_minutes: null,
            tags: ['自定义'], energy_level: 'medium', mood_fit: [], notes: '', priority: 3, extension: {},
          },
          provided_fields: ['category', 'title', 'tags'], status: 'valid', errors: [], existing_card: null,
        }],
        summary: { total: 1, valid: 1, duplicate: 0, invalid: 0 }, warnings: [],
      })
      if (url.startsWith('/api/metadata/movie/search')) return response({ items: [{
        source: 'tmdb', external_id: '7', category: 'movie', title: '外部标题', subtitle: '导演',
        year: 2025, creators: [], image_url: null, description: '',
      }] })
      if (url.startsWith('/api/metadata/movie/draft')) return response({
        category: 'movie', title: '外部标题', source: 'tmdb', external_id: '7',
        description: '外部简介', image_url: null, duration_minutes: 100, min_session_minutes: null,
        tags: ['外部标签'], energy_level: 'low', mood_fit: ['放松'], notes: '', priority: 3, extension: {},
      })
      if (url === '/api/cards/import') return response({
        items: [{ row_number: 2, status: 'created', card: null, message: '' }],
        summary: { created: 1, skipped: 0, failed: 0 },
      })
      throw new Error(`Unexpected request: ${url}`)
    })

    const wrapper = mount(BatchImport, {
      props: { config: { metadata: { movie: { available: true } } } },
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await upload(wrapper, csvFile('分类,标题,标签\n电影,CSV 标题,自定义\n'))

    expect(wrapper.text()).toContain('请选择正确候选')
    expect(wrapper.find<HTMLButtonElement>('.import-submit button').element.disabled).toBe(true)
    await wrapper.findAll('.candidate-option')[0].trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('已匹配：外部标题')
    expect(wrapper.find<HTMLButtonElement>('.import-submit button').element.disabled).toBe(false)

    await wrapper.find<HTMLButtonElement>('.import-submit button').trigger('click')
    await flushPromises()
    const importCall = calls.find((call) => call.url === '/api/cards/import')!
    expect(importCall.body.items[0].draft).toMatchObject({
      title: 'CSV 标题', tags: ['自定义'], description: '外部简介', source: 'tmdb', external_id: '7',
    })
    expect(wrapper.text()).toContain('新增 1 张，跳过 0 张，失败 0 张')
  })

  it('keeps invalid and duplicate rows out of the submitted items', async () => {
    let submitted: any
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      if (url === '/api/cards/import/preview') return response({
        rows: [
          { row_number: 2, raw: {}, draft: null, provided_fields: [], status: 'invalid', errors: ['标题不能为空'], existing_card: null },
          { row_number: 3, raw: {}, draft: { category: 'game', title: '已有', source: 'manual', external_id: null, description: '', image_url: null, duration_minutes: null, min_session_minutes: null, tags: [], energy_level: 'medium', mood_fit: [], notes: '', priority: 3, extension: {} }, provided_fields: ['category', 'title'], status: 'duplicate', errors: ['重复'], existing_card: null },
          { row_number: 4, raw: {}, draft: { category: 'game', title: '新游戏', source: 'manual', external_id: null, description: '', image_url: null, duration_minutes: null, min_session_minutes: null, tags: [], energy_level: 'medium', mood_fit: [], notes: '', priority: 3, extension: {} }, provided_fields: ['category', 'title'], status: 'valid', errors: [], existing_card: null },
        ],
        summary: { total: 3, valid: 1, duplicate: 1, invalid: 1 }, warnings: [],
      })
      if (url === '/api/cards/import') {
        submitted = JSON.parse(String(init?.body))
        return response({ items: [], summary: { created: 1, skipped: 0, failed: 0 } })
      }
      throw new Error(`Unexpected request: ${url}`)
    })
    const wrapper = mount(BatchImport, {
      props: { config: { metadata: { game: { available: false } } } },
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await upload(wrapper, csvFile('分类,标题\n游戏,新游戏\n'))
    await wrapper.find<HTMLButtonElement>('.import-submit button').trigger('click')
    await flushPromises()
    expect(submitted.items).toHaveLength(1)
    expect(submitted.items[0].row_number).toBe(4)
  })
})
