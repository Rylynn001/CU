<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElDialog, ElInput } from 'element-plus'
import VideoPlayer from '../components/VideoPlayer.vue'
import ImageViewer from '../components/ImageViewer.vue'
import AssetGrid from '../components/AssetGrid.vue'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import ProjectTeamDialog from '../components/ProjectTeamDialog.vue'
import { favoriteAsset } from '../api/apiService'
import type { MemberRole } from '../api/apiService'

interface Asset {
  id: number
  location: string
  asset_type?: string
  tag?: number
}

interface Category {
  id: number
  name: string
  asset_count: number
}

interface Project {
  id: number
  name: string
  category_count: number
  categories?: Category[]   // 点击项目后按需加载
  role?: MemberRole   // 当前用户在该项目的角色
}

// ── 资产展示 ──────────────────────────────────────────────────────────────
const assets = ref<Asset[]>([])
const loading = ref(false)
const loadingMore = ref(false)
const activeFilter = ref<'all' | 'picture' | 'video'>('all')
// 收藏颜色筛选：0=不筛选，1=红，2=黄，3=绿，4=蓝
const favoriteTag = ref<0 | 1 | 2 | 3 | 4>(1)
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

// ── 项目面板 ──────────────────────────────────────────────────────────────
const projects = ref<Project[]>([])
const projectsLoading = ref(false)
const activeView = ref<'assets' | 'project'>('assets')
const selectedProject = ref<Project | null>(null)
const selectedCategory = ref<Category | null>(null)

// 创建项目弹窗
const showCreateProject = ref(false)
const newProjectName = ref('')
const creatingProject = ref(false)

// 创建分类弹窗
const showCreateCategory = ref(false)
const newCategoryName = ref('')
const creatingCategory = ref(false)

// ── 图片预览 ──────────────────────────────────────────────────────────────
const showImageViewer = ref(false)
const previewUrl = ref('')
const currentAssetIndex = ref(0)
const currentAssetList = ref<Asset[]>([])

function previewImage(asset: Asset, list: Asset[]) {
  if (isVideo(asset)) return
  currentAssetList.value = list
  const idx = list.findIndex(a => a.id === asset.id)
  currentAssetIndex.value = idx >= 0 ? idx : 0
  previewUrl.value = getMediaUrl(asset.location)
  showImageViewer.value = true
}

function closeImageViewer() {
  showImageViewer.value = false
}

// 图片滚轮缩放
// 切换到上一个资产（图片或视频）
function goToPrev() {
  if (currentAssetList.value.length === 0) return
  currentAssetIndex.value = (currentAssetIndex.value - 1 + currentAssetList.value.length) % currentAssetList.value.length
  const asset = currentAssetList.value[currentAssetIndex.value]

  if (isVideo(asset)) {
    showImageViewer.value = false
    activeVideo.value = asset
    showVideoPlayer.value = true
  } else {
    showVideoPlayer.value = false
    previewUrl.value = getMediaUrl(asset.location)
    showImageViewer.value = true
  }
}

