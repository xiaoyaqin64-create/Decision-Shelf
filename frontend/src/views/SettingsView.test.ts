import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import SettingsView from './SettingsView.vue'

afterEach(() => vi.restoreAllMocks())

function response(body: unknown): Response {
  return { ok: true, json: async () => body } as Response
}

describe('SettingsView', () => {
  it('shows configured state without exposing saved secrets', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(response({
      deepseek_configured: true,
      deepseek_base_url: 'https://api.deepseek.com',
      deepseek_model: 'deepseek-v4-flash',
      tmdb_configured: true,
      musicbrainz_contact: 'person@example.com',
      secret_storage: 'system',
    }))
    const wrapper = mount(SettingsView)
    await flushPromises()

    expect(wrapper.text()).toContain('已配置')
    const passwordInputs = wrapper.findAll('input[type="password"]')
    expect(passwordInputs).toHaveLength(2)
    expect((passwordInputs[0].element as HTMLInputElement).value).toBe('')
    expect((passwordInputs[1].element as HTMLInputElement).value).toBe('')
    expect(fetchMock).toHaveBeenCalledWith('/api/settings', expect.anything())
  })

  it('saves a new key, clears the form, and announces config refresh', async () => {
    const eventSpy = vi.spyOn(window, 'dispatchEvent')
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(response({
        deepseek_configured: false,
        deepseek_base_url: 'https://api.deepseek.com',
        deepseek_model: 'deepseek-v4-flash',
        tmdb_configured: false,
        musicbrainz_contact: '',
      }))
      .mockResolvedValueOnce(response({
        deepseek_configured: true,
        deepseek_base_url: 'https://api.deepseek.com',
        deepseek_model: 'deepseek-v4-flash',
        tmdb_configured: false,
        musicbrainz_contact: '',
      }))
    const wrapper = mount(SettingsView)
    await flushPromises()
    await wrapper.find('input[type="password"]').setValue('secret-value')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    const request = fetchMock.mock.calls[1][1] as RequestInit
    expect(JSON.parse(String(request.body)).deepseek_api_key).toBe('secret-value')
    expect((wrapper.find('input[type="password"]').element as HTMLInputElement).value).toBe('')
    expect(wrapper.text()).toContain('已立即生效')
    expect(eventSpy).toHaveBeenCalledWith(expect.objectContaining({ type: 'decision-shelf-config-changed' }))
  })

  it('removes a configured secret after confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(response({
        deepseek_configured: true,
        deepseek_base_url: 'https://api.deepseek.com',
        deepseek_model: 'deepseek-v4-flash',
        tmdb_configured: false,
        musicbrainz_contact: '',
      }))
      .mockResolvedValueOnce(response({
        deepseek_configured: false,
        deepseek_base_url: 'https://api.deepseek.com',
        deepseek_model: 'deepseek-v4-flash',
        tmdb_configured: false,
        musicbrainz_contact: '',
      }))
    const wrapper = mount(SettingsView)
    await flushPromises()
    await wrapper.find('.danger-text').trigger('click')
    await flushPromises()

    expect(fetchMock.mock.calls[1][0]).toBe('/api/settings/deepseek')
    expect((fetchMock.mock.calls[1][1] as RequestInit).method).toBe('DELETE')
  })
})
