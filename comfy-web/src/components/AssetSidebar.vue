<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage, ElDialog, ElInput, ElImageViewer } from 'element-plus'
import { favoriteAsset, fetchHistoryByAsset } from '../api/apiService'
import { useLocateHistory } from '../composables/useLocateHistory'
import FavoriteHeart from './FavoriteHeart.vue'
import VideoPlayer from './VideoPlayer.vue'

interface Asset {
  id: number
  location: string
  asset_type?: string
  tag?: number
}

interface Category {
  id: number
  name: string
  assets: number[]
}

interface Project {
  id: number
  name: string
  categories: Category[]
}

const emit = defineEmits<{
  select: [asset: Asset]
}>()

const router = useRouter()
const route = useRoute()
const { requestLocateHistory } = useLocateHistory()

// ── 视图切换 ──────────────────────────────────────────────────────────────
const activeView = ref<'assets' | 'project'>('assets')

// ── 用户 ──────────────────────────────────────────────────────────────────
function getUser() {
  const s = localStorage.getItem('user')
  return s ? JSON.parse(s) : null
}

// ── 我的资产 ──────────────────────────────────────────────────────────────
const assets = ref<Asset[]>([])
const loading = ref(false)
const loadingMore = ref(false)
const activeFilter = ref<'all' | 'picture' | 'video'>('all')
// 收藏颜色筛选：0=不筛选，1=红，2=黄，3=绿，4=蓝
const favoriteTag = ref<0 | 1 | 2 | 3 | 4>(0)
const FAVORITE_COLORS: { tag: 1 | 2 | 3 | 4; color: string; label: string }[] = [
  { tag: 1, color: '#f43f5e', label: '红' },
  { tag: 2, color: '#eab308', label: '黄' },
  { tag: 3, color: '#22c55e', label: '绿' },
  { tag: 4, color: '#3b82f6', label: '蓝' },
]
const currentPage = ref(1)
const total = ref(0)
const PAGE_SIZE = 20
const hasMore = computed(() => assets.value.length < total.value)

async function loadAssets(assetType?: 'picture' | 'video') {
  const user = getUser()
  if (!user) return
  loading.value = true
  currentPage.value = 1
  try {
    let url = `/api/api-proxy/user/assets?user_id=${user.id}&page=1&page_size=${PAGE_SIZE}`
    if (assetType) url += `&asset_type=${assetType}`
    if (favoriteTag.value > 0) url += `&tag=${favoriteTag.value}`
    const res = await fetch(url)
    if (!res.ok) throw new Error()
    const data = await res.json()
    assets.value = data.assets || []
    total.value = data.total ?? 0
  } catch {
    ElMessage.error('加载资产失败')
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  const user = getUser()
  if (!user || loadingMore.value) return
  loadingMore.value = true
  const nextPage = currentPage.value + 1
  try {
    const assetType = activeFilter.value === 'all' ? undefined : activeFilter.value
    let url = `/api/api-proxy/user/assets?user_id=${user.id}&page=${nextPage}&page_size=${PAGE_SIZE}`
    if (assetType) url += `&asset_type=${assetType}`
    if (favoriteTag.value > 0) url += `&tag=${favoriteTag.value}`
    const res = await fetch(url)
    if (!res.ok) throw new Error()
    const data = await res.json()
    assets.value.push(...(data.assets || []))
    total.value = data.total ?? 0
    currentPage.value = nextPage
  } catch {
    ElMessage.error('加载失败')
  } finally {
    loadingMore.value = false
  }
}

function setFilter(f: 'all' | 'picture' | 'video') {
  activeFilter.value = f
  loadAssets(f === 'all' ? undefined : f)
}

// ── 项目管理 ──────────────────────────────────────────────────────────────
const projects = ref<Project[]>([])
const projectsLoading = ref(false)
const selectedProject = ref<Project | null>(null)
const selectedCategory = ref<Category | null>(null)
const categoryAssets = ref<Asset[]>([])
const categoryAssetsLoading = ref(false)

async function loadProjects() {
  const user = getUser()
  if (!user) return
  projectsLoading.value = true
  try {
    const res = await fetch(`/api/api-proxy/projects?user_id=${user.id}`)
    if (!res.ok) throw new Error()
    const data = await res.json()
    projects.value = data.projects || []
  } catch {
    ElMessage.error('加载项目失败')
  } finally {
    projectsLoading.value = false
  }
}

async function loadCategoryAssets(ids: number[]) {
  if (!ids.length) { categoryAssets.value = []; return }
  if (categoryAssetsLoading.value) return
  categoryAssetsLoading.value = true
  try {
    const res = await fetch('/api/api-proxy/assets/by-ids', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids }),
    })
    if (!res.ok) throw new Error()
    const data = await res.json()
    categoryAssets.value = data.assets || []
  } catch {
    categoryAssets.value = []
  } finally {
    categoryAssetsLoading.value = false
  }
}

