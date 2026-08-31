<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { Brush, Film, FolderOpened, House, MagicStick, Moon, Picture, SwitchButton, VideoCamera } from '@element-plus/icons-vue'

const props = defineProps<{
  businessTheme: 'light' | 'dot' | 'black'
  showThemeToggle: boolean
}>()

const emit = defineEmits<{
  toggleTheme: []
}>()

const router = useRouter()
const route = useRoute()

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
    await ElMessageBox.confirm('确定要退出登录吗？', '提示', {
      confirmButtonText: '退出',
      cancelButtonText: '取消',
      type: 'warning',
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
    <RouterLink class="nav-logo" to="/" aria-label="返回首页">
      <span class="logo-dot" aria-hidden="true" />
    </RouterLink>

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
  justify-content: center;
  flex-shrink: 0;
  margin-bottom: 16px;
  border-radius: var(--radius-md);
}

.side-nav:hover .nav-logo,
.side-nav:has(:focus-visible) .nav-logo {
  padding-left: 12px;
  justify-content: flex-start;
}

.logo-dot {
  width: 18px;
  height: 18px;
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.9);
  animation: pulse-dot 2.5s ease-in-out infinite;
  flex-shrink: 0;
  box-shadow: 0 0 24px rgba(255,255,255, 0.24);
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

@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.7; transform: scale(0.95); }
}

</style>
