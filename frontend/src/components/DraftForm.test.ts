import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import DraftForm from './DraftForm.vue'
import type { CardDraft } from '../types'

const draft: CardDraft = {
  category: 'book', title: '测试书', source: 'manual', external_id: null,
  description: '', image_url: null, duration_minutes: null, min_session_minutes: 25,
  tags: ['文学'], energy_level: 'medium', mood_fit: [], notes: '', priority: 3, extension: {},
}

describe('DraftForm', () => {
  it('emits editable title and normalized tags', async () => {
    const wrapper = mount(DraftForm, { props: { modelValue: draft } })
    const inputs = wrapper.findAll('input')
    await inputs[0].setValue('新的标题')
    const emitted = wrapper.emitted('update:modelValue') ?? []
    expect((emitted[0][0] as CardDraft).title).toBe('新的标题')

    const tagInput = wrapper.findAll('label').find((label) => label.text().startsWith('标签'))!.find('input')
    await tagInput.setValue('文学，经典、想象力')
    const latest = wrapper.emitted('update:modelValue')!.at(-1)![0] as CardDraft
    expect(latest.tags).toEqual(['文学', '经典', '想象力'])
  })
})
