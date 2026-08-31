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

// Gecko 初始化
const geckoInitializing = ref(false)
const geckoStatus = ref<{ success: boolean; name: string | null; id: string | null; department: string | null; ip: string | null } | null>(null)
const geckoDialogVisible = ref(false)
const geckoDialogMessage = ref('')

async function initGecko() {
  geckoInitializing.value = true
  try {
    const res = await fetch('/api/api-proxy/gecko/init', { method: 'POST' })
    const data = await res.json()
    geckoStatus.value = {
      success: data.success,
      name: data.name || null,
      id: data.id || null,
      department: data.department || null,
      ip: data.ip || null
    }
    geckoDialogMessage.value = data.success ? '' : (data.message || '请先登录Gecko')
    geckoDialogVisible.value = true
  } catch (e: any) {
    geckoStatus.value = { success: false, name: null, id: null, department: null, ip: null }
    geckoDialogMessage.value = '初始化失败'
    geckoDialogVisible.value = true
  } finally {
    geckoInitializing.value = false
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

      <!-- Gecko 初始化 -->
      <li>
        <button
          type="button"
          class="nav-item gecko-item"
          :class="{ 'gecko-success': geckoStatus?.success, 'gecko-error': geckoStatus && !geckoStatus.success }"
          :disabled="geckoInitializing"
          @click="initGecko"
        >
          <el-icon v-if="!geckoInitializing" class="nav-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/>
              <polyline points="12 6 12 12 16 14"/>
            </svg>
          </el-icon>
          <span v-else class="nav-icon">
            <span class="mini-spin-nav" />
          </span>
          <span class="nav-label">{{ geckoStatus?.success ? `Gecko: ${geckoStatus.name}` : 'Gecko初始化' }}</span>
        </button>
      </li>
    </ul>

    <el-dialog
      v-model="geckoDialogVisible"
      title="Gecko 初始化结果"
      width="360px"
      align-center
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="true"
    >
      <template v-if="geckoStatus?.success">
        <p class="gecko-dialog-warning">
          请仔细核对以下信息是否与您本人一致。如信息有误，请先检查当前登录的 Gecko 客户端账户是否为您本人的账户；若账户确认无误但信息仍不一致，请联系管理员处理。
        </p>
        <div class="gecko-dialog-info">
          <p><span class="gecko-info-label">姓名：</span><span class="gecko-info-value">{{ geckoStatus.name }}</span></p>
          <p><span class="gecko-info-label">部门：</span><span class="gecko-info-value">{{ geckoStatus.department }}</span></p>
          <p><span class="gecko-info-label">ID：</span><span class="gecko-info-value">{{ geckoStatus.id }}</span></p>
          <p><span class="gecko-info-label">IP：</span><span class="gecko-info-value">{{ geckoStatus.ip }}</span></p>
        </div>
      </template>
      <template v-else>
        <p class="gecko-dialog-warning">{{ geckoDialogMessage }}</p>
      </template>
      <template #footer>
        <button class="dlg-btn confirm" @click="geckoDialogVisible = false">我已确认</button>
      </template>
    </el-dialog>

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

/* Gecko 初始化样式 */
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

.gecko-item:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.gecko-item.gecko-success {
  border-color: rgba(34,197,94,0.4);
  background: rgba(34,197,94,0.12);
  color: #4ade80;
}

.gecko-item.gecko-error {
  border-color: rgba(244,63,94,0.4);
  background: rgba(244,63,94,0.12);
  color: #fb7185;
}

.mini-spin-nav {
  display: block;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 2px solid rgba(96,165,250,0.3);
  border-top-color: #60a5fa;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.7; transform: scale(0.95); }
}

.gecko-dialog-warning {
  color: #f56c6c;
  font-size: 13px;
  line-height: 1.6;
  margin: 0 0 12px;
}

.gecko-dialog-info {
  color: #ffffff;
  font-size: 13px;
  line-height: 1.8;
}

.gecko-dialog-info p {
  margin: 0;
}

.gecko-info-label {
  color: rgba(255, 255, 255, 0.6);
}

.gecko-info-value {
  color: #ffffff;
}

.dlg-btn {
  padding: 7px 20px;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.dlg-btn.confirm {
  background: rgba(255,255,255,0.12);
  border-color: rgba(255,255,255,0.24);
  color: rgba(255,255,255,0.95);
}

.dlg-btn.confirm:hover:not(:disabled) { background: rgba(255,255,255,0.18); }

</style>