// 切换到下一个资产（图片或视频）
function goToNext() {
  if (currentAssetList.value.length === 0) return
  currentAssetIndex.value = (currentAssetIndex.value + 1) % currentAssetList.value.length
  const asset = currentAssetList.value[currentAssetIndex.value]

  if (isVideo(asset)) {
    showImageViewer.value = false
    activeVideo.value = asset
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

// ── 视频播放器 ────────────────────────────────────────────────────────────
const showVideoPlayer = ref(false)
const activeVideo = ref<Asset | null>(null)

function openVideo(asset: Asset, list: Asset[]) {
  currentAssetList.value = list
  const idx = list.findIndex(a => a.id === asset.id)
  currentAssetIndex.value = idx >= 0 ? idx : 0
  activeVideo.value = asset
  showVideoPlayer.value = true
}

// ── 用户 ──────────────────────────────────────────────────────────────────
function getUser() {
  const s = localStorage.getItem('user')
  return s ? JSON.parse(s) : null
}

// ── 团队弹窗 ──────────────────────────────────────────────────────────────
const showTeamDialog = ref(false)
const currentUserId = computed(() => getUser()?.id ?? 0)

function openTeamDialog() {
  if (!selectedProject.value) return
  showTeamDialog.value = true
}

// 审核通过后刷新当前分类资产
function handleReviewed() {
  if (selectedCategory.value) loadCategoryAssetDetails(selectedCategory.value.id)
}

// ── 资产加载 ──────────────────────────────────────────────────────────────
async function loadAssets(assetType?: 'picture' | 'video') {
  const user = getUser()
  if (!user) { ElMessage.error('请先登录'); return }
  loading.value = true
  currentPage.value = 1
  try {
    let url = `/api/api-proxy/user/assets?user_id=${user.id}&page=1&page_size=${PAGE_SIZE}`
    if (assetType) url += `&asset_type=${assetType}`
    if (favoriteTag.value > 0) url += `&tag=${favoriteTag.value}`
    const res = await fetch(url)
    if (!res.ok) throw new Error('加载失败')
    const data = await res.json()
    assets.value = data.assets || []
    total.value = data.total ?? 0
  } catch (e: any) {
    ElMessage.error(e.message || '加载资产失败')
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
    if (!res.ok) throw new Error('加载失败')
    const data = await res.json()
    assets.value.push(...(data.assets || []))
    total.value = data.total ?? 0
    currentPage.value = nextPage
  } catch (e: any) {
    ElMessage.error(e.message || '加载失败')
  } finally {
    loadingMore.value = false
  }
}

// ── 项目加载 ──────────────────────────────────────────────────────────────
async function loadProjects() {
  const user = getUser()
  if (!user) return
  projectsLoading.value = true
  try {
    const res = await fetch(`/api/api-proxy/projects?user_id=${user.id}`)
    if (!res.ok) throw new Error('加载失败')
    const data = await res.json()
    projects.value = data.projects || []
  } catch (e: any) {
    ElMessage.error(e.message || '加载项目失败')
  } finally {
    projectsLoading.value = false
  }
}

// 分类下的资产详情
const categoryAssets = ref<Asset[]>([])
const categoryAssetsLoading = ref(false)

async function selectCategory(cat: Category) {
  if (selectedCategory.value?.id === cat.id) return
  selectedCategory.value = cat
  await loadCategoryAssetDetails(cat.id)
}

async function loadCategoryAssetDetails(categoryId: number) {
  if (categoryAssetsLoading.value) return
  categoryAssetsLoading.value = true
  try {
    const res = await fetch(`/api/api-proxy/categories/${categoryId}/assets`)
    if (!res.ok) throw new Error()
    const data = await res.json()
    categoryAssets.value = data.assets || []
  } catch {
    categoryAssets.value = []
  } finally {
    categoryAssetsLoading.value = false
  }
}

// 点击项目时按需加载分类
async function loadCategories(p: Project) {
  const user = getUser()
  if (!user) return
  try {
    const res = await fetch(`/api/api-proxy/projects/${p.id}/categories?user_id=${user.id}`)
    if (!res.ok) throw new Error()
    const data = await res.json()
    p.categories = data.categories || []
  } catch {
    p.categories = []
    ElMessage.error('加载分类失败')
  }
}

async function selectProject(p: Project) {
  // 已选中同一项目不重复加载
  if (selectedProject.value?.id === p.id) return
  selectedProject.value = p
  selectedCategory.value = null
  categoryAssets.value = []
  await loadCategories(p)
  if (p.categories && p.categories.length > 0) {
    selectCategory(p.categories[0])
  }
}

function switchToAssets() {
  activeView.value = 'assets'
  selectedProject.value = null
  selectedCategory.value = null
}

function switchToProjects() {
  activeView.value = 'project'
  selectedProject.value = null
  selectedCategory.value = null
  loadProjects()
}

// ── 创建项目 ──────────────────────────────────────────────────────────────
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
    if (!res.ok) throw new Error('创建失败')
    const data = await res.json()
    projects.value.push({ id: data.id, name: data.name, category_count: (data.categories || []).length, categories: data.categories || [] })
    ElMessage.success('项目已创建')
    showCreateProject.value = false
    newProjectName.value = ''
  } catch (e: any) {
    ElMessage.error(e.message || '创建失败')
  } finally {
    creatingProject.value = false
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
  const res = await fetch(`/api/api-proxy/projects/${p.id}`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: user.id }),
  })
  if (!res.ok) throw new Error('删除失败')
  projects.value = projects.value.filter(x => x.id !== p.id)
  if (selectedProject.value?.id === p.id) { selectedProject.value = null; selectedCategory.value = null }
  ElMessage.success('已删除')
}

// ── 创建分类 ──────────────────────────────────────────────────────────────
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
    if (!res.ok) throw new Error('创建失败')
    const data = await res.json()
    if (!selectedProject.value.categories) selectedProject.value.categories = []
    selectedProject.value.categories.push({ id: data.id, name: data.name, asset_count: 0 })
    selectedProject.value.category_count += 1
    ElMessage.success('分类已创建')
    showCreateCategory.value = false
    newCategoryName.value = ''
  } catch (e: any) {
    ElMessage.error(e.message || '创建失败')
  } finally {
    creatingCategory.value = false
  }
}

