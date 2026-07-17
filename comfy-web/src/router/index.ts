import { createRouter, createWebHashHistory } from 'vue-router'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login', name: 'Login', component: () => import('../views/Login.vue'), meta: { public: true } },
    { path: '/', name: 'Home', component: () => import('../views/Home.vue') },
    { path: '/image', name: 'TextToImage', component: () => import('../views/TextToImage.vue') },
    { path: '/video', name: 'TextToVideo', component: () => import('../views/TextToVideo.vue') },
    { path: '/node-panel', name: 'NodePanel', component: () => import('../views/NodePanel.vue') },
    { path: '/models', name: 'ModelManager', component: () => import('../views/ModelManager.vue') },
    { path: '/assets', name: 'Assets', component: () => import('../views/Assets.vue') },
    { path: '/drama', name: 'DramaList', component: () => import('../views/DramaList.vue') },
    { path: '/drama/:id', name: 'DramaDetail', component: () => import('../views/DramaDetail.vue') },
    { path: '/drama/:id/episode/:num', name: 'DramaStudio', component: () => import('../views/DramaStudio.vue') },
  ],
})

// 全局路由守卫：未登录访问业务页时跳转到登录页，已登录访问登录页时回到首页。
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')

  if (!token && !to.meta.public) {
    next('/login')
  } else if (token && to.path === '/login') {
    next('/')
  } else {
    next()
  }
})

export default router
