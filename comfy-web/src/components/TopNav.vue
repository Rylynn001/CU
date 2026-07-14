<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElIcon, ElMessageBox } from 'element-plus'
import { Box, Menu, Monitor, SwitchButton, User } from '@element-plus/icons-vue'
import { TOP_NOTICE_EVENT, type TopNoticeType } from '../utils/topNotice'

const route = useRoute()
const router = useRouter()
const root = ref<HTMLElement>()
const mobileOpen = ref(false)
const userOpen = ref(false)
const compactIndex = ref(0)
const latestNotice = ref('')
const latestNoticeType = ref<TopNoticeType>('info')
let compactTimer: ReturnType<typeof setInterval> | undefined
let noticeTimer: ReturnType<typeof setTimeout> | undefined
const navItems = [
  { path: '/', label: '工作台' },
  { path: '/create', label: '制作板' },
  { path: '/drama', label: '导演台' },
]
function isActive(path: string) { return path === '/' ? route.path === '/' : route.path.startsWith(path) }
const pageName = computed(() => {
  if (route.path === '/') return '工作台'
  if (route.path.startsWith('/projects')) return '项目'
  if (route.path.startsWith('/create')) return '制作板'
  if (route.path.startsWith('/image')) return '生成图片'
  if (route.path.startsWith('/video')) return '生成视频'
  if (route.path.startsWith('/drama')) return '导演台'
  if (route.path.startsWith('/models')) return '模型管理'
  if (route.path.startsWith('/developer')) return '开发者面板'
  return '灵枢 AI'
})
const compactItems = computed(() => ['RQVFX', pageName.value])
const compactIsNotice = computed(() => Boolean(latestNotice.value))
const compactText = computed(() => latestNotice.value || compactItems.value[compactIndex.value % compactItems.value.length])
function handleTopNotice(event: Event) {
  const detail = (event as CustomEvent<{ message?: string; type?: TopNoticeType; duration?: number }>).detail
  const message = detail?.message?.trim()
  if (!message) return
  latestNotice.value = message
  latestNoticeType.value = detail.type || 'info'
  clearTimeout(noticeTimer)
  noticeTimer = setTimeout(() => {
    latestNotice.value = ''
    compactIndex.value = 0
  }, detail.duration ?? 10000)
}
function getUserName() { try { return JSON.parse(localStorage.getItem('user') || 'null')?.username || '用户' } catch { return '用户' } }
function closeMenus() { mobileOpen.value = false; userOpen.value = false }
function handleOutside(event: PointerEvent) { if (!root.value?.contains(event.target as Node)) closeMenus() }
async function handleLogout() {
  try {
    await ElMessageBox.confirm('确定要退出登录吗？', '提示', { confirmButtonText: '退出', cancelButtonText: '取消', type: 'warning' })
    localStorage.removeItem('token'); localStorage.removeItem('user'); router.push('/login')
  } catch { /* 用户取消 */ }
}
watch(() => route.fullPath, () => {
  closeMenus()
  compactIndex.value = 1
  if (root.value?.contains(document.activeElement)) (document.activeElement as HTMLElement).blur()
})
onMounted(() => {
  document.addEventListener('pointerdown', handleOutside)
  compactTimer = setInterval(() => {
    if (!latestNotice.value) compactIndex.value = (compactIndex.value + 1) % compactItems.value.length
  }, 4500)
  window.addEventListener(TOP_NOTICE_EVENT, handleTopNotice)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleOutside)
  clearInterval(compactTimer)
  clearTimeout(noticeTimer)
  window.removeEventListener(TOP_NOTICE_EVENT, handleTopNotice)
})
</script>