async function selectCategory(cat: Category) {
  if (selectedCategory.value?.id === cat.id) return
  selectedCategory.value = cat
  await loadCategoryAssets(cat.assets)
}

function selectProject(p: Project) {
  if (selectedProject.value?.id === p.id) return
  selectedProject.value = p
  selectedCategory.value = null
  categoryAssets.value = []
  if (p.categories.length > 0) selectCategory(p.categories[0])
}

function switchToProjects() {
  activeView.value = 'project'
  if (!projects.value.length) loadProjects()
}

function switchToAssets() {
  activeView.value = 'assets'
}

// ── 新建项目 ──────────────────────────────────────────────────────────────
const showCreateProject = ref(false)
const newProjectName = ref('')
const creatingProject = ref(false)

async function confirmCreateProject() {
  const name = newProjectName.value.trim()
  if (!name) { ElMessage.warning('请输入项目名称'); return }
  const user = getUser()
  if (!user) return
  creatingProject.value = true
  try {
    const res = await fetch('/api/api-proxy/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: user.id, name }),
    })
    if (!res.ok) throw new Error()
    const data = await res.json()
    projects.value.push({ id: data.id, name: data.name, categories: [] })
    showCreateProject.value = false
    newProjectName.value = ''
  } catch {
    ElMessage.error('创建失败')
  } finally {
    creatingProject.value = false
  }
}

// ── 新建分类 ──────────────────────────────────────────────────────────────
const showCreateCategory = ref(false)
const newCategoryName = ref('')
const creatingCategory = ref(false)

async function confirmCreateCategory() {
  const name = newCategoryName.value.trim()
  if (!name) { ElMessage.warning('请输入分类名称'); return }
  if (!selectedProject.value) return
  creatingCategory.value = true
  try {
    const res = await fetch('/api/api-proxy/categories', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: selectedProject.value.id, name }),
    })
    if (!res.ok) throw new Error()
    const data = await res.json()
    selectedProject.value.categories.push({ id: data.id, name: data.name, assets: [] })
    showCreateCategory.value = false
    newCategoryName.value = ''
  } catch {
    ElMessage.error('创建失败')
  } finally {
    creatingCategory.value = false
  }
}

// ── 删除项目 / 分类 ───────────────────────────────────────────────────────
async function deleteProject(p: Project) {
  const user = getUser()
  if (!user) return
  try {
    await fetch(`/api/api-proxy/projects/${p.id}`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: user.id }),
    })
    projects.value = projects.value.filter(x => x.id !== p.id)
    if (selectedProject.value?.id === p.id) { selectedProject.value = null; selectedCategory.value = null; categoryAssets.value = [] }
  } catch {
    ElMessage.error('删除失败')
  }
}

async function deleteCategory(cat: Category) {
  try {
    await fetch(`/api/api-proxy/categories/${cat.id}`, { method: 'DELETE' })
    if (selectedProject.value) {
      selectedProject.value.categories = selectedProject.value.categories.filter(c => c.id !== cat.id)
    }
    if (selectedCategory.value?.id === cat.id) { selectedCategory.value = null; categoryAssets.value = [] }
  } catch {
    ElMessage.error('删除失败')
  }
}

// ── 重命名 ────────────────────────────────────────────────────────────────
const editingType = ref<'project' | 'category' | null>(null)
const editingId = ref<number | null>(null)
const editingName = ref('')

