import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CompletedCollection from './CompletedCollection.vue'

const base:any={id:'done',title:'完成作品',status:'completed',image_url:'/cover.jpg',completed_at:'2026-06-20',rating:9.2,review:'值得收藏',extension:{}}

describe('CompletedCollection',()=>{
  it('renders movie posters, album vinyl and game discs',async()=>{
    const movie=mount(CompletedCollection,{props:{category:'movie',cards:[{...base,category:'movie'}]}})
    expect(movie.find('.movie-poster').exists()).toBe(true)
    expect(movie.text()).toContain('9.2/10')
    await movie.find('.completed-artifact').trigger('click')
    expect(movie.emitted('open')?.[0][0]).toMatchObject({id:'done'})

    const album=mount(CompletedCollection,{props:{category:'album',cards:[{...base,category:'album'}]}})
    expect(album.find('.vinyl-disc').exists()).toBe(true)
    expect(album.find('.album-sleeve img').attributes('src')).toBe('/cover.jpg')

    const game=mount(CompletedCollection,{props:{category:'game',cards:[{...base,category:'game'}]}})
    expect(game.find('.game-disc').exists()).toBe(true)
    expect(game.text()).toContain('值得收藏')
  })

  it('keeps long titles complete and places them below each artifact',()=>{
    const movieTitle='一部拥有非常非常长中文标题的电影作品'
    const albumTitle='The Dark Side of the Moon Anniversary Edition'
    const gameTitle='OuterWildsEchoesOfTheEyeWithoutSpaces'

    const movie=mount(CompletedCollection,{props:{category:'movie',cards:[{...base,category:'movie',title:movieTitle}]}})
    expect(movie.find('.artifact-title').text()).toBe(movieTitle)
    expect(movie.find('.movie-archive').element.children[0].classList.contains('movie-poster')).toBe(true)
    expect(movie.find('.movie-archive').element.children[1].querySelector('.artifact-title')?.textContent).toBe(movieTitle)

    const album=mount(CompletedCollection,{props:{category:'album',cards:[{...base,category:'album',title:albumTitle}]}})
    const albumVisual=album.find('.artifact-visual')
    expect(albumVisual.element.children[0].classList.contains('vinyl-stage')).toBe(true)
    expect(albumVisual.element.children[1].classList.contains('artifact-title')).toBe(true)
    expect(albumVisual.find('.artifact-title').text()).toBe(albumTitle)
    expect(album.find('.artifact-copy').text()).not.toContain(albumTitle)

    const game=mount(CompletedCollection,{props:{category:'game',cards:[{...base,category:'game',title:gameTitle}]}})
    const gameVisual=game.find('.artifact-visual')
    expect(gameVisual.element.children[0].classList.contains('game-disc')).toBe(true)
    expect(gameVisual.element.children[1].classList.contains('artifact-title')).toBe(true)
    expect(gameVisual.find('.artifact-title').text()).toBe(gameTitle)
    expect(game.find('.artifact-copy').text()).not.toContain(gameTitle)
  })
})
