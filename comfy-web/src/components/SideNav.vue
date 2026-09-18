<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { Brush, Film, FolderOpened, House, MagicStick, Moon, Picture, SwitchButton, VideoCamera } from '@element-plus/icons-vue'
import { getCurrentUserName } from '../utils/user'

const props = defineProps<{
  businessTheme: 'light' | 'dot' | 'black'
  showThemeToggle: boolean
}>()

const emit = defineEmits<{
  toggleTheme: []
}>()

const router = useRouter()
const route = useRoute()
const currentUserName = getCurrentUserName()

const themeMeta = computed(() => ({
  light: { icon: Brush, label: '光束主题' },
  dot: { icon: MagicStick, label: '点阵主题' },
  black: { icon: Moon, label: '纯黑主题' },
}[props.businessTheme]))

const navItems = [
  { path: '/', icon: House, label: '首页' },
  { path: '/image', icon: Picture, label: '图片生成' },
  { path: '/video', icon: VideoCamera, label: '视频生成' },
  { path: '/drama', icon: Film, label: '导演台' },
  { path: '/assets', icon: FolderOpened, label: '我的资产' },
]

function isActive(path: string) {
  if (path === '/') return route.path === '/'
  return route.path.startsWith(path)
}

async function handleLogout() {
  try {
    await ElMessageBox.confirm('退出后，需要重新登录才能继续使用。', '退出登录', {
      confirmButtonText: '退出登录',
      cancelButtonText: '继续使用',
      confirmButtonClass: 'logout-confirm-button',
      cancelButtonClass: 'logout-cancel-button',
      customClass: 'logout-confirm',
      type: 'warning',
      showClose: false,
      closeOnClickModal: false,
      autofocus: false,
    })

    localStorage.removeItem('token')
    localStorage.removeItem('user')
    router.push('/login')
  } catch {
    // 用户取消
  }
}

</script>

<template>
  <nav class="side-nav" aria-label="主导航">
    <div class="brand-section">
      <RouterLink class="nav-logo" to="/" aria-label="返回首页">
        <span class="brand-logo-viewport">
          <img class="brand-logo" src="/logo.svg" alt="若晴AI Studio" />
        </span>
      </RouterLink>
      <div v-if="currentUserName" class="brand-greeting" aria-live="polite">Hi！{{ currentUserName }}</div>
    </div>

    <ul class="nav-list">
      <li v-for="item in navItems" :key="item.path">
        <RouterLink
          :to="item.path"
          class="nav-item"
          :class="{ active: isActive(item.path) }"
          :aria-current="isActive(item.path) ? 'page' : undefined"
        >
          <span class="active-bar" aria-hidden="true" />
          <el-icon class="nav-icon" aria-hidden="true"><component :is="item.icon" /></el-icon>
          <span class="nav-label">{{ item.label }}</span>
        </RouterLink>
      </li>

      <!-- Gecko -->
      <li>
        <button
          type="button"
          class="nav-item gecko-item"
          @click="router.push('/gecko')"
        >
          <el-icon class="nav-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12 6 12 12 16 14"/>
            </svg>
          </el-icon>
          <span class="nav-label">Gecko</span>
        </button>
      </li>
    </ul>

    <div class="nav-footer">
      <button
        v-if="showThemeToggle"
        type="button"
        class="nav-item theme-item"
        :aria-label="themeMeta.label"
        :title="themeMeta.label"
        @click="emit('toggleTheme')"
      >
        <el-icon class="nav-icon" aria-hidden="true"><component :is="themeMeta.icon" /></el-icon>
        <span class="nav-label">{{ themeMeta.label }}</span>
      </button>
      <button type="button" class="nav-item logout-item" aria-label="退出登录" @click="handleLogout">
        <el-icon class="nav-icon" aria-hidden="true"><SwitchButton /></el-icon>
        <span class="nav-label">退出登录</span>
      </button>
    </div>
  </nav>
</template>

<style scoped>
.side-nav {
  position: fixed;
  left: 0;
  top: 0;
  height: 100vh;
  width: 64px;
  background: transparent;
  border-right: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 18px 8px;
  z-index: 100;
  overflow: hidden;
  transition:
    width 0.48s cubic-bezier(0.22, 1, 0.36, 1),
    background 0.4s ease;
  backdrop-filter: none;
  box-shadow: none;
}

.side-nav:hover,
.side-nav:has(:focus-visible) {
  width: 190px;
  align-items: flex-start;
  background: rgba(5, 7, 12, 0.74);
}

.nav-logo {
  width: 48px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  flex-shrink: 0;
  padding-left: 12px;
  border-radius: var(--radius-md);
}

.side-nav:hover .nav-logo,
.side-nav:has(:focus-visible) .nav-logo {
  width: 174px;
  padding-left: 12px;
  justify-content: flex-start;
}

.brand-logo-viewport {
  width: 30px;
  display: block;
  overflow: hidden;
  flex-shrink: 0;
  transition: width 0.48s cubic-bezier(0.22, 1, 0.36, 1);
}

.side-nav:hover .brand-logo-viewport,
.side-nav:has(:focus-visible) .brand-logo-viewport {
  width: 156px;
}

.brand-logo {
  width: 156px;
  height: auto;
  display: block;
  flex-shrink: 0;
}

.brand-section {
  width: 100%;
  flex-shrink: 0;
  margin-bottom: 16px;
}