function startEdit(type: 'project' | 'category', id: number, name: string) {
  editingType.value = type; editingId.value = id; editingName.value = name
}
function cancelEdit() {
  editingType.value = null; editingId.value = null; editingName.value = ''
}
async function submitEdit() {
  const name = editingName.value.trim()
  if (!name) { cancelEdit(); return }
  const id = editingId.value!
  const type = editingType.value!
  const user = getUser()
  cancelEdit()
  try {
    if (type === 'project') {
      await fetch(`/api/api-proxy/projects/${id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: user.id, name }),
      })
      const p = projects.value.find(x => x.id === id)
      if (p) p.name = name
      if (selectedProject.value?.id === id) selectedProject.value.name = name
    } else {
      await fetch(`/api/api-proxy/categories/${id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
      if (selectedProject.value) {
        const cat = selectedProject.value.categories.find(c => c.id === id)
        if (cat) cat.name = name
      }
      if (selectedCategory.value?.id === id) selectedCategory.value.name = name
    }
  } catch {
    ElMessage.error('重命名失败')
  }
}

// ── 工具 ──────────────────────────────────────────────────────────────────
function getMediaUrl(location: string) {
  return `/api/api-proxy/output/${location.split(/[/\\]/).pop()}`
}
function isVideo(asset: Asset) {
  const ext = asset.location.split('.').pop()?.toLowerCase()
  return ['mp4', 'mov', 'avi', 'webm'].includes(ext || '')
}
function getThumb(asset: Asset) {
  return getMediaUrl(asset.location)
}

async function setFavorite(asset: Asset, tag: 0 | 1 | 2 | 3 | 4) {
  const user = getUser()
  if (!user) return
  try {
    await favoriteAsset(asset.id, user.id, tag)
    asset.tag = tag
    if (favoriteTag.value > 0 && tag !== favoriteTag.value) {
      assets.value = assets.value.filter(a => a.id !== asset.id)
    }
  } catch {
    ElMessage.error('操作失败')
  }
}

// ── 左键：查看图片 / 播放视频 ────────────────────────────────────────────
const showImageViewer = ref(false)
const previewUrl = ref('')
const showVideoPlayer = ref(false)
const activeVideoUrl = ref('')
const activeVideoId = ref<number | undefined>(undefined)

function handleAssetClick(asset: Asset) {
  if (isVideo(asset)) {
    activeVideoUrl.value = getMediaUrl(asset.location)
    activeVideoId.value = asset.id
    showVideoPlayer.value = true
  } else {
    previewUrl.value = getMediaUrl(asset.location)
    showImageViewer.value = true
  }
}

// ── 右键菜单：添加到素材 / 定位历史记录 ──────────────────────────────────
const contextMenu = ref<{ visible: boolean; x: number; y: number; asset: Asset | null }>({
  visible: false, x: 0, y: 0, asset: null,
})

function openContextMenu(e: MouseEvent, asset: Asset) {
  contextMenu.value = { visible: true, x: e.clientX, y: e.clientY, asset }
}
function closeContextMenu() {
  contextMenu.value.visible = false
}

function addToMaterial() {
  const asset = contextMenu.value.asset
  closeContextMenu()
  if (asset) emit('select', asset)
}

async function locateHistory() {
  const asset = contextMenu.value.asset
  closeContextMenu()
  if (!asset) return
  const user = getUser()
  if (!user) return
  try {
    const record = await fetchHistoryByAsset(asset.id, user.id)
    const targetPath = record.type?.includes('video') ? '/video' : '/image'
    requestLocateHistory(record)
    if (route.path !== targetPath) router.push(targetPath)
  } catch {
    ElMessage.error('未找到该资产对应的历史记录')
  }
}

onMounted(() => {
  loadAssets()
  window.addEventListener('click', closeContextMenu)
})
onUnmounted(() => {
  window.removeEventListener('click', closeContextMenu)
})
</script>

<template>
  <div class="asset-sidebar">
    <!-- ── 顶部 tab ── -->
    <div class="sidebar-tabs">
      <button class="stab" :class="{ active: activeView === 'assets' }" @click="switchToAssets">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
        我的资产
      </button>
      <button class="stab" :class="{ active: activeView === 'project' }" @click="switchToProjects">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
        项目管理
      </button>
    </div>

    <!-- ══════ 我的资产视图 ══════ -->
    <div v-if="activeView === 'assets'" class="view-wrap">
      <!-- 筛选栏 -->
      <div class="filter-row">
        <div class="chip-group">
          <button class="chip" :class="{ active: activeFilter === 'all' }" @click="setFilter('all')">全部</button>
          <button class="chip" :class="{ active: activeFilter === 'picture' }" @click="setFilter('picture')">图片</button>
          <button class="chip" :class="{ active: activeFilter === 'video' }" @click="setFilter('video')">视频</button>
        </div>
        <div class="fav-chip-group">
          <button
            v-for="c in FAVORITE_COLORS" :key="c.tag"
            class="fav-chip"
            :class="{ active: favoriteTag === c.tag }"
            :style="{ color: c.color }"
            :title="`${c.label}色收藏`"
            @click="favoriteTag = favoriteTag === c.tag ? 0 : c.tag; loadAssets(activeFilter === 'all' ? undefined : activeFilter)"
          >
            <svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
            </svg>
          </button>
        </div>
      </div>

      <!-- 加载中 -->
      <div v-if="loading" class="center-state">
        <div class="mini-spin" />
      </div>

      <!-- 空态 -->
      <div v-else-if="assets.length === 0" class="center-state">
        <p class="empty-hint">暂无资产</p>
      </div>

      <!-- 网格 -->
      <div v-else class="thumb-grid">
        <div
          v-for="asset in assets"
          :key="asset.id"
          class="thumb-item"
          @click="handleAssetClick(asset)"
          @contextmenu.prevent="openContextMenu($event, asset)"
          :title="asset.location.split(/[/\\]/).pop()"
        >
          <video v-if="isVideo(asset)" :src="getThumb(asset)" class="thumb-media" preload="metadata" />
          <img v-else :src="getThumb(asset)" class="thumb-media" loading="lazy" />
          <div v-if="isVideo(asset)" class="thumb-play">▶</div>
          <span class="thumb-fav-slot" @click.stop>
            <FavoriteHeart :tag="asset.tag || 0" :size="11" @change="(t) => setFavorite(asset, t)" />
          </span>
        </div>
      </div>

      <!-- 加载更多 -->
      <div v-if="assets.length > 0 && hasMore" class="load-more">
        <button class="load-more-btn" :disabled="loadingMore" @click="loadMore">
          {{ loadingMore ? '加载中...' : '加载更多' }}
        </button>
      </div>
    </div>

    <!-- ══════ 项目管理视图 ══════ -->
    <div v-else class="view-wrap">
      <!-- 未选择项目：项目列表 -->
      <template v-if="!selectedProject">
        <div class="proj-header">
          <span class="proj-title">项目</span>
          <button class="icon-btn" @click="showCreateProject = true" title="新建项目">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          </button>
        </div>

        <div v-if="projectsLoading" class="center-state"><div class="mini-spin" /></div>
        <div v-else-if="projects.length === 0" class="center-state"><p class="empty-hint">暂无项目</p></div>

        <div v-else class="proj-list">
          <div
            v-for="p in projects"
            :key="p.id"
            class="proj-item"
            @click="selectProject(p)"
          >
            <div class="proj-item-icon">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
            </div>
            <div class="proj-item-info">
              <template v-if="editingType === 'project' && editingId === p.id">
                <input class="inline-input" v-model="editingName" @blur="submitEdit" @keyup.enter="submitEdit" @keyup.esc="cancelEdit" @click.stop autofocus />
              </template>
              <template v-else>
                <span class="proj-item-name" @dblclick.stop="startEdit('project', p.id, p.name)">{{ p.name }}</span>
                <span class="proj-item-meta">{{ p.categories.length }} 个分类</span>
              </template>
            </div>
            <button class="del-btn" @click.stop="deleteProject(p)" title="删除">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
            </button>
          </div>
        </div>
      </template>

      <!-- 已选项目：分类 tab + 资产网格 -->
      <template v-else>
        <!-- 面包屑 -->
        <div class="proj-header">
          <button class="back-btn" @click="selectedProject = null; selectedCategory = null; categoryAssets = []">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
          </button>
          <span class="proj-title" style="flex:1">{{ selectedProject.name }}</span>
          <button class="icon-btn" @click="showCreateCategory = true" title="新建分类">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          </button>
        </div>

        <!-- 分类 chips -->
        <div v-if="selectedProject.categories.length > 0" class="cat-chips">
          <div
            v-for="cat in selectedProject.categories"
            :key="cat.id"
            class="cat-chip"
            :class="{ active: selectedCategory?.id === cat.id }"
            @click="selectCategory(cat)"
          >
            <template v-if="editingType === 'category' && editingId === cat.id">
              <input class="inline-input" v-model="editingName" @blur="submitEdit" @keyup.enter="submitEdit" @keyup.esc="cancelEdit" @click.stop autofocus />
            </template>
            <template v-else>
              <span @dblclick.stop="startEdit('category', cat.id, cat.name)">{{ cat.name }}</span>
              <span class="cat-count">{{ cat.assets.length }}</span>
              <span class="cat-del" @click.stop="deleteCategory(cat)">✕</span>
            </template>
          </div>
        </div>
        <div v-else class="center-state"><p class="empty-hint">暂无分类，点击 + 新建</p></div>

        <!-- 资产网格 -->
        <div v-if="categoryAssetsLoading" class="center-state"><div class="mini-spin" /></div>
        <div v-else-if="selectedCategory && categoryAssets.length === 0" class="center-state">
          <p class="empty-hint">该分类下暂无资产</p>
        </div>
        <div v-else-if="categoryAssets.length > 0" class="thumb-grid">
          <div
            v-for="asset in categoryAssets"
            :key="asset.id"
            class="thumb-item"
            @click="handleAssetClick(asset)"
            @contextmenu.prevent="openContextMenu($event, asset)"
            :title="asset.location.split(/[/\\]/).pop()"
          >
            <video v-if="isVideo(asset)" :src="getThumb(asset)" class="thumb-media" preload="metadata" />
            <img v-else :src="getThumb(asset)" class="thumb-media" loading="lazy" />
            <div v-if="isVideo(asset)" class="thumb-play">▶</div>
          </div>
        </div>
      </template>
    </div>

    <!-- 新建项目弹窗 -->
    <el-dialog v-model="showCreateProject" title="新建项目" width="320px" align-center>
      <el-input v-model="newProjectName" placeholder="项目名称" @keyup.enter="confirmCreateProject" autofocus />
      <template #footer>
        <button class="dlg-btn cancel" @click="showCreateProject = false">取消</button>
        <button class="dlg-btn confirm" :disabled="creatingProject" @click="confirmCreateProject">确认</button>
      </template>
    </el-dialog>

    <!-- 新建分类弹窗 -->
    <el-dialog v-model="showCreateCategory" title="新建分类" width="320px" align-center>
      <el-input v-model="newCategoryName" placeholder="分类名称" @keyup.enter="confirmCreateCategory" autofocus />
      <template #footer>
        <button class="dlg-btn cancel" @click="showCreateCategory = false">取消</button>
        <button class="dlg-btn confirm" :disabled="creatingCategory" @click="confirmCreateCategory">确认</button>
      </template>
    </el-dialog>

    <!-- 图片查看器 -->
    <el-image-viewer v-if="showImageViewer" :url-list="[previewUrl]" @close="showImageViewer = false" :hide-on-click-modal="true" />

    <!-- 视频播放器 -->
    <VideoPlayer :visible="showVideoPlayer" :src="activeVideoUrl" :asset-id="activeVideoId" @close="showVideoPlayer = false" />

    <!-- 右键菜单：添加到素材 / 定位历史记录 -->
    <Teleport to="body">
      <Transition name="ctx-menu">
        <div
          v-if="contextMenu.visible"
          class="context-menu"
          :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
          @click.stop
        >
          <div class="context-menu-item" @click="addToMaterial">
            <span class="context-menu-icon">＋</span>
            <span>添加到素材</span>
          </div>
          <div class="context-menu-item" @click="locateHistory">
            <span class="context-menu-icon">◎</span>
            <span>定位历史记录</span>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.asset-sidebar {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
  border-left: 1px solid rgba(255,255,255,0.06);
  background: rgba(255,255,255,0.015);
  backdrop-filter: blur(16px);
  overflow: hidden;
}

.view-wrap {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── 顶部 tab ── */
.sidebar-tabs {
  display: flex;
  flex-shrink: 0;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.stab {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 44px;
  background: none;
  border: none;
  color: rgba(255,255,255,0.35);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  border-bottom: 2px solid transparent;
}
.stab:hover { color: rgba(255,255,255,0.7); }
.stab.active {
  color: rgba(255,255,255,0.9);
  border-bottom-color: rgba(108,99,255,0.8);
  background: rgba(108,99,255,0.06);
}

/* ── 筛选栏 ── */
.filter-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 12px 8px;
  flex-shrink: 0;
  flex-wrap: wrap;
}
.chip-group { display: flex; gap: 4px; }
.chip {
  display: flex; align-items: center; gap: 4px;
  padding: 4px 10px;
  border-radius: 14px;
  border: 1px solid rgba(255,255,255,0.08);
  background: transparent;
  color: rgba(255,255,255,0.4);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
}
.chip:hover { border-color: rgba(108,99,255,0.35); color: rgba(255,255,255,0.75); }
.chip.active {
  background: rgba(108,99,255,0.2);
  border-color: rgba(108,99,255,0.6);
  color: rgba(255,255,255,0.95);
}

.fav-chip-group { display: flex; gap: 3px; }
.fav-chip {
  width: 22px; height: 22px;
  border-radius: 50%;
  border: 1px solid rgba(255,255,255,0.08);
  background: transparent;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  opacity: 0.5;
  transition: all 0.2s;
}
.fav-chip svg { fill: none; }
.fav-chip:hover { opacity: 0.85; transform: scale(1.1); }
.fav-chip.active {
  opacity: 1;
  background: color-mix(in srgb, currentColor 20%, transparent);
  border-color: currentColor;
}
.fav-chip.active svg { fill: currentColor; }

/* ── 缩略图网格 ── */
.thumb-grid {
  flex: 1;
  overflow-y: auto;
  padding: 8px 10px;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  grid-auto-rows: 80px;
  gap: 6px;
  align-content: start;
  min-height: 0;
}
.thumb-grid::-webkit-scrollbar { width: 4px; }
.thumb-grid::-webkit-scrollbar-track { background: transparent; }
.thumb-grid::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }

.thumb-item {
  position: relative;
  height: 100%;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.07);
  transition: border-color 0.2s, transform 0.15s;
}
.thumb-item:hover {
  border-color: rgba(108,99,255,0.5);
  transform: scale(1.03);
}
.thumb-item:hover .thumb-fav-slot,
.thumb-fav-slot:has(.favorited) { opacity: 1; }

.thumb-fav-slot {
  position: absolute;
  top: 3px; right: 3px;
  z-index: 2;
  opacity: 0;
  transition: opacity 0.2s;
}

.thumb-media {
  width: 100%; height: 100%;
  object-fit: cover;
  display: block;
}
.thumb-play {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 16px; color: rgba(255,255,255,0.85);
  background: rgba(0,0,0,0.3);
  pointer-events: none;
}

/* ── 加载更多 ── */
.load-more {
  flex-shrink: 0;
  padding: 8px 10px 12px;
  display: flex;
  justify-content: center;
}
.load-more-btn {
  padding: 6px 20px;
  border-radius: 8px;
  border: 1px solid rgba(108,99,255,0.3);
  background: rgba(108,99,255,0.08);
  color: rgba(255,255,255,0.6);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.load-more-btn:hover:not(:disabled) { background: rgba(108,99,255,0.2); color: #fff; }
.load-more-btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── 项目列表 ── */
.proj-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px 8px;
  flex-shrink: 0;
}
.proj-title {
  font-size: 11px;
  color: rgba(255,255,255,0.3);
  letter-spacing: 1px;
  text-transform: uppercase;
  flex-shrink: 0;
}
.back-btn {
  width: 24px; height: 24px;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.1);
  background: transparent;
  color: rgba(255,255,255,0.5);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s;
}
.back-btn:hover { background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.9); }