<template>
  <header
    ref="root"
    class="top-nav"
    :class="[
      { open: mobileOpen || userOpen, 'notice-active': compactIsNotice },
      compactIsNotice ? 'notice-bar-' + latestNoticeType : '',
    ]"
  >
    <span class="compact-title" :class="[{ notice: compactIsNotice }, compactIsNotice ? 'notice-' + latestNoticeType : '']" aria-live="polite">
      <Transition name="compact-fade" mode="out-in">
        <span :key="compactText"><i v-if="compactIsNotice" />{{ compactText }}</span>
      </Transition>
    </span>
    <span class="compact-user" aria-hidden="true">{{ getUserName() }}</span>
    <RouterLink to="/" class="brand" aria-label="返回工作台"><span class="brand-mark" aria-hidden="true" /><span>灵枢 AI</span></RouterLink>
    <nav class="desktop-nav" aria-label="主导航">
      <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" :class="{ active: isActive(item.path) }" :aria-current="isActive(item.path) ? 'page' : undefined">{{ item.label }}</RouterLink>
    </nav>
    <div class="top-actions">
      <button type="button" class="icon-btn mobile-menu-btn" aria-label="打开导航菜单" @click="mobileOpen = !mobileOpen; userOpen = false"><el-icon><Menu /></el-icon></button>
      <button type="button" class="user-btn" :aria-expanded="userOpen" aria-label="打开用户菜单" @click="userOpen = !userOpen; mobileOpen = false"><el-icon><User /></el-icon><span>{{ getUserName() }}</span></button>
    </div>
    <nav v-if="mobileOpen" class="mobile-menu" aria-label="移动端导航"><RouterLink v-for="item in navItems" :key="item.path" :to="item.path" :class="{ active: isActive(item.path) }">{{ item.label }}</RouterLink></nav>
    <div v-if="userOpen" class="user-menu">
      <div class="user-summary"><span>当前用户</span><strong>{{ getUserName() }}</strong></div>
      <RouterLink to="/models"><el-icon><Box /></el-icon><span>模型管理</span></RouterLink>
      <RouterLink to="/developer"><el-icon><Monitor /></el-icon><span>开发者面板</span></RouterLink>
      <button type="button" @click="handleLogout"><el-icon><SwitchButton /></el-icon><span>退出登录</span></button>
    </div>
  </header>
</template>

