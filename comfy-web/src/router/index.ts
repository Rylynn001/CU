import { createRouter, createWebHashHistory } from 'vue-router'
import Home from '../views/Home.vue'
import TextToImage from '../views/TextToImage.vue'
import TextToVideo from '../views/TextToVideo.vue'
import ModelManager from '../views/ModelManager.vue'
import Assets from '../views/Assets.vue'
import Login from '../views/Login.vue'
import DramaList from '../views/DramaList.vue'
import DramaDetail from '../views/DramaDetail.vue'
import DramaStudio from '../views/DramaStudio.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login',  component: Login,        meta: { public: true } },
    { path: '/',       component: Home },
    { path: '/image',  component: TextToImage },
    { path: '/video',  component: TextToVideo },
    { path: '/models', component: ModelManager },
    { path: '/assets', component: Assets },
    { path: '/drama',              component: DramaList },
    { path: '/drama/:id',          component: DramaDetail },
    { path: '/drama/:id/episode/:num', component: DramaStudio },
  ],
})

// 全局路由守卫：未登录时跳转到登录页；已登录时访问登录页跳转到首页
router.beforeEach((to, from, next) => {
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