.icon-btn {
  width: 22px; height: 22px;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.1);
  background: transparent;
  color: rgba(255,255,255,0.4);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s;
}
.icon-btn:hover { background: rgba(108,99,255,0.2); border-color: rgba(108,99,255,0.5); color: rgba(255,255,255,0.9); }

.proj-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 8px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.proj-list::-webkit-scrollbar { width: 4px; }
.proj-list::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }

.proj-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 10px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}
.proj-item:hover {
  background: rgba(108,99,255,0.08);
  border-color: rgba(108,99,255,0.2);
}
.proj-item-icon {
  width: 32px; height: 32px;
  border-radius: 8px;
  background: rgba(108,99,255,0.12);
  display: flex; align-items: center; justify-content: center;
  color: rgba(167,139,250,0.7);
  flex-shrink: 0;
}
.proj-item-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.proj-item-name {
  font-size: 13px;
  color: rgba(255,255,255,0.8);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.proj-item-meta {
  font-size: 11px;
  color: rgba(255,255,255,0.25);
}
.del-btn {
  width: 20px; height: 20px;
  border-radius: 4px;
  border: none;
  background: transparent;
  color: rgba(255,255,255,0.2);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
  opacity: 0;
  transition: all 0.2s;
}
.proj-item:hover .del-btn { opacity: 1; }
.del-btn:hover { background: rgba(244,63,94,0.15); color: #f43f5e; }

/* ── 分类 chips ── */
.cat-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 6px 10px 8px;
  flex-shrink: 0;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}
.cat-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 14px;
  border: 1px solid rgba(255,255,255,0.08);
  background: transparent;
  color: rgba(255,255,255,0.45);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
}
.cat-chip:hover { border-color: rgba(167,139,250,0.4); color: rgba(255,255,255,0.8); }
.cat-chip.active {
  background: rgba(167,139,250,0.18);
  border-color: rgba(167,139,250,0.55);
  color: rgba(255,255,255,0.95);
}
.cat-count {
  font-size: 10px;
  background: rgba(255,255,255,0.08);
  padding: 1px 5px;
  border-radius: 8px;
  color: rgba(255,255,255,0.35);
}
.cat-chip.active .cat-count { background: rgba(167,139,250,0.2); color: rgba(167,139,250,0.9); }
.cat-del {
  font-size: 10px;
  color: rgba(255,255,255,0.2);
  opacity: 0;
  transition: all 0.15s;
  margin-left: 1px;
}
.cat-chip:hover .cat-del { opacity: 1; }
.cat-del:hover { color: #f43f5e; }

/* ── 状态 ── */
.center-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 10px;
  padding: 32px 0;
}
.empty-hint {
  font-size: 12px;
  color: rgba(255,255,255,0.2);
  letter-spacing: 1px;
}
.mini-spin {
  width: 24px; height: 24px;
  border-radius: 50%;
  border: 2px solid rgba(108,99,255,0.3);
  border-top-color: rgba(108,99,255,0.9);
  animation: spin 0.8s linear infinite;
}

