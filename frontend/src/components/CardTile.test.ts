import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CardTile from './CardTile.vue'

describe('CardTile',()=>{
  it('keeps the collapsed spine category-colored and reserves the poster for expansion',async()=>{
    const card:any={id:'m1',category:'movie',title:'主题电影',status:'todo',image_url:'https://example/a.jpg',theme_color:'#334455',tags:['科幻'],mood_fit:['沉浸'],description:'简介',is_prioritized:false}
    const wrapper=mount(CardTile,{props:{card}})
    expect(wrapper.find('.spine-surface img').exists()).toBe(false)
    expect(wrapper.find('.expanded-poster').attributes('src')).toBe('https://example/a.jpg')
    expect(wrapper.attributes('style')).toContain('#583039')
    expect(wrapper.attributes('style')).toContain('#334455')
    await wrapper.trigger('click')
    expect(wrapper.emitted('open')).toHaveLength(1)
  })
})
