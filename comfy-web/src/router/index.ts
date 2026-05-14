import { createRouter, createWebHashHistory } from 'vue-router'
import Home from '../views/Home.vue'
import TextToImage from '../views/TextToImage.vue'
import TextToVideo from '../views/TextToVideo.vue'
import ModelManager from '../views/ModelManager.vue'
import Assets from '../views/Assets.vue'
import Login from '../views/Login.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login',  component: Login, meta: { public: true } },
    { path: '/',       component: Home },
    { path: '/image',  component: TextToImage },
    { path: '/video',  component: TextToVideo },
    { path: '/models', component: ModelManager },
    { path: '/assets', component: Assets },
  ],
})

// 路由守卫：未登录跳转到登录页
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
