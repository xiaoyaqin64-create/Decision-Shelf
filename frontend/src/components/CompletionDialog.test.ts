import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CompletionDialog from './CompletionDialog.vue'

describe('CompletionDialog',()=>{
  it('submits a date, decimal ten-point score, review and optional minutes',async()=>{
    const wrapper=mount(CompletionDialog,{props:{title:'测试书',includeMinutes:true}})
    const inputs=wrapper.findAll('input')
    await inputs[0].setValue('2026-06-01')
    await inputs[1].setValue('8.7')
    await inputs[2].setValue('35')
    await wrapper.find('textarea').setValue('完成感想')
    await wrapper.find('.modal-actions button:last-child').trigger('click')
    expect(wrapper.emitted('submit')?.[0][0]).toEqual({completed_at:'2026-06-01',rating:8.7,review:'完成感想',final_minutes:35})
  })

  it('rejects scores with more than one decimal place',async()=>{
    const wrapper=mount(CompletionDialog,{props:{title:'测试电影'}})
    await wrapper.findAll('input')[1].setValue('9.15')
    await wrapper.find('.modal-actions button:last-child').trigger('click')
    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.text()).toContain('最多保留一位小数')
  })
})