<style scoped>
.top-nav { position:fixed; inset:0 0 auto 0; z-index:500; height:22px; padding:0 22px; display:grid; grid-template-columns:1fr auto 1fr; align-items:center; background:rgba(5,7,11,.42); border-bottom:1px solid rgba(255,255,255,.08); backdrop-filter:blur(24px) saturate(120%); -webkit-backdrop-filter:blur(24px) saturate(120%); transition:height .11s ease-out, background .11s ease-out, border-color .11s ease-out, backdrop-filter .11s ease-out; }
.top-nav:hover,.top-nav:focus-within,.top-nav.open { height:56px; background:rgba(5,7,11,.72); backdrop-filter:blur(32px) saturate(125%); -webkit-backdrop-filter:blur(32px) saturate(125%); }
.compact-title { position:absolute; left:50%; top:50%; width:min(360px,55vw); height:16px; transform:translate(-50%,-50%); overflow:hidden; color:rgba(255,255,255,.3); font-size:9px; font-weight:600; letter-spacing:.12em; line-height:16px; text-align:center; white-space:nowrap; text-overflow:ellipsis; transition:opacity .06s ease; }
.compact-title>span { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.compact-title.notice { letter-spacing:.04em; }
.compact-title.notice-success { color:rgba(114,214,160,.78); }
.compact-title.notice-warning { color:rgba(232,184,102,.82); }
.compact-title.notice-error { color:rgba(238,119,119,.82); }
.compact-title.notice-info { color:rgba(130,181,232,.8); }
.compact-title i { width:4px; height:4px; margin:0 6px 1px 0; display:inline-block; border-radius:50%; background:currentColor; box-shadow:0 0 7px currentColor; }
.compact-fade-enter-active,.compact-fade-leave-active { transition:opacity .45s ease; }
.compact-fade-enter-from,.compact-fade-leave-to { opacity:0; }
.top-nav.notice-active { box-shadow:inset 0 -1px var(--notice-line),0 5px 24px var(--notice-glow); }
.top-nav.notice-bar-success { --notice-line:rgba(114,214,160,.28); --notice-glow:rgba(56,160,105,.08); background:linear-gradient(90deg,rgba(5,7,11,.44),rgba(29,73,51,.52),rgba(5,7,11,.44)); }
.top-nav.notice-bar-warning { --notice-line:rgba(232,184,102,.3); --notice-glow:rgba(190,126,35,.09); background:linear-gradient(90deg,rgba(5,7,11,.44),rgba(78,58,25,.54),rgba(5,7,11,.44)); }
.top-nav.notice-bar-error { --notice-line:rgba(238,119,119,.3); --notice-glow:rgba(190,50,50,.09); background:linear-gradient(90deg,rgba(5,7,11,.44),rgba(77,31,35,.54),rgba(5,7,11,.44)); }
.top-nav.notice-bar-info { --notice-line:rgba(130,181,232,.28); --notice-glow:rgba(47,112,180,.08); background:linear-gradient(90deg,rgba(5,7,11,.44),rgba(30,55,82,.54),rgba(5,7,11,.44)); }
.compact-user { position:absolute; right:31px; top:50%; transform:translateY(-50%); max-width:140px; overflow:hidden; color:rgba(255,255,255,.28); font-size:10px; line-height:1; text-overflow:ellipsis; white-space:nowrap; transition:opacity .06s ease; }
.top-nav:hover .compact-title,.top-nav:hover .compact-user,.top-nav:focus-within .compact-title,.top-nav:focus-within .compact-user,.top-nav.open .compact-title,.top-nav.open .compact-user { opacity:0; }
.brand,.desktop-nav,.top-actions { height:34px; margin-top:11px; align-self:start; opacity:0; pointer-events:none; transition:opacity .07s ease-out; }
.top-nav:hover .brand,.top-nav:hover .desktop-nav,.top-nav:hover .top-actions,.top-nav:focus-within .brand,.top-nav:focus-within .desktop-nav,.top-nav:focus-within .top-actions,.top-nav.open .brand,.top-nav.open .desktop-nav,.top-nav.open .top-actions { opacity:1; pointer-events:auto; }
.brand { display:flex; align-items:center; gap:10px; color:#fff; text-decoration:none; font-size:14px; font-weight:600; }.brand-mark { width:17px; height:17px; border-radius:5px; background:rgba(255,255,255,.92); }
.desktop-nav { display:flex; align-items:center; gap:30px; }.desktop-nav a { position:relative; height:100%; display:flex; align-items:center; color:rgba(255,255,255,.42); text-decoration:none; font-size:13px; }.desktop-nav a:hover,.desktop-nav a.active { color:#fff; }.desktop-nav a.active::after { content:''; position:absolute; left:0; right:0; bottom:-11px; height:2px; background:var(--color-primary); }
.top-actions { justify-self:end; display:flex; align-items:center; gap:8px; }.icon-btn,.user-btn { height:34px; border:0; background:transparent; color:rgba(255,255,255,.48); cursor:pointer; }.icon-btn { width:34px; display:inline-flex; align-items:center; justify-content:center; border-radius:7px; }.icon-btn:hover,.user-btn:hover { color:#fff; background:rgba(255,255,255,.055); }.user-btn { padding:0 9px; display:flex; align-items:center; gap:7px; border-radius:7px; font-size:12px; }.mobile-menu-btn { display:none; }
.mobile-menu,.user-menu { position:absolute; top:48px; padding:8px; border:1px solid rgba(255,255,255,.09); border-radius:9px; background:#0c0f15; box-shadow:0 18px 50px rgba(0,0,0,.42); }.user-menu { right:18px; width:190px; }.mobile-menu { right:58px; width:180px; }
.mobile-menu a,.user-menu a,.user-menu button { width:100%; height:38px; padding:0 10px; display:flex; align-items:center; gap:9px; border:0; border-radius:6px; background:transparent; color:rgba(255,255,255,.66); text-decoration:none; font-size:12px; cursor:pointer; }.mobile-menu a:hover,.mobile-menu a.active,.user-menu a:hover,.user-menu button:hover { color:#fff; background:rgba(255,255,255,.06); }
.user-summary { padding:8px 10px 11px; margin-bottom:5px; border-bottom:1px solid rgba(255,255,255,.07); }.user-summary span { display:block; color:rgba(255,255,255,.3); font-size:10px; }.user-summary strong { display:block; margin-top:4px; font-size:12px; font-weight:500; }
@media (max-width:760px) { .top-nav { height:56px; padding:0 14px; grid-template-columns:1fr auto; }.compact-title,.compact-user { display:none; }.brand,.top-actions { opacity:1; pointer-events:auto; }.desktop-nav { display:none; }.mobile-menu-btn { display:inline-flex; }.user-btn span { display:none; } }
</style>
