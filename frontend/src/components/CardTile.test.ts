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

  it('shows completion date, ten-point score and review for completed books',()=>{
    const card:any={id:'b1',category:'book',title:'完成之书',status:'completed',image_url:null,theme_color:'#334455',tags:['经典'],mood_fit:['沉浸'],description:'不应展示的简介',is_prioritized:false,completed_at:'2026-06-18',rating:8.6,review:'读完之后仍有余味'}
    const wrapper=mount(CardTile,{props:{card}})
    expect(wrapper.find('.completed-spine-copy').text()).toContain('8.6/10')
    expect(wrapper.find('.completed-spine-copy').text()).toContain('读完之后仍有余味')
    expect(wrapper.find('.completed-spine-copy').text()).not.toContain('不应展示的简介')
  })

  it('expands on the first touch and opens on the second touch',async()=>{
    const card:any={id:'m2',category:'movie',title:'触屏电影',status:'todo',image_url:null,theme_color:'#334455',tags:[],mood_fit:[],description:'',is_prioritized:false}
    const wrapper=mount(CardTile,{props:{card,touchMode:true,expanded:false}})
    await wrapper.trigger('click')
    expect(wrapper.emitted('expand')).toHaveLength(1)
    expect(wrapper.emitted('open')).toBeUndefined()
    await wrapper.setProps({expanded:true})
    await wrapper.trigger('click')
    expect(wrapper.emitted('open')).toHaveLength(1)
  })
})
