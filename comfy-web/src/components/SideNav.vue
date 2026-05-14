<script setup lang="ts">
import { useRouter, useRoute } from 'vue-router'
import { House, Picture, VideoCamera, FolderOpened, SwitchButton } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'

const router = useRouter()
const route = useRoute()

const navItems = [
  { path: '/',       icon: House,        label: '首页' },
  { path: '/image',  icon: Picture,      label: '图片生成' },
  { path: '/video',  icon: VideoCamera,  label: '视频生成' },
  { path: '/assets', icon: FolderOpened, label: '我的资产' },
  // { path: '/models', icon: Files,        label: '模型管理' },
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
  <nav class="side-nav">
    <!-- logo -->
    <div class="nav-logo">
      <span class="logo-dot" />
    </div>

    <!-- nav items -->
    <ul class="nav-list">
      <li
        v-for="item in navItems"
        :key="item.path"
        class="nav-item"
        :class="{ active: isActive(item.path) }"
        @click="router.push(item.path)"
      >
        <span class="active-bar" />
        <el-icon class="nav-icon"><component :is="item.icon" /></el-icon>
        <span class="nav-label">{{ item.label }}</span>
      </li>
    </ul>

    <!-- logout button -->
    <div class="nav-footer">
      <div class="nav-item logout-item" @click="handleLogout">
        <el-icon class="nav-icon"><SwitchButton /></el-icon>
        <span class="nav-label">退出登录</span>
      </div>
    </div>
  </nav>
</template>

<style scoped>
.side-nav {
  position: fixed;
  left: 0;
  top: 0;
  height: 100vh;
  width: 56px;
  background: rgba(255, 255, 255, 0.02);
  border-right: 1px solid rgba(255, 255, 255, 0.06);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 20px 0;
  z-index: 100;
  overflow: hidden;
  transition: width 0.25s ease;
  backdrop-filter: blur(12px);
}

.side-nav:hover {
  width: 180px;
  align-items: flex-start;
}

/* logo */
.nav-logo {
  width: 56px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-bottom: 16px;
}

.side-nav:hover .nav-logo {
  padding-left: 18px;
  justify-content: flex-start;
}

.logo-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #a78bfa;
  animation: pulse-dot 2.5s ease-in-out infinite;
  flex-shrink: 0;
}

/* list */
.nav-list {
  list-style: none;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 0;
  margin: 0;
  flex: 1;
}

/* footer */
.nav-footer {
  width: 100%;
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  margin-top: auto;
}

.logout-item {
  color: rgba(255, 255, 255, 0.35) !important;
}

.logout-item:hover {
  color: rgba(248, 113, 113, 0.85) !important;
  background: rgba(248, 113, 113, 0.08) !important;
}

/* item */
.nav-item {
  position: relative;
  display: flex;
  align-items: center;
  height: 44px;
  cursor: pointer;
  padding: 0 16px;
  gap: 12px;
  color: rgba(255, 255, 255, 0.4);
  transition: color 0.2s, background 0.2s;
  white-space: nowrap;
  border-radius: 0;
}

.nav-item:hover {
  color: rgba(255, 255, 255, 0.85);
  background: rgba(255, 255, 255, 0.04);
}

.nav-item.active {
  color: rgba(255, 255, 255, 0.95);
  background: rgba(108, 99, 255, 0.1);
}

/* active left bar */
.active-bar {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 2px;
  height: 20px;
  border-radius: 0 2px 2px 0;
  background: #a78bfa;
  opacity: 0;
  transition: opacity 0.2s;
}

.nav-item.active .active-bar {
  opacity: 1;
}

/* icon */
.nav-icon {
  font-size: 18px;
  flex-shrink: 0;
  width: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* label — hidden until nav expands */
.nav-label {
  font-size: 13px;
  font-weight: 400;
  letter-spacing: 0.3px;
  opacity: 0;
  transform: translateX(-6px);
  transition: opacity 0.2s ease, transform 0.2s ease;
  pointer-events: none;
}

.side-nav:hover .nav-label {
  opacity: 1;
  transform: translateX(0);
}
</style>
