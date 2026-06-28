import { describe, expect, it } from 'vitest'
import router from './router'

describe('shelf routes',()=>{
  it('uses independent category pages instead of a shared shelf route',()=>{
    const paths=router.getRoutes().map(route=>route.path)
    expect(paths).toContain('/shelf/:category(movie|book|album|game)')
    expect(paths).not.toContain('/:category')
    expect(router.resolve('/shelf/book').matched).toHaveLength(1)
  })
})
