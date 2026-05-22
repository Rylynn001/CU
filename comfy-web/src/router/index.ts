import { createRouter, createWebHashHistory } from 'vue-router'
import Home from '../views/Home.vue'
import TextToImage from '../views/TextToImage.vue'
import TextToVideo from '../views/TextToVideo.vue'
import ModelManager from '../views/ModelManager.vue'
import Assets from '../views/Assets.vue'
import Login from '../views/Login.vue'

const router = createRouter({
  // 使用 Hash 模式，避免服务器需要配置 history fallback
  history: createWebHashHistory(),
  routes: [
    { path: '/login',  component: Login,        meta: { public: true } }, // 登录页，不需要鉴权
    { path: '/',       component: Home },         // 首页
    { path: '/image',  component: TextToImage },  // 文生图 / 图生图
    { path: '/video',  component: TextToVideo },  // 文生视频 / 图生视频
    { path: '/models', component: ModelManager }, // 模型管理
    { path: '/assets', component: Assets },       // 我的资产库
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
