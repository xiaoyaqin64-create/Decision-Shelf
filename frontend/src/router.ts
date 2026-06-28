import { createRouter, createWebHashHistory } from 'vue-router'
import ShelfView from './views/ShelfView.vue'
import AddView from './views/AddView.vue'
import DecisionView from './views/DecisionView.vue'
import HistoryView from './views/HistoryView.vue'

export default createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', redirect: '/shelf/movie' },
    { path: '/shelf/:category(movie|book|album|game)', component: ShelfView },
    { path: '/add', component: AddView },
    { path: '/decide', component: DecisionView },
    { path: '/history', component: HistoryView },
  ],
})
