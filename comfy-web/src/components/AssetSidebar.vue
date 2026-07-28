<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage, ElDialog, ElInput } from 'element-plus'
import { favoriteAsset, fetchHistoryByAsset } from '../api/apiService'
import FavoriteHeart from './FavoriteHeart.vue'
import VideoPlayer from './VideoPlayer.vue'
import ImageViewer from './ImageViewer.vue'
import ProjectManager from './ProjectManager.vue'
import ConfirmDialog from './ConfirmDialog.vue'

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

interface HistoryRecord {
  id: number
  task_id?: string
  prompt: string
  mode?: string
  status?: string
  type?: string
  message?: string
  model_name?: string
  model_id?: number
  output_urls: Array<{ url: string; type: string; id?: number }>
  input_asset_ids: number[]
  input_asset_urls: Array<{ url: string; type: string }>
  payload?: any
}

const emit = defineEmits<{
  select: [asset: Asset]
  reuseParams: [record: HistoryRecord]
}>()

// ── 视图切换 ──────────────────────────────────────────────────────────────
const activeView = ref<'assets' | 'project'>('assets')

// ── 用户 ──────────────────────────────────────────────────────────────────
function getUser() {
  const s = localStorage.getItem('user')
  return s ? JSON.parse(s) : null
}

// ── 添加到项目弹窗 ────────────────────────────────────────────────────────
const showProjectManager = ref(false)
const currentAssetIdForProject = ref<number | undefined>(undefined)

function openAddToProjectDialog(asset: Asset) {
  currentAssetIdForProject.value = asset.id
  showProjectManager.value = true
}

function handleProjectManagerClose() {
  showProjectManager.value = false
  currentAssetIdForProject.value = undefined
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
const PAGE_SIZE = 30
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
  await fillIfNotScrollable()
}

const thumbGridRef = ref<HTMLElement | null>(null)

// 内容没撑满容器时无法触发 scroll 事件，需主动补齐到出现滚动条或数据加载完
async function fillIfNotScrollable() {
  await nextTick()
  const el = thumbGridRef.value
  if (!el || loadingMore.value || !hasMore.value) return
  if (el.scrollHeight <= el.clientHeight) {
    await loadMore()
  }
}

function handleThumbGridScroll() {
  const el = thumbGridRef.value
  if (!el || loadingMore.value || !hasMore.value) return
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 150) {
    loadMore()
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
  await fillIfNotScrollable()
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
    projects.value.push({ id: data.id, name: data.name, categories: data.categories || [] })
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
// 确认弹窗状态
const showDeleteConfirm = ref(false)
const deleteConfirmLoading = ref(false)
const deleteTarget = ref<{ type: 'project' | 'category'; data: Project | Category } | null>(null)

function confirmDeleteProject(p: Project) {
  deleteTarget.value = { type: 'project', data: p }
  showDeleteConfirm.value = true
}

function confirmDeleteCategory(cat: Category) {
  deleteTarget.value = { type: 'category', data: cat }
  showDeleteConfirm.value = true
}

async function handleDeleteConfirm() {
  if (!deleteTarget.value) return
  deleteConfirmLoading.value = true

  try {
    if (deleteTarget.value.type === 'project') {
      await deleteProject(deleteTarget.value.data as Project)
    } else {
      await deleteCategory(deleteTarget.value.data as Category)
    }
    showDeleteConfirm.value = false
  } catch (e) {
    // 错误已在 deleteProject/deleteCategory 中处理
  } finally {
    deleteConfirmLoading.value = false
    deleteTarget.value = null
  }
}

function handleDeleteCancel() {
  showDeleteConfirm.value = false
  deleteTarget.value = null
  deleteConfirmLoading.value = false
}

async function deleteProject(p: Project) {
  const user = getUser()
  if (!user) return
  await fetch(`/api/api-proxy/projects/${p.id}`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: user.id }),
  })
  projects.value = projects.value.filter(x => x.id !== p.id)
  if (selectedProject.value?.id === p.id) { selectedProject.value = null; selectedCategory.value = null; categoryAssets.value = [] }
  ElMessage.success('删除成功')
}

