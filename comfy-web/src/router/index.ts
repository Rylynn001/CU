import { createRouter, createWebHashHistory } from 'vue-router'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login', name: 'Login', component: () => import('../views/Login.vue'), meta: { public: true } },
    { path: '/', name: 'Workbench', component: () => import('../views/Workbench.vue') },
    { path: '/create', name: 'ProductionBoard', component: () => import('../views/ProductionBoard.vue') },
    { path: '/projects', name: 'Projects', component: () => import('../views/Projects.vue') },
    { path: '/projects/:id', name: 'ProjectDetail', component: () => import('../views/ProjectDetail.vue') },
    { path: '/image', name: 'TextToImage', component: () => import('../views/TextToImage.vue') },
    { path: '/video', name: 'TextToVideo', component: () => import('../views/TextToVideo.vue') },
    { path: '/models', name: 'ModelManager', component: () => import('../views/ModelManager.vue') },
    { path: '/developer', name: 'DeveloperPanel', component: () => import('../views/DeveloperPanel.vue') },
    { path: '/assets', redirect: '/' },
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