/* ── 内联编辑 ── */
.inline-input {
  background: rgba(108,99,255,0.15);
  border: 1px solid rgba(108,99,255,0.5);
  border-radius: 5px;
  color: rgba(255,255,255,0.9);
  font-size: 12px;
  padding: 2px 6px;
  outline: none;
  width: 100px;
}

/* ── 弹窗按钮 ── */
.dlg-btn {
  padding: 7px 20px;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}
.dlg-btn.cancel {
  background: rgba(255,255,255,0.04);
  border-color: rgba(255,255,255,0.1);
  color: rgba(255,255,255,0.5);
  margin-right: 8px;
}
.dlg-btn.cancel:hover { background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.8); }
.dlg-btn.confirm {
  background: rgba(108,99,255,0.3);
  border-color: rgba(108,99,255,0.6);
  color: rgba(255,255,255,0.95);
}
.dlg-btn.confirm:hover:not(:disabled) { background: rgba(108,99,255,0.45); }
.dlg-btn.confirm:disabled { opacity: 0.5; cursor: not-allowed; }

@keyframes spin { to { transform: rotate(360deg); } }

/* ── 右键菜单 ── */
.context-menu {
  position: fixed;
  z-index: 3000;
  min-width: 140px;
  padding: 5px;
  border-radius: 10px;
  background: rgba(30,30,36,0.95);
  border: 1px solid rgba(255,255,255,0.1);
  box-shadow: 0 8px 24px rgba(0,0,0,0.4);
  backdrop-filter: blur(12px);
  transform-origin: top left;
}
.context-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 12px;
  color: rgba(255,255,255,0.85);
  cursor: pointer;
  transition: background 0.15s;
}
.context-menu-item:hover { background: rgba(108,99,255,0.25); }
.context-menu-item .context-menu-icon {
  font-size: 13px;
  color: rgba(167,139,250,0.9);
  font-weight: 400;
  line-height: 1;
}

.ctx-menu-enter-active { transition: opacity 0.15s ease, transform 0.15s ease; }
.ctx-menu-leave-active { transition: opacity 0.1s ease, transform 0.1s ease; }
.ctx-menu-enter-from,
.ctx-menu-leave-to {
  opacity: 0;
  transform: scale(0.92);
}
</style>