async function deleteCategory(cat: Category) {
  await fetch(`/api/api-proxy/categories/${cat.id}`, { method: 'DELETE' })
  if (selectedProject.value) {
    selectedProject.value.categories = selectedProject.value.categories.filter(c => c.id !== cat.id)
  }
  if (selectedCategory.value?.id === cat.id) { selectedCategory.value = null; categoryAssets.value = [] }
  ElMessage.success('删除成功')
}

async function removeAssetFromCategory(asset: Asset) {
  if (!selectedCategory.value) return
  try {
    const res = await fetch(`/api/api-proxy/categories/${selectedCategory.value.id}/assets/${asset.id}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error()
    // 从当前分类的资产列表中移除
    selectedCategory.value.assets = selectedCategory.value.assets.filter(id => id !== asset.id)
    categoryAssets.value = categoryAssets.value.filter(a => a.id !== asset.id)
    ElMessage.success('已移除')
  } catch {
    ElMessage.error('移除失败')
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
const currentAssetIndex = ref(0)

// 获取当前视图的资产列表
const currentAssetList = computed(() => {
  return activeView.value === 'assets' ? assets.value : categoryAssets.value
})

function handleAssetClick(asset: Asset) {
  const index = currentAssetList.value.findIndex(a => a.id === asset.id)
  if (index !== -1) currentAssetIndex.value = index

  if (isVideo(asset)) {
    activeVideoUrl.value = getMediaUrl(asset.location)
    activeVideoId.value = asset.id
    showVideoPlayer.value = true
  } else {
    previewUrl.value = getMediaUrl(asset.location)
    showImageViewer.value = true
  }
}

// 切换到上一个资产
function goToPrev() {
  if (currentAssetList.value.length === 0) return
  currentAssetIndex.value = (currentAssetIndex.value - 1 + currentAssetList.value.length) % currentAssetList.value.length
  const asset = currentAssetList.value[currentAssetIndex.value]

  if (isVideo(asset)) {
    showImageViewer.value = false
    activeVideoUrl.value = getMediaUrl(asset.location)
    activeVideoId.value = asset.id
    showVideoPlayer.value = true
  } else {
    showVideoPlayer.value = false
    previewUrl.value = getMediaUrl(asset.location)
    showImageViewer.value = true
  }
}

// 切换到下一个资产
function goToNext() {
  if (currentAssetList.value.length === 0) return
  currentAssetIndex.value = (currentAssetIndex.value + 1) % currentAssetList.value.length
  const asset = currentAssetList.value[currentAssetIndex.value]

  if (isVideo(asset)) {
    showImageViewer.value = false
    activeVideoUrl.value = getMediaUrl(asset.location)
    activeVideoId.value = asset.id
    showVideoPlayer.value = true
  } else {
    showVideoPlayer.value = false
    previewUrl.value = getMediaUrl(asset.location)
    showImageViewer.value = true
  }
}

// 键盘事件监听
function handleKeydown(e: KeyboardEvent) {
  if (!showImageViewer.value && !showVideoPlayer.value) return

  if (e.key === 'ArrowLeft') {
    e.preventDefault()
    goToPrev()
  } else if (e.key === 'ArrowRight') {
    e.preventDefault()
    goToNext()
  } else if (e.key === 'Escape') {
    e.preventDefault()
    showImageViewer.value = false
    showVideoPlayer.value = false
  }
}

// ── 右键菜单：添加到素材 / 查看生成记录 ──────────────────────────────────
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
  if (asset) emit('select', [asset])
}

// ── 拖拽发起：将资产数据写入 dataTransfer，供拖放目标读取 ──────────────────
function handleDragStart(e: DragEvent, asset: Asset) {
  e.dataTransfer?.setData('application/json', JSON.stringify(asset))
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'copy'
}

// ── 查看生成记录弹窗 ──────────────────────────────────────────────────────
const showRecordDetail = ref(false)
const recordDetail = ref<HistoryRecord | null>(null)
const loadingRecord = ref(false)

async function viewGenerationRecord() {
  const asset = contextMenu.value.asset
  closeContextMenu()
  if (!asset) return
  const user = getUser()
  if (!user) return

  loadingRecord.value = true
  try {
    const record = await fetchHistoryByAsset(asset.id, user.id)
    recordDetail.value = record
    showRecordDetail.value = true
  } catch {
    ElMessage.error('未找到该资产对应的生成记录')
  } finally {
    loadingRecord.value = false
  }
}

function closeRecordDetail() {
  showRecordDetail.value = false
  setTimeout(() => {
    recordDetail.value = null
  }, 300)
}

function reuseRecordParams() {
  if (recordDetail.value) {
    emit('reuseParams', recordDetail.value)
    closeRecordDetail()
    ElMessage.success('参数已复用到左侧面板')
  }
}

onMounted(() => {
  loadAssets()
  window.addEventListener('click', closeContextMenu)
  window.addEventListener('keydown', handleKeydown)
})
onUnmounted(() => {
  window.removeEventListener('click', closeContextMenu)
  window.removeEventListener('keydown', handleKeydown)
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
      <div v-else ref="thumbGridRef" class="thumb-grid" @scroll="handleThumbGridScroll">
        <div
          v-for="asset in assets"
          :key="asset.id"
          class="thumb-item"
          draggable="true"
          @dragstart="handleDragStart($event, asset)"
          @click="handleAssetClick(asset)"
          @contextmenu.prevent="openContextMenu($event, asset)"
          :title="asset.location.split(/[/\\]/).pop()"
        >
          <video v-if="isVideo(asset)" :src="getThumb(asset)" class="thumb-media" preload="metadata" draggable="false" />
          <img v-else :src="getThumb(asset)" class="thumb-media" loading="lazy" draggable="false" />
          <div v-if="isVideo(asset)" class="thumb-play">▶</div>
          <div class="thumb-action-buttons">
            <button class="thumb-action-btn" @click.stop="openAddToProjectDialog(asset)" title="添加到项目">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
              </svg>
            </button>
            <span class="thumb-fav-slot" @click.stop>
              <FavoriteHeart :tag="asset.tag || 0" :size="11" @change="(t) => setFavorite(asset, t)" />
            </span>
          </div>
        </div>
      </div>

      <!-- 加载状态 -->
      <div v-if="assets.length > 0 && (loadingMore || !hasMore)" class="load-more">
        <span v-if="loadingMore" class="no-more-text">加载中...</span>
        <span v-else class="no-more-text">已全部加载（{{ assets.length }} / {{ total }}）</span>
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
            <button class="del-btn" @click.stop="confirmDeleteProject(p)" title="删除">
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
              <span class="cat-del" @click.stop="confirmDeleteCategory(cat)">✕</span>
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
            draggable="true"
            @dragstart="handleDragStart($event, asset)"
            @click="handleAssetClick(asset)"
            @contextmenu.prevent="openContextMenu($event, asset)"
            :title="asset.location.split(/[/\\]/).pop()"
          >
            <video v-if="isVideo(asset)" :src="getThumb(asset)" class="thumb-media" preload="metadata" draggable="false" />
            <img v-else :src="getThumb(asset)" class="thumb-media" loading="lazy" draggable="false" />
            <div v-if="isVideo(asset)" class="thumb-play">▶</div>
            <div class="thumb-action-buttons">
              <button class="thumb-action-btn" @click.stop="openAddToProjectDialog(asset)" title="添加到项目">
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                </svg>
              </button>
            </div>
            <button class="thumb-remove-btn" @click.stop="removeAssetFromCategory(asset)" title="移除">✕</button>
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
    <ImageViewer
      :visible="showImageViewer"
      :src="previewUrl"
      :show-nav="currentAssetList.length > 1"
      :index-text="currentAssetList.length > 1 ? `${currentAssetIndex + 1} / ${currentAssetList.length}` : ''"
      @close="showImageViewer = false"
      @prev="goToPrev"
      @next="goToNext"
    />

    <!-- 视频播放器 -->
    <VideoPlayer :visible="showVideoPlayer" :src="activeVideoUrl" :asset-id="activeVideoId" @close="showVideoPlayer = false" @prev="goToPrev" @next="goToNext" :show-nav="currentAssetList.length > 1" />

    <!-- 右键菜单：添加到素材 / 查看生成记录 -->
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
          <div class="context-menu-item" @click="viewGenerationRecord">
            <span class="context-menu-icon">◉</span>
            <span>查看生成记录</span>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 生成记录详情弹窗 -->
    <Teleport to="body">
      <Transition name="record-detail">
        <div v-if="showRecordDetail" class="record-detail-overlay" @click="closeRecordDetail">
          <div class="record-detail-modal" @click.stop>
            <!-- 头部 -->
            <div class="modal-header">
              <span class="modal-title">生成记录详情</span>
              <button class="modal-close-btn" @click="closeRecordDetail">✕</button>
            </div>

            <!-- 内容 -->
            <div v-if="recordDetail" class="modal-body">
              <!-- 参考素材 -->
              <div v-if="recordDetail.input_asset_urls && recordDetail.input_asset_urls.length > 0" class="detail-section">
                <div class="section-title">参考素材</div>
                <div class="reference-grid">
                  <div v-for="(asset, idx) in recordDetail.input_asset_urls" :key="idx" class="reference-item">
                    <video v-if="asset.type === 'video'" :src="asset.url" class="reference-media" controls />
                    <img v-else :src="asset.url" class="reference-media" />
                    <span class="reference-badge">{{ asset.type === 'video' ? '视频' : '图片' }}{{ idx + 1 }}</span>
                  </div>
                </div>
              </div>

              <!-- 提示词 -->
              <div class="detail-section">
                <div class="section-title">提示词</div>
                <div class="prompt-box">{{ recordDetail.prompt || '无' }}</div>
              </div>

              <!-- 模型信息 -->
              <div class="detail-section">
                <div class="section-title">模型</div>
                <div class="model-tag">{{ recordDetail.model_name || '未知' }}</div>
              </div>

              <!-- 生成参数 -->
              <div class="detail-section">
                <div class="section-title">生成参数</div>
                <div class="param-row">
                  <span class="param-label">类型：</span>
                  <span class="param-value">{{ recordDetail.type?.includes('video') ? '视频生成' : '图片生成' }}</span>
                </div>
                <div class="param-row" v-if="recordDetail.mode">
                  <span class="param-label">模式：</span>
                  <span class="param-value">{{ recordDetail.mode === 'img2video' ? '图生视频' : recordDetail.mode === 'txt2video' ? '文生视频' : recordDetail.mode === 'img2img' ? '图生图' : recordDetail.mode === 'txt2img' ? '文生图' : recordDetail.mode }}</span>
                </div>
                <template v-if="recordDetail.payload">
                  <!-- 视频参数 -->
                  <div class="param-row" v-if="recordDetail.payload.ratio">
                    <span class="param-label">比例：</span>
                    <span class="param-value">{{ recordDetail.payload.ratio }}</span>
                  </div>
                  <div class="param-row" v-if="recordDetail.payload.resolution">
                    <span class="param-label">分辨率：</span>
                    <span class="param-value">{{ recordDetail.payload.resolution }}</span>
                  </div>
                  <div class="param-row" v-if="recordDetail.payload.duration">
                    <span class="param-label">时长：</span>
                    <span class="param-value">{{ recordDetail.payload.duration }}秒</span>
                  </div>
                  <!-- 图片参数 -->
                  <div class="param-row" v-if="recordDetail.payload.aspect_ratio">
                    <span class="param-label">宽高比：</span>
                    <span class="param-value">{{ recordDetail.payload.aspect_ratio }}</span>
                  </div>
                  <div class="param-row" v-if="recordDetail.payload.quality">
                    <span class="param-label">质量：</span>
                    <span class="param-value">{{ recordDetail.payload.quality }}</span>
                  </div>
                  <div class="param-row" v-if="recordDetail.payload.width && recordDetail.payload.height">
                    <span class="param-label">尺寸：</span>
                    <span class="param-value">{{ recordDetail.payload.width }} × {{ recordDetail.payload.height }}</span>
                  </div>
                  <div class="param-row" v-if="recordDetail.payload.steps">
                    <span class="param-label">采样步数：</span>
                    <span class="param-value">{{ recordDetail.payload.steps }}</span>
                  </div>
                  <div class="param-row" v-if="recordDetail.payload.cfg">
                    <span class="param-label">CFG：</span>
                    <span class="param-value">{{ recordDetail.payload.cfg }}</span>
                  </div>
                  <div class="param-row" v-if="recordDetail.payload.sampler_name">
                    <span class="param-label">采样器：</span>
                    <span class="param-value">{{ recordDetail.payload.sampler_name }}</span>
                  </div>
                  <div class="param-row" v-if="recordDetail.payload.scheduler">
                    <span class="param-label">调度器：</span>
                    <span class="param-value">{{ recordDetail.payload.scheduler }}</span>
                  </div>
                  <div class="param-row" v-if="recordDetail.payload.seed !== undefined">
                    <span class="param-label">种子：</span>
                    <span class="param-value">{{ recordDetail.payload.seed }}</span>
                  </div>
                  <div class="param-row" v-if="recordDetail.payload.n || recordDetail.payload.batchSize">
                    <span class="param-label">生成数量：</span>
                    <span class="param-value">{{ recordDetail.payload.n || recordDetail.payload.batchSize }}</span>
                  </div>
                </template>
              </div>

              <!-- 生成结果 -->
              <div v-if="recordDetail.output_urls && recordDetail.output_urls.length > 0" class="detail-section">
                <div class="section-title">生成结果</div>
                <div class="output-grid">
                  <div v-for="(output, idx) in recordDetail.output_urls" :key="idx" class="output-item">
                    <video v-if="output.type === 'video'" :src="output.url" class="output-media" controls />
                    <img v-else :src="output.url" class="output-media" />
                  </div>
                </div>
              </div>
            </div>

            <!-- 底部操作 -->
            <div class="modal-footer">
              <button class="modal-btn cancel-btn" @click="closeRecordDetail">关闭</button>
              <button class="modal-btn reuse-btn" @click="reuseRecordParams">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="1 4 1 10 7 10"/>
                  <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>
                </svg>
                复用参数
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <!-- 项目管理器 -->
    <ProjectManager
      :visible="showProjectManager"
      :asset-id="currentAssetIdForProject"
      mode="add"
      @close="handleProjectManagerClose"
    />

    <!-- 确认删除弹窗 -->
    <ConfirmDialog
      :visible="showDeleteConfirm"
      :title="deleteTarget?.type === 'project' ? '删除项目' : '删除标签'"
      :message="deleteTarget?.type === 'project'
        ? `确定要删除项目「${(deleteTarget?.data as Project)?.name || ''}」吗？删除后，该项目下的所有分类也将被删除。`
        : `确定要删除标签「${(deleteTarget?.data as Category)?.name || ''}」吗？删除后，该标签下的资产关联将被移除。`"
      confirm-text="删除"
      cancel-text="取消"
      type="danger"
      :confirm-loading="deleteConfirmLoading"
      @confirm="handleDeleteConfirm"
      @cancel="handleDeleteCancel"
    />
  </div>
</template>

<style scoped>
.asset-sidebar {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: linear-gradient(180deg, rgba(25, 29, 39, 0.5), rgba(6, 8, 13, 0.34));
  backdrop-filter: var(--glass-blur);
  box-shadow: var(--shadow-soft);
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
  margin: 14px 12px 0;
  padding: 3px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: rgba(255,255,255,0.05);
}
.stab {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 34px;
  background: none;
  border: none;
  border-radius: 9px;
  color: var(--color-faint);
  font-size: 12px;
  cursor: pointer;
  transition: color 0.2s, background 0.2s;
}
.stab:hover { color: var(--color-muted); }
.stab.active {
  color: var(--color-text);
  background: rgba(255, 255, 255, 0.11);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.24);
}

/* ── 筛选栏 ── */
.filter-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 12px 8px;
  flex-shrink: 0;
  flex-wrap: wrap;
}
.chip-group {
  display: flex;
  gap: 2px;
  padding: 2px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: rgba(255,255,255,0.055);
}
.chip {
  display: flex; align-items: center; gap: 4px;
  padding: 5px 12px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--color-faint);
  font-size: 12px;
  cursor: pointer;
  transition: color 0.2s, background 0.2s;
}
.chip:hover { color: var(--color-muted); }
.chip.active {
  background: rgba(255, 255, 255, 0.1);
  color: var(--color-text);
}

.fav-chip-group { display: flex; gap: 3px; }
.fav-chip {
  width: 22px; height: 22px;
  border-radius: 50%;
  border: 1px solid var(--color-border);
  background: rgba(255,255,255,0.045);
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
  padding: 8px 12px;
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
  border: 1px solid var(--color-border);
  transition: border-color 0.2s, transform 0.15s;
  /* 防止子元素溢出 */
  contain: layout;
}
.thumb-item:hover {
  border-color: rgba(255, 255, 255, 0.24);
  transform: scale(1.03);
}
.thumb-item:hover .thumb-action-buttons,
.thumb-action-buttons:has(.favorited) { opacity: 1; }

.thumb-action-buttons {
  position: absolute;
  top: 3px;
  right: 3px;
  display: flex;
  gap: 4px;
  align-items: center;
  opacity: 0;
  transition: opacity 0.2s;
  z-index: 2;
}

.thumb-action-btn {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: rgba(0,0,0,0.6);
  border: 1px solid rgba(255,255,255,0.2);
  color: rgba(255,255,255,0.85);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  backdrop-filter: blur(4px);
}

.thumb-action-btn:hover {
  background: rgba(255, 255, 255, 0.18);
  border-color: rgba(255, 255, 255, 0.34);
  transform: scale(1.1);
}

.thumb-fav-slot {
  position: relative;
  top: 0;
  left: 0;
  opacity: 1;
  transition: opacity 0.2s;
  pointer-events: auto;
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

.thumb-remove-btn {
  position: absolute;
  top: 3px;
  right: 3px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: rgba(0,0,0,0.6);
  border: 1px solid rgba(255,255,255,0.2);
  color: rgba(255,255,255,0.8);
  font-size: 12px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: all 0.2s;
  z-index: 3;
  backdrop-filter: blur(4px);
}
.thumb-item:hover .thumb-remove-btn { opacity: 1; }
.thumb-remove-btn:hover {
  background: rgba(244,63,94,0.9);
  border-color: rgba(244,63,94,0.8);
  transform: scale(1.15);
}

/* ── 加载更多 ── */
.load-more {
  flex-shrink: 0;
  padding: 8px 10px 12px;
  display: flex;
  justify-content: center;
}
.no-more-text {
  font-size: 12px;
  color: rgba(255,255,255,0.25);
}

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
.icon-btn:hover {
  background: rgba(255,255,255,0.1);
  border-color: rgba(255,255,255,0.24);
  color: var(--color-text);
}

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
  background: rgba(255,255,255,0.06);
  border-color: rgba(255,255,255,0.16);
}
.proj-item-icon {
  width: 32px; height: 32px;
  border-radius: 8px;
  background: rgba(255,255,255,0.06);
  display: flex; align-items: center; justify-content: center;
  color: var(--color-muted);
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
  border: 1px solid var(--color-border);
  background: rgba(255,255,255,0.045);
  color: var(--color-faint);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
}
.cat-chip:hover {
  border-color: rgba(255,255,255,0.22);
  color: var(--color-muted);
}
.cat-chip.active {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255,255,255,0.24);
  color: var(--color-text);
}
.cat-count {
  font-size: 10px;
  background: rgba(255,255,255,0.08);
  padding: 1px 5px;
  border-radius: 8px;
  color: rgba(255,255,255,0.35);
}
.cat-chip.active .cat-count {
  background: rgba(255,255,255,0.12);
  color: var(--color-text);
}
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
  border: 2px solid rgba(255,255,255,0.14);
  border-top-color: var(--color-primary);
  animation: spin 0.8s linear infinite;
}

/* ── 内联编辑 ── */
.inline-input {
  background: rgba(255,255,255,0.07);
  border: 1px solid rgba(255,255,255,0.22);
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
  background: rgba(255,255,255,0.12);
  border-color: rgba(255,255,255,0.24);
  color: rgba(255,255,255,0.95);
}
.dlg-btn.confirm:hover:not(:disabled) { background: rgba(255,255,255,0.18); }
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
.context-menu-item:hover { background: rgba(255,255,255,0.1); }
.context-menu-item .context-menu-icon {
  font-size: 13px;
  color: var(--color-muted);
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

/* ── 生成记录详情弹窗 ── */
.record-detail-overlay {
  position: fixed;
  inset: 0;
  z-index: 3500;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(12px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.record-detail-modal {
  width: 90%;
  max-width: 800px;
  max-height: 85vh;
  background: rgba(25, 25, 30, 0.98);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 20px;
  box-shadow: 0 25px 80px rgba(0, 0, 0, 0.6);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}

.modal-title {
  font-size: 16px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.9);
  letter-spacing: 0.5px;
}

.modal-close-btn {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: transparent;
  color: rgba(255, 255, 255, 0.5);
  font-size: 18px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.modal-close-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.2);
  color: rgba(255, 255, 255, 0.9);
  transform: rotate(90deg);
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.modal-body::-webkit-scrollbar { width: 6px; }
.modal-body::-webkit-scrollbar-track { background: rgba(255, 255, 255, 0.03); }
.modal-body::-webkit-scrollbar-thumb {
  background: rgba(108, 99, 255, 0.3);
  border-radius: 3px;
}
.modal-body::-webkit-scrollbar-thumb:hover { background: rgba(108, 99, 255, 0.5); }

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.section-title {
  font-size: 12px;
  font-weight: 500;
  color: rgba(167, 139, 250, 0.8);
  text-transform: uppercase;
  letter-spacing: 1.2px;
}

.reference-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
}

.reference-item {
  position: relative;
  aspect-ratio: 16 / 9;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(0, 0, 0, 0.3);
}

.reference-media {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.reference-badge {
  position: absolute;
  bottom: 6px;
  left: 6px;
  padding: 3px 8px;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.75);
  color: rgba(255, 255, 255, 0.85);
  font-size: 10px;
  backdrop-filter: blur(4px);
}

.prompt-box {
  padding: 14px 16px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.8);
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.model-tag {
  display: inline-flex;
  padding: 8px 16px;
  border-radius: 8px;
  background: rgba(108, 99, 255, 0.12);
  border: 1px solid rgba(108, 99, 255, 0.25);
  color: rgba(167, 139, 250, 0.9);
  font-size: 13px;
  font-weight: 500;
}

.param-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
}

.param-label {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.45);
  min-width: 60px;
}

.param-value {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.75);
}

.output-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}

.output-item {
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid rgba(108, 99, 255, 0.2);
  background: rgba(0, 0, 0, 0.4);
  aspect-ratio: 16 / 9;
}

.output-media {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}

.modal-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}

.modal-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 20px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  border: 1px solid transparent;
}

.cancel-btn {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.6);
}

.cancel-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.2);
  color: rgba(255, 255, 255, 0.9);
}

.reuse-btn {
  background: linear-gradient(135deg, rgba(108, 99, 255, 0.25), rgba(167, 139, 250, 0.25));
  border-color: rgba(108, 99, 255, 0.4);
  color: rgba(255, 255, 255, 0.95);
  position: relative;
  overflow: hidden;
}

.reuse-btn::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(108, 99, 255, 0.15), rgba(167, 139, 250, 0.15));
  opacity: 0;
  transition: opacity 0.25s;
}

.reuse-btn:hover::before {
  opacity: 1;
}

.reuse-btn:hover {
  border-color: rgba(108, 99, 255, 0.6);
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(108, 99, 255, 0.25);
}

.reuse-btn:active {
  transform: translateY(0);
}

/* 弹窗动画 - 呼吸感 */
.record-detail-enter-active {
  transition: all 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.record-detail-leave-active {
  transition: all 0.25s cubic-bezier(0.4, 0, 1, 1);
}

.record-detail-enter-from,
.record-detail-leave-to {
  opacity: 0;
}

.record-detail-enter-from .record-detail-modal,
.record-detail-leave-to .record-detail-modal {
  opacity: 0;
  transform: scale(0.85) translateY(30px);
}

.record-detail-enter-active .record-detail-modal {
  animation: breathe-in 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}

@keyframes breathe-in {
  0% {
    opacity: 0;
    transform: scale(0.85) translateY(30px);
  }
  50% {
    transform: scale(1.02) translateY(-5px);
  }
  100% {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

/* 统一为参数面板风格 */
.modal-body::-webkit-scrollbar-thumb,
.modal-body::-webkit-scrollbar-thumb:hover {
  background: rgba(255,255,255,0.16);
}

.section-title,
.model-tag {
  color: var(--color-muted);
}

.model-tag,
.output-item {
  background: rgba(255,255,255,0.04);
  border-color: var(--color-border);
}

.reuse-btn {
  background: rgba(255,255,255,0.1);
  border-color: rgba(255,255,255,0.24);
}
.reuse-btn::before {
  background: rgba(255,255,255,0.08);
}
.reuse-btn:hover {
  border-color: rgba(255,255,255,0.32);
  box-shadow: 0 8px 24px rgba(0,0,0,0.28);
}
</style>