// ── 删除分类 ──────────────────────────────────────────────────────────────
async function deleteCategory(cat: Category) {
  const res = await fetch(`/api/api-proxy/categories/${cat.id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('删除失败')
  if (selectedProject.value) {
    if (selectedProject.value.categories) {
      selectedProject.value.categories = selectedProject.value.categories.filter(c => c.id !== cat.id)
    }
    selectedProject.value.category_count = Math.max(0, selectedProject.value.category_count - 1)
  }
  if (selectedCategory.value?.id === cat.id) { selectedCategory.value = null; categoryAssets.value = [] }
  ElMessage.success('已删除')
}

async function removeAssetFromCategory(asset: Asset) {
  if (!selectedCategory.value) return
  try {
    const res = await fetch(`/api/api-proxy/categories/${selectedCategory.value.id}/assets/${asset.id}`, {
      method: 'DELETE',
    })
    if (!res.ok) throw new Error()
    // 从当前分类的资产列表中移除
    selectedCategory.value.asset_count = Math.max(0, selectedCategory.value.asset_count - 1)
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
  editingType.value = type
  editingId.value = id
  editingName.value = name
}

function cancelEdit() {
  editingType.value = null
  editingId.value = null
  editingName.value = ''
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
      const res = await fetch(`/api/api-proxy/projects/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: user.id, name }),
      })
      if (!res.ok) throw new Error('重命名失败')
      const p = projects.value.find(x => x.id === id)
      if (p) p.name = name
      if (selectedProject.value?.id === id) selectedProject.value.name = name
    } else {
      const res = await fetch(`/api/api-proxy/categories/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      })
      if (!res.ok) throw new Error('重命名失败')
      if (selectedProject.value) {
        const cat = selectedProject.value.categories?.find(c => c.id === id)
        if (cat) cat.name = name
      }
      if (selectedCategory.value?.id === id) selectedCategory.value.name = name
    }
  } catch (e: any) {
    ElMessage.error(e.message || '重命名失败')
  }
}
function setFilter(filter: 'all' | 'picture' | 'video') {
  activeFilter.value = filter
  loadAssets(filter === 'all' ? undefined : filter)
}

function setFavoriteTag(tag: 0 | 1 | 2 | 3 | 4) {
  favoriteTag.value = favoriteTag.value === tag ? 0 : tag
  loadAssets(activeFilter.value === 'all' ? undefined : activeFilter.value)
}

function getMediaUrl(location: string) {
  return `/api/api-proxy/output/${location.split(/[/\\]/).pop()}`
}

function isVideo(asset: Asset): boolean {
  const ext = asset.location.split('.').pop()?.toLowerCase()
  return ['mp4', 'mov', 'avi', 'webm'].includes(ext || '')
}

function downloadAsset(asset: Asset) {
  const url = getMediaUrl(asset.location)
  const a = document.createElement('a')
  a.href = url
  a.download = asset.location.split(/[/\\]/).pop() || 'asset'
  a.click()
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
    ElMessage.success(tag === 0 ? '已取消收藏' : '已收藏')
  } catch {
    ElMessage.error('操作失败')
  }
}

function handleWindowScroll() {
  if (loadingMore.value || !hasMore.value) return
  if (window.scrollY + window.innerHeight >= document.documentElement.scrollHeight - 200) {
    loadMore()
  }
}

onMounted(() => {
  loadAssets()
  window.addEventListener('keydown', handleKeydown)
  window.addEventListener('scroll', handleWindowScroll, { passive: true })
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('scroll', handleWindowScroll)
})
</script>

<template>
  <div class="page">
    <div class="orb orb-1" />
    <div class="orb orb-2" />

    <div class="layout">
      <!-- ── 左侧导航 ── -->
      <aside class="sidebar">
        <div class="sidebar-section">
          <button class="nav-item" :class="{ active: activeView === 'assets' }" @click="switchToAssets">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
            我的资产
          </button>
          <button class="nav-item" :class="{ active: activeView === 'project' }" @click="switchToProjects">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
            项目管理
          </button>
        </div>

        <!-- 项目列表 -->
        <div v-if="activeView === 'project'" class="sidebar-projects">
          <div class="sidebar-label">
            <span>项目</span>
            <button class="icon-btn" title="新建项目" @click="showCreateProject = true">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
            </button>
          </div>

          <div v-if="projectsLoading" class="sidebar-loading">
            <div class="mini-ring" />
          </div>

          <div v-else-if="projects.length === 0" class="sidebar-empty">暂无项目</div>

          <div v-else class="project-list">
            <div
              v-for="p in projects"
              :key="p.id"
              class="project-item"
              :class="{ active: selectedProject?.id === p.id }"
              @click="selectProject(p)"
            >
              <template v-if="editingType === 'project' && editingId === p.id">
                <input
                  class="inline-input"
                  v-model="editingName"
                  @blur="submitEdit"
                  @keyup.enter="submitEdit"
                  @keyup.esc="cancelEdit"
                  @click.stop
                  autofocus
                />
              </template>
              <template v-else>
                <span class="project-name" @dblclick.stop="startEdit('project', p.id, p.name)">{{ p.name }}</span>
                <button class="del-btn" title="删除" @click.stop="confirmDeleteProject(p)">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </template>
            </div>
          </div>
        </div>
      </aside>

      <!-- ── 右侧主区 ── -->
      <main class="main">

        <!-- 我的资产视图 -->
        <template v-if="activeView === 'assets'">
          <div class="header">
            <h2 class="title">我的资产</h2>
            <div class="header-right">
              <div class="filter-bar">
                <button class="filter-btn" :class="{ active: activeFilter === 'all' }" @click="setFilter('all')">全部</button>
                <button class="filter-btn" :class="{ active: activeFilter === 'picture' }" @click="setFilter('picture')">图片</button>
                <button class="filter-btn" :class="{ active: activeFilter === 'video' }" @click="setFilter('video')">视频</button>
              </div>
              <div class="filter-bar">
                <button class="filter-btn" :class="{ active: favoriteTag === 0 }" @click="setFavoriteTag(0)">生成记录</button>
                <button
                  v-for="c in FAVORITE_COLORS" :key="c.tag"
                  class="fav-filter-btn"
                  :class="{ active: favoriteTag === c.tag }"
                  :style="{ color: c.color }"
                  :title="`${c.label}色收藏`"
                  @click="setFavoriteTag(c.tag)"
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
                  </svg>
                </button>
              </div>
              <button class="refresh-btn" @click="loadAssets()" :disabled="loading">{{ loading ? '加载中...' : '刷新' }}</button>
            </div>
          </div>

          <AssetGrid
            :assets="assets"
            :loading="loading"
            @preview="(a) => previewImage(a, assets)"
            @open-video="(a) => openVideo(a, assets)"
            @download="downloadAsset"
            @set-favorite="setFavorite"
          />

          <div v-if="assets.length > 0 && (loadingMore || !hasMore)" class="load-more-bar">
            <span v-if="loadingMore" class="no-more-text">加载中...</span>
            <span v-else class="no-more-text">已全部加载（{{ assets.length }} / {{ total }}）</span>
          </div>
        </template>

        <!-- 项目视图 -->
        <template v-else>
          <!-- 未选择项目 -->
          <div v-if="!selectedProject" class="header">
            <h2 class="title">项目管理</h2>
            <button class="refresh-btn" @click="loadProjects">刷新</button>
          </div>

          <div v-if="!selectedProject" class="project-cards">
            <div v-if="projects.length === 0 && !projectsLoading" class="empty">
              <div class="empty-orb" />
              <p class="empty-text">暂无项目，点击左侧 + 新建</p>
            </div>
            <div
              v-for="p in projects"
              :key="p.id"
              class="project-card"
              @click="selectProject(p)"
            >
              <div class="project-card-icon">
                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
              </div>
              <div class="project-card-info">
                <span class="project-card-name">{{ p.name }}</span>
                <span class="project-card-meta">{{ p.category_count }} 个分类</span>
              </div>
            </div>
          </div>

          <!-- 已选择项目：顶部 tab + 直接展示资产 -->
          <template v-if="selectedProject">
            <div class="header">
              <div class="breadcrumb">
                <span class="bc-link" @click="selectedProject = null; selectedCategory = null">项目</span>
                <span class="bc-sep">›</span>
                <span class="bc-current">{{ selectedProject.name }}</span>
              </div>
              <div style="display:flex; gap:8px;">
                <button class="refresh-btn" @click="openTeamDialog">团队协作</button>
                <button class="refresh-btn" @click="showCreateCategory = true">+ 新建分类</button>
              </div>
            </div>

            <div v-if="!selectedProject.categories || selectedProject.categories.length === 0" class="empty">
              <div class="empty-orb" />
              <p class="empty-text">暂无分类，点击右上角新建</p>
            </div>

            <template v-else>
              <div class="cat-tabs">
                <div
                  v-for="cat in selectedProject.categories"
                  :key="cat.id"
                  class="cat-tab"
                  :class="{ active: selectedCategory?.id === cat.id }"
                  @click="selectCategory(cat)"
                >
                  <template v-if="editingType === 'category' && editingId === cat.id">
                    <input
                      class="inline-input tab-input"
                      v-model="editingName"
                      @blur="submitEdit"
                      @keyup.enter="submitEdit"
                      @keyup.esc="cancelEdit"
                      @click.stop
                      autofocus
                    />
                  </template>
                  <template v-else>
                    <span @dblclick.stop="startEdit('category', cat.id, cat.name)">{{ cat.name }}</span>
                    <span class="cat-count">{{ cat.asset_count }}</span>
                    <span class="cat-del-tab" title="删除" @click.stop="confirmDeleteCategory(cat)">✕</span>
                  </template>
                </div>
              </div>

              <!-- 资产网格 -->
              <div v-if="categoryAssetsLoading" class="loading">
                <div class="breath-ring">
                  <div class="ring r1" /><div class="ring r2" /><div class="ring r3" />
                  <div class="center-dot" />
                </div>
                <p class="loading-text">加载中...</p>
              </div>

              <div v-else-if="categoryAssets.length === 0" class="empty">
                <div class="empty-orb" />
                <p class="empty-text">该分类下暂无资产</p>
              </div>

              <div v-else class="gallery">
                <div v-for="asset in categoryAssets" :key="asset.id" class="gallery-item">
                  <div
                    v-if="isVideo(asset)"
                    class="gallery-media video-thumb"
                    @click="openVideo(asset, categoryAssets)"
                  >
                    <video :src="getMediaUrl(asset.location)" class="gallery-media" preload="metadata" />
                    <div class="video-play-icon">▶</div>
                  </div>
                  <img
                    v-else
                    :src="getMediaUrl(asset.location)"
                    class="gallery-media"
                    @click="previewImage(asset, categoryAssets)"
                  />
                  <div class="gallery-info">
                    <span class="gallery-name">{{ asset.location.split(/[/\\]/).pop() }}</span>
                    <span v-if="isVideo(asset)" class="gallery-type">视频</span>
                  </div>
                  <button class="download-btn" @click.stop="downloadAsset(asset)" title="下载">
                    <span>⬇</span>
                  </button>
                  <button class="remove-asset-btn" @click.stop="removeAssetFromCategory(asset)" title="移除">✕</button>
                </div>
              </div>
            </template>
          </template>
        </template>
      </main>
    </div>

    <!-- 新建项目弹窗 -->
    <el-dialog v-model="showCreateProject" title="新建项目" width="380px" :show-close="true" align-center>
      <el-input v-model="newProjectName" placeholder="项目名称" @keyup.enter="confirmCreateProject" autofocus />
      <template #footer>
        <button class="dialog-btn cancel" @click="showCreateProject = false">取消</button>
        <button class="dialog-btn confirm" :disabled="creatingProject" @click="confirmCreateProject">
          {{ creatingProject ? '创建中...' : '确认' }}
        </button>
      </template>
    </el-dialog>

    <!-- 新建分类弹窗 -->
    <el-dialog v-model="showCreateCategory" title="新建分类" width="380px" :show-close="true" align-center>
      <el-input v-model="newCategoryName" placeholder="分类名称" @keyup.enter="confirmCreateCategory" autofocus />
      <template #footer>
        <button class="dialog-btn cancel" @click="showCreateCategory = false">取消</button>
        <button class="dialog-btn confirm" :disabled="creatingCategory" @click="confirmCreateCategory">
          {{ creatingCategory ? '创建中...' : '确认' }}
        </button>
      </template>
    </el-dialog>

    <ImageViewer
      :visible="showImageViewer"
      :src="previewUrl"
      :show-nav="currentAssetList.length > 1"
      :index-text="currentAssetList.length > 1 ? `${currentAssetIndex + 1} / ${currentAssetList.length}` : ''"
      @close="closeImageViewer"
      @prev="goToPrev"
      @next="goToNext"
    />

    <!-- Video Player -->
    <VideoPlayer
      v-if="activeVideo"
      :visible="showVideoPlayer"
      :src="getMediaUrl(activeVideo.location)"
      :asset-id="activeVideo.id"
      :show-nav="currentAssetList.length > 1"
      @close="showVideoPlayer = false"
      @prev="goToPrev"
      @next="goToNext"
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

    <!-- 团队协作弹窗 -->
    <ProjectTeamDialog
      v-if="selectedProject"
      :visible="showTeamDialog"
      :project-id="selectedProject.id"
      :project-name="selectedProject.name"
      :current-role="selectedProject.role || 'member'"
      :current-user-id="currentUserId"
      @close="showTeamDialog = false"
      @reviewed="handleReviewed"
    />
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
  position: relative;
  overflow: hidden;
}

.orb {
  position: fixed;
  border-radius: 50%;
  filter: blur(90px);
  pointer-events: none;
  z-index: 0;
  animation: breathe 6s ease-in-out infinite;
}
.orb-1 {
  width: 500px; height: 500px;
  background: radial-gradient(circle, rgba(166,231,226,0.12) 0%, transparent 70%);
  top: -140px; left: 40px;
}
.orb-2 {
  width: 400px; height: 400px;
  background: radial-gradient(circle, rgba(255,255,255,0.08) 0%, transparent 70%);
  bottom: -100px; right: 60px;
  animation-delay: 3s;
}

/* ── 布局 ── */
.layout {
  position: relative;
  z-index: 1;
  display: flex;
  min-height: 100vh;
}

/* ── 侧边栏 ── */
.sidebar {
  width: 220px;
  flex-shrink: 0;
  padding: 40px 12px 40px 16px;
  border-right: 1px solid rgba(255,255,255,0.06);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sidebar-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: 10px;
  border: none;
  background: transparent;
  color: rgba(255,255,255,0.45);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
  width: 100%;
}
.nav-item:hover {
  background: rgba(255,255,255,0.05);
  color: rgba(255,255,255,0.8);
}
.nav-item.active {
  background: rgba(255,255,255,0.1);
  color: var(--color-text);
}

.sidebar-projects {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sidebar-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px 6px;
  font-size: 11px;
  color: rgba(255,255,255,0.25);
  letter-spacing: 1px;
  text-transform: uppercase;
}

.icon-btn {
  width: 22px; height: 22px;
  border-radius: 6px;
  border: 1px solid rgba(255,255,255,0.1);
  background: transparent;
  color: rgba(255,255,255,0.4);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.2s;
}
.icon-btn:hover {
  background: rgba(255,255,255,0.1);
  border-color: rgba(255,255,255,0.24);
  color: rgba(255,255,255,0.9);
}

.sidebar-loading {
  display: flex;
  justify-content: center;
  padding: 16px 0;
}
.mini-ring {
  width: 20px; height: 20px;
  border-radius: 50%;
  border: 1.5px solid rgba(166,231,226,0.42);
  border-top-color: transparent;
  animation: spin 0.8s linear infinite;
}

.sidebar-empty {
  font-size: 12px;
  color: rgba(255,255,255,0.2);
  text-align: center;
  padding: 12px 0;
}

.project-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.project-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  color: rgba(255,255,255,0.55);
  font-size: 13px;
}
.project-item:hover {
  background: rgba(255,255,255,0.05);
  color: rgba(255,255,255,0.85);
}
.project-item.active {
  background: rgba(255,255,255,0.1);
  color: var(--color-text);
}
.project-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
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
.project-item:hover .del-btn,
.category-card:hover .cat-del {
  opacity: 1;
}
.del-btn:hover {
  background: rgba(244,63,94,0.15);
  color: #f43f5e;
}

/* ── 主区域 ── */
.main {
  flex: 1;
  min-width: 0;
  padding: 40px 32px;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 32px;
}

.title {
  font-size: 26px;
  font-weight: 600;
  color: rgba(255,255,255,0.9);
  letter-spacing: 2px;
  margin: 0;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.filter-bar {
  display: flex;
  gap: 6px;
}

.filter-btn {
  padding: 6px 16px;
  border-radius: 20px;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.03);
  color: rgba(255,255,255,0.5);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.filter-btn:hover {
  border-color: rgba(255,255,255,0.24);
  color: rgba(255,255,255,0.8);
}
.filter-btn.active {
  background: rgba(255,255,255,0.1);
  border-color: rgba(255,255,255,0.24);
  color: rgba(255,255,255,0.95);
}

.fav-filter-btn {
  width: 30px; height: 30px;
  border-radius: 50%;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.03);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  opacity: 0.55;
  transition: all 0.2s;
}
.fav-filter-btn svg { fill: none; }
.fav-filter-btn:hover { opacity: 0.85; transform: scale(1.08); }
.fav-filter-btn.active {
  opacity: 1;
  background: color-mix(in srgb, currentColor 18%, transparent);
  border-color: currentColor;
}
.fav-filter-btn.active svg { fill: currentColor; }

.refresh-btn {
  padding: 7px 18px;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.13);
  background: rgba(255,255,255,0.08);
  color: rgba(255,255,255,0.8);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.refresh-btn:hover:not(:disabled) {
  background: rgba(255,255,255,0.12);
  border-color: rgba(255,255,255,0.24);
}
.refresh-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* ── 面包屑 ── */
.breadcrumb {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
}
.bc-link {
  color: var(--color-muted);
  cursor: pointer;
  transition: color 0.2s;
}
.bc-link:hover { color: var(--color-text); }
.bc-sep { color: rgba(255,255,255,0.2); }
.bc-current { color: rgba(255,255,255,0.85); font-weight: 500; }

/* ── 项目卡片 ── */
.project-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
}

.project-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 20px;
  border-radius: 14px;
  border: 1px solid rgba(255,255,255,0.07);
  background: rgba(255,255,255,0.02);
  cursor: pointer;
  transition: all 0.25s;
}
.project-card:hover {
  border-color: rgba(255,255,255,0.24);
  background: rgba(255,255,255,0.06);
  transform: translateY(-3px);
}

.project-card-icon {
  width: 48px; height: 48px;
  border-radius: 12px;
  background: rgba(255,255,255,0.06);
  display: flex; align-items: center; justify-content: center;
  color: var(--color-muted);
  flex-shrink: 0;
}

.project-card-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.project-card-name {
  font-size: 14px;
  font-weight: 500;
  color: rgba(255,255,255,0.85);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.project-card-meta {
  font-size: 12px;
  color: rgba(255,255,255,0.3);
}

/* ── 分类 tab 栏 ── */
.cat-tabs {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}

.cat-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 16px;
  border-radius: 20px;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.03);
  color: rgba(255,255,255,0.5);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
}
.cat-tab:hover {
  border-color: rgba(255,255,255,0.24);
  color: rgba(255,255,255,0.8);
}
.cat-tab.active {
  background: rgba(255,255,255,0.1);
  border-color: rgba(255,255,255,0.24);
  color: rgba(255,255,255,0.95);
}

.cat-count {
  font-size: 11px;
  background: rgba(255,255,255,0.1);
  padding: 1px 6px;
  border-radius: 10px;
  color: rgba(255,255,255,0.4);
}
.cat-tab.active .cat-count {
  background: rgba(255,255,255,0.08);
  color: var(--color-muted);
}

.cat-del-tab {
  font-size: 11px;
  color: rgba(255,255,255,0.2);
  margin-left: 2px;
  opacity: 0;
  transition: all 0.15s;
  line-height: 1;
}
.cat-tab:hover .cat-del-tab {
  opacity: 1;
}
.cat-del-tab:hover {
  color: #f43f5e;
}

/* ── 加载 / 空态 ── */
.loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
  padding: 80px 0;
}
.loading-text {
  font-size: 13px;
  color: rgba(255,255,255,0.35);
  letter-spacing: 2px;
}

.breath-ring {
  position: relative;
  width: 100px; height: 100px;
  display: flex; align-items: center; justify-content: center;
}
.ring {
  position: absolute;
  border-radius: 50%;
  border: 1.5px solid rgba(166,231,226,0.42);
  animation: breathe 3s ease-in-out infinite;
}
.r1 { width: 100%; height: 100%; animation-delay: 0s; }
.r2 { width: 72%; height: 72%; animation-delay: 0.5s; border-color: rgba(255,255,255,0.2); }
.r3 { width: 44%; height: 44%; animation-delay: 1s; border-color: rgba(255,255,255,0.28); }
.center-dot {
  width: 10px; height: 10px;
  border-radius: 50%;
  background: rgba(255,255,255,0.72);
  animation: pulse-dot 2s ease-in-out infinite;
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 80px 0;
}
.empty-orb {
  width: 60px; height: 60px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(166,231,226,0.12) 0%, transparent 70%);
  border: 1px solid rgba(255,255,255,0.13);
  animation: breathe 4s ease-in-out infinite;
}
.empty-text {
  font-size: 12px;
  color: rgba(255,255,255,0.2);
  letter-spacing: 2px;
}

/* ── 加载更多 ── */
.load-more-bar {
  display: flex;
  justify-content: center;
  padding: 24px 0 8px;
}
.load-more-btn {
  padding: 8px 28px;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.13);
  background: rgba(255,255,255,0.08);
  color: rgba(255,255,255,0.7);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.load-more-btn:hover:not(:disabled) { background: rgba(255,255,255,0.12); color: #fff; }
.load-more-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.no-more-text {
  font-size: 12px;
  color: rgba(255,255,255,0.25);
  align-self: center;
}

/* ── 弹窗按钮 ── */
.dialog-btn {
  padding: 8px 24px;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}
.dialog-btn.cancel {
  background: rgba(255,255,255,0.04);
  border-color: rgba(255,255,255,0.1);
  color: rgba(255,255,255,0.5);
  margin-right: 8px;
}
.dialog-btn.cancel:hover { background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.8); }
.dialog-btn.confirm {
  background: rgba(255,255,255,0.1);
  border-color: rgba(255,255,255,0.24);
  color: rgba(255,255,255,0.95);
}
.dialog-btn.confirm:hover:not(:disabled) { background: rgba(255,255,255,0.14); }
.dialog-btn.confirm:disabled { opacity: 0.5; cursor: not-allowed; }

@keyframes breathe {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.7; transform: scale(0.95); }
}
@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ── 资产网格 ── */
.gallery {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 20px;
}
.gallery-item {
  position: relative;
  border-radius: 12px;
  overflow: hidden;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.08);
  transition: transform 0.2s, border-color 0.2s;
}
.gallery-item:hover {
  transform: translateY(-4px);
  border-color: rgba(255,255,255,0.24);
}
.gallery-media {
  width: 100%;
  height: 260px;
  object-fit: cover;
  display: block;
  cursor: pointer;
}
.video-thumb {
  position: relative;
  height: 260px;
  background: #000;
  cursor: pointer;
}
.video-thumb video {
  height: 260px;
}
.video-play-icon {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 32px;
  color: rgba(255,255,255,0.8);
  background: rgba(0,0,0,0.25);
  transition: background 0.2s;
}
.video-thumb:hover .video-play-icon {
  background: rgba(0,0,0,0.4);
}
.gallery-info {
  padding: 10px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.gallery-name {
  font-size: 12px;
  color: rgba(255,255,255,0.4);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 85%;
}
.gallery-type {
  font-size: 11px;
  color: var(--color-muted);
  background: rgba(255,255,255,0.08);
  padding: 2px 7px;
  border-radius: 10px;
}
.download-btn {
  position: absolute;
  bottom: 44px;
  right: 10px;
  width: 30px; height: 30px;
  border-radius: 50%;
  background: rgba(0,0,0,0.5);
  border: none;
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  opacity: 0;
  transition: all 0.2s;
  backdrop-filter: blur(4px);
}
.gallery-item:hover .download-btn { opacity: 1; }
.download-btn:hover { background: rgba(255,255,255,0.18); transform: scale(1.1); }

.remove-asset-btn {
  position: absolute;
  top: 10px;
  right: 10px;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: rgba(0,0,0,0.6);
  border: 1px solid rgba(255,255,255,0.2);
  color: rgba(255,255,255,0.8);
  font-size: 14px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: all 0.2s;
  z-index: 2;
  backdrop-filter: blur(4px);
}
.gallery-item:hover .remove-asset-btn { opacity: 1; }
.remove-asset-btn:hover {
  background: rgba(244,63,94,0.9);
  border-color: rgba(244,63,94,0.8);
  transform: scale(1.15);
}

/* ── 内联编辑输入框 ── */
.inline-input {
  background: rgba(255,255,255,0.07);
  border: 1px solid rgba(255,255,255,0.22);
  border-radius: 6px;
  color: rgba(255,255,255,0.9);
  font-size: 13px;
  padding: 2px 8px;
  outline: none;
  width: 120px;
}
.inline-input.tab-input {
  width: 90px;
  padding: 1px 6px;
}

/* 统一为参数面板风格 */
.icon-btn:hover,
.project-item.active,
.project-card:hover,
.filter-btn:hover,
.filter-btn.active,
.cat-tab:hover,
.cat-tab.active,
.refresh-btn,
.load-more-btn,
.dialog-btn.confirm,
.gallery-item:hover {
  border-color: rgba(255,255,255,0.24);
}

.icon-btn:hover,
.project-item.active,
.filter-btn.active,
.cat-tab.active,
.refresh-btn,
.load-more-btn,
.dialog-btn.confirm {
  background: rgba(255,255,255,0.1);
  color: var(--color-text);
}

.project-card:hover,
.refresh-btn:hover:not(:disabled),
.load-more-btn:hover:not(:disabled),
.dialog-btn.confirm:hover:not(:disabled) {
  background: rgba(255,255,255,0.12);
}

.filter-btn,
.cat-tab,
.refresh-btn,
.load-more-btn {
  border-color: var(--color-border);
}

.filter-btn:hover,
.cat-tab:hover {
  color: var(--color-muted);
}

.project-card-icon,
.empty-orb {
  background: rgba(255,255,255,0.06);
  border-color: var(--color-border);
  color: var(--color-muted);
}

.bc-link,
.gallery-type,
.cat-tab.active .cat-count {
  color: var(--color-muted);
}
.bc-link:hover {
  color: var(--color-text);
}

.cat-tab.active .cat-count,
.gallery-type {
  background: rgba(255,255,255,0.08);
}

.ring {
  border-color: rgba(255,255,255,0.24);
}
.r2,
.r3 {
  border-color: rgba(255,255,255,0.18);
}
.center-dot {
  background: rgba(255,255,255,0.72);
}

.gallery-item:hover {
  transform: translateY(-4px);
}
.download-btn:hover {
  background: rgba(255,255,255,0.18);
}

.inline-input {
  background: rgba(255,255,255,0.07);
  border-color: rgba(255,255,255,0.22);
}
</style>