.brand-greeting {
  width: 174px;
  padding: 0 12px;
  color: var(--color-muted);
  font-size: 12px;
  line-height: 18px;
  white-space: nowrap;
  opacity: 0;
  transform: translateX(-10px);
  overflow: hidden;
  pointer-events: none;
  transition: opacity 0.26s ease, transform 0.42s cubic-bezier(0.22, 1, 0.36, 1);
}

.side-nav:hover .brand-greeting,
.side-nav:has(:focus-visible) .brand-greeting {
  opacity: 1;
  transform: translateX(0);
  transition-delay: 0.14s;
}

.nav-list {
  list-style: none;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 0;
  margin: 0;
  flex: 1;
}

.nav-footer {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-top: 12px;
  border-top: 1px solid var(--color-border);
  margin-top: auto;
}

.theme-item:hover,
.theme-item:focus-visible {
  color: var(--color-primary);
}

.nav-item {
  position: relative;
  display: flex;
  align-items: center;
  height: 42px;
  width: 100%;
  padding: 0 12px;
  gap: 12px;
  border: 0;
  border-radius: var(--radius-md);
  background: transparent;
  color: var(--color-faint);
  cursor: pointer;
  text-decoration: none;
  white-space: nowrap;
  transition: color 0.2s, background 0.2s, transform 0.2s;
}

.nav-item:hover,
.nav-item:focus-visible {
  color: var(--color-text);
  background: rgba(255, 255, 255, 0.06);
  transform: translateX(2px);
}

.nav-item.active {
  color: var(--color-text);
  background: rgba(255, 255, 255, 0.1);
}

.logout-item {
  color: var(--color-faint);
}

.logout-item:hover,
.logout-item:focus-visible {
  color: var(--color-danger);
  background: rgba(248, 113, 113, 0.08);
}

:global(.logout-confirm.el-message-box) {
  width: min(380px, calc(100vw - 32px));
  max-width: 380px;
  padding: 0;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.13);
  border-radius: 16px;
  background: rgba(9, 12, 18, 0.92);
  backdrop-filter: blur(24px) saturate(130%);
  box-shadow: 0 28px 90px rgba(0, 0, 0, 0.58);
}

:global(.logout-confirm.el-message-box::before) {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 2px;
  background: #fb7185;
}

:global(.logout-confirm .el-message-box__header) {
  padding: 22px 22px 0;
}

:global(.logout-confirm .el-message-box__title) {
  color: rgba(255, 255, 255, 0.94);
  font-size: 16px;
  font-weight: 600;
}

:global(.logout-confirm .el-message-box__content) {
  padding: 14px 22px 22px;
  color: rgba(226, 232, 240, 0.56);
  font-size: 13px;
}

:global(.logout-confirm .el-message-box__container) {
  align-items: flex-start;
}

:global(.logout-confirm .el-message-box__status) {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: rgba(251, 113, 133, 0.1);
  color: #fb7185;
  font-size: 19px;
}

:global(.logout-confirm .el-message-box__message) {
  padding-top: 6px;
  line-height: 1.6;
}

:global(.logout-confirm .el-message-box__btns) {
  gap: 8px;
  padding: 14px 22px 18px;
  border-top: 1px solid rgba(255, 255, 255, 0.07);
}

:global(.logout-confirm .el-button) {
  height: 34px;
  margin-left: 0;
  padding: 0 15px;
  border-radius: 7px;
  font-size: 13px;
  transition: background 0.18s, border-color 0.18s, color 0.18s;
}

:global(.logout-confirm .logout-cancel-button) {
  border-color: rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.72);
}

:global(.logout-confirm .logout-cancel-button:hover),
:global(.logout-confirm .logout-cancel-button:focus-visible) {
  border-color: rgba(255, 255, 255, 0.24);
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.94);
}

:global(.logout-confirm .logout-confirm-button) {
  border-color: #e11d48;
  background: #e11d48;
  color: #fff;
}

:global(.logout-confirm .logout-confirm-button:hover),
:global(.logout-confirm .logout-confirm-button:focus-visible) {
  border-color: #f43f5e;
  background: #f43f5e;
  color: #fff;
}

.active-bar {
  position: absolute;
  left: -8px;
  top: 50%;
  transform: translateY(-50%);
  width: 2px;
  height: 20px;
  border-radius: 0 2px 2px 0;
  background: var(--color-primary);
  opacity: 0;
  transition: opacity 0.2s;
}

.nav-item.active .active-bar {
  opacity: 1;
}

.nav-icon {
  width: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 18px;
}

.nav-label {
  font-size: 13px;
  font-weight: 400;
  letter-spacing: 0;
  opacity: 0;
  transform: translateX(-6px);
  transition: opacity 0.22s ease, transform 0.32s cubic-bezier(0.22, 1, 0.36, 1);
  pointer-events: none;
}

.side-nav:hover .nav-label,
.side-nav:has(:focus-visible) .nav-label {
  opacity: 1;
  transform: translateX(0);
  transition-delay: 0.1s;
}

/* Gecko 样式 */
.gecko-item {
  margin-top: 8px;
  border: 1px solid rgba(96,165,250,0.3);
  background: rgba(96,165,250,0.08);
  color: #60a5fa;
}

.gecko-item:hover:not(:disabled),
.gecko-item:focus-visible:not(:disabled) {
  background: rgba(96,165,250,0.15);
  border-color: rgba(96,165,250,0.5);
}

@media (prefers-reduced-motion: reduce) {
  .side-nav,
  .nav-logo,
  .brand-logo-viewport,
  .brand-greeting {
    transition: none;
  }
}

</style>
