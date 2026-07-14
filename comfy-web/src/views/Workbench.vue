<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElDialog, ElInput, ElMessage, ElOption, ElSelect } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import MediaViewer, { type MediaViewerItem } from '../components/MediaViewer.vue'
import ProjectManager from '../components/ProjectManager.vue'
import FavoriteHeart from '../components/FavoriteHeart.vue'
import ProjectCard from '../components/ProjectCard.vue'
import type { ProjectSummary } from '../types/project'
import { favoriteAsset } from '../api/apiService'
import { analyzeImageColors, getColorPercentage, getDominantColors, type ColorAnalysis, type ImageColor } from '../utils/imageColors'

interface Asset {
  id: number
  location: string
  name?: string
  asset_type?: 'picture' | 'video'
  tag?: number
  created_at?: string
}

interface Category { id: number; name: string; assets: number[] }
interface Project extends ProjectSummary { categories: Category[] }

const now = Date.now()
const day = 86_400_000
const MOCK_ASSETS: Asset[] = [
  { id: 9001, name: '星夜概念图', location: 'https://images.unsplash.com/photo-1519608487953-e999c86e7455?auto=format&fit=crop&w=1000&q=85', asset_type: 'picture', tag: 1, created_at: new Date(now - day).toISOString() },
  { id: 9002, name: '夏日公路', location: 'https://images.unsplash.com/photo-1500530855697-b586d89ba3ee?auto=format&fit=crop&w=1000&q=85', asset_type: 'picture', tag: 2, created_at: new Date(now - day * 2).toISOString() },
  { id: 9003, name: '荒野远景', location: 'https://images.unsplash.com/photo-1500534314209-a25ddb2bd429?auto=format&fit=crop&w=1000&q=85', asset_type: 'picture', tag: 3, created_at: new Date(now - day * 5).toISOString() },
  { id: 9004, name: '人物造型', location: 'https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?auto=format&fit=crop&w=1000&q=85', asset_type: 'picture', tag: 4, created_at: new Date(now - day * 9).toISOString() },
  { id: 9005, name: '创意空间', location: 'https://images.unsplash.com/photo-1497366754035-f200968a6e72?auto=format&fit=crop&w=1000&q=85', asset_type: 'picture', tag: 1, created_at: new Date(now - day * 14).toISOString() },
  { id: 9006, name: '山野晨光', location: 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?auto=format&fit=crop&w=1000&q=85', asset_type: 'picture', tag: 0, created_at: new Date(now - day * 32).toISOString() },
  { id: 9011, name: '海岸动态测试', location: 'https://storage.googleapis.com/coverr-main/mp4/Mt_Baker.mp4', asset_type: 'video', tag: 1, created_at: new Date(now - day).toISOString() },
  { id: 9012, name: '森林光线测试', location: 'https://storage.googleapis.com/coverr-main/mp4/Footboys.mp4', asset_type: 'video', tag: 3, created_at: new Date(now - day * 4).toISOString() },
]

const MOCK_PROJECTS: Project[] = [
  { id: 9101, name: '品牌视觉提案', categories: [
    { id: 9201, name: '情绪参考', assets: [9001, 9003, 9006] },
    { id: 9202, name: '主视觉候选', assets: [9004, 9011] },
  ] },
  { id: 9102, name: '夏日短片', categories: [
    { id: 9203, name: '场景概念', assets: [9002, 9005, 9012] },
  ] },
]

const assets = ref<Asset[]>([])
const projects = ref<Project[]>([])
const router = useRouter()
const mediaType = ref<'all' | 'picture' | 'video'>('all')
const search = ref('')
const projectFilter = ref('all')
const favoriteFilter = ref('all')
const dateFilter = ref('all')
const colorTarget = ref('#d6d6d6')
const colorFilterActive = ref(false)
const detectedColors = ref<ImageColor[]>([])
const loading = ref(false)
const recentExpanded = ref(false)
const showCreateProject = ref(false)
const newProjectName = ref('')
const creatingProject = ref(false)
const previewAsset = ref<Asset | null>(null)
const viewerItem = computed<MediaViewerItem | null>(() => previewAsset.value ? {
  id: previewAsset.value.id,
  src: mediaUrl(previewAsset.value.location),
  type: previewAsset.value.asset_type === 'video' ? 'video' : 'image',
  title: previewAsset.value.name || previewAsset.value.location.split(/[/\\]/).pop(),
  subtitle: previewAsset.value.created_at ? new Date(previewAsset.value.created_at).toLocaleDateString() : '',
} : null)
const managerAssetId = ref<number>()
const showProjectManager = ref(false)
let searchTimer: ReturnType<typeof setTimeout> | undefined
let loadVersion = 0
let activeRequest: AbortController | undefined
let paletteVersion = 0
const colorAnalysisCache = new Map<string, Promise<ColorAnalysis | null>>()

const recentAssets = computed(() => recentExpanded.value ? assets.value : assets.value.slice(0, 8))
const visibleProjects = computed(() => (projectFilter.value === 'all' ? projects.value : projects.value.filter(project => project.id === Number(projectFilter.value))).slice(0, 6))
const hasFilters = computed(() => Boolean(search.value || projectFilter.value !== 'all' || favoriteFilter.value !== 'all' || dateFilter.value !== 'all' || colorFilterActive.value))

function getUser() {
  try { return JSON.parse(localStorage.getItem('user') || 'null') } catch { return null }
}

function isDebugUser() {
  return getUser()?.debug === true
}

function mediaUrl(location: string) {
  return /^https?:\/\//.test(location) ? location : `/api/api-proxy/output/${location.split(/[/\\]/).pop()}`
}

function colorRgb(hex: string) {
  return Number.parseInt(hex.slice(1), 16)
}

function analyzeAssetColors(asset: Asset) {
  const url = mediaUrl(asset.location)
  const cached = colorAnalysisCache.get(url)
  if (cached) return cached

  const analysis = new Promise<ColorAnalysis | null>((resolve) => {
    const image = new Image()
    image.crossOrigin = 'anonymous'
    image.onload = () => {
      const scale = Math.min(1, 256 / Math.max(image.naturalWidth, image.naturalHeight))
      const width = Math.max(1, Math.round(image.naturalWidth * scale))
      const height = Math.max(1, Math.round(image.naturalHeight * scale))
      const canvas = document.createElement('canvas')
      canvas.width = width
      canvas.height = height
      const context = canvas.getContext('2d', { willReadFrequently: true })

      try {
        if (!context) throw new Error('Canvas unavailable')
        context.drawImage(image, 0, 0, width, height)
        resolve(analyzeImageColors(context.getImageData(0, 0, width, height)))
      } catch {
        resolve(null)
      }
    }
    image.onerror = () => resolve(null)
    image.src = url
  })

  colorAnalysisCache.set(url, analysis)
  return analysis
}

async function filterByColorShare(list: Asset[]) {
  if (!colorFilterActive.value) return list

  const targetRgb = colorRgb(colorTarget.value)
  const minimumShare = 10
  const pictures = list.filter(asset => asset.asset_type !== 'video')
  const matches = new Set<number>()
  let nextIndex = 0

  await Promise.all(Array.from({ length: Math.min(4, pictures.length) }, async () => {
    while (nextIndex < pictures.length) {
      const asset = pictures[nextIndex++]
      const analysis = await analyzeAssetColors(asset)
      if (analysis && getColorPercentage(analysis, targetRgb) >= minimumShare) matches.add(asset.id)
    }
  }))

  return list.filter(asset => matches.has(asset.id))
}

async function refreshDetectedColors(list: Asset[]) {
  const version = ++paletteVersion
  const pictures = list.filter(asset => asset.asset_type !== 'video').slice(0, 24)
  const buckets = new Map<number, { red: number; green: number; blue: number; weight: number }>()
  let nextIndex = 0

  await Promise.all(Array.from({ length: Math.min(4, pictures.length) }, async () => {
    while (nextIndex < pictures.length) {
      const analysis = await analyzeAssetColors(pictures[nextIndex++])
      if (!analysis) continue

      for (const color of getDominantColors(analysis)) {
        const bucketId = ((color.rgb >> 20) << 8) | (((color.rgb >> 12) & 15) << 4) | ((color.rgb >> 4) & 15)
        const bucket = buckets.get(bucketId)
        if (bucket) {
          bucket.red += (color.rgb >> 16) * color.percentage
          bucket.green += ((color.rgb >> 8) & 255) * color.percentage
          bucket.blue += (color.rgb & 255) * color.percentage
          bucket.weight += color.percentage
        } else {
          buckets.set(bucketId, { red: (color.rgb >> 16) * color.percentage, green: ((color.rgb >> 8) & 255) * color.percentage, blue: (color.rgb & 255) * color.percentage, weight: color.percentage })
        }
      }
    }
  }))

  if (version !== paletteVersion) return
  detectedColors.value = [...buckets.values()]
    .sort((left, right) => right.weight - left.weight)
    .slice(0, 5)
    .map(bucket => {
      const rgb = (Math.round(bucket.red / bucket.weight) << 16) | (Math.round(bucket.green / bucket.weight) << 8) | Math.round(bucket.blue / bucket.weight)
      return { rgb, hex: `#${rgb.toString(16).padStart(6, '0')}`, pixels: Math.round(bucket.weight), percentage: bucket.weight / pictures.length }
    })
}

function useDetectedColor(color: ImageColor) {
  colorTarget.value = color.hex
  colorFilterActive.value = true
}

function projectFallbackAssets(project: Project) {
  const ids = new Set(project.categories.flatMap(category => category.assets))
  return MOCK_ASSETS.filter(asset => ids.has(asset.id))
}

function openProject(project: Project) {
  sessionStorage.setItem('active-project', JSON.stringify({ project, assets: projectFallbackAssets(project) }))
  router.push(`/projects/${project.id}`)
}

function mockFiltered(projectId?: number) {
  let list = MOCK_ASSETS.filter(a => mediaType.value === 'all' || a.asset_type === mediaType.value)
  const selectedId = projectId || (projectFilter.value === 'all' ? undefined : Number(projectFilter.value))
  if (selectedId) {
    const project = MOCK_PROJECTS.find(p => p.id === selectedId)
    const ids = new Set(project?.categories.flatMap(c => c.assets) || [])
    list = list.filter(a => ids.has(a.id))
  }
  const q = search.value.trim().toLowerCase()
  if (q) {
    const matchingProjects = MOCK_PROJECTS.filter(p => p.name.toLowerCase().includes(q) || p.categories.some(c => c.name.toLowerCase().includes(q)))
    const ids = new Set(matchingProjects.flatMap(p => p.categories.flatMap(c => c.assets)))
    list = list.filter(a => a.name?.toLowerCase().includes(q) || ids.has(a.id))
  }
  if (favoriteFilter.value !== 'all') list = list.filter(a => (a.tag || 0) === Number(favoriteFilter.value))
  if (dateFilter.value !== 'all') {
    const cutoff = now - Number(dateFilter.value) * day
    list = list.filter(a => new Date(a.created_at || 0).getTime() >= cutoff)
  }
  return list.sort((a, b) => new Date(b.created_at || 0).getTime() - new Date(a.created_at || 0).getTime())
}

function queryParams(projectId?: number) {
  const user = getUser()
  const params = new URLSearchParams({ user_id: String(user?.id || ''), page: '1', page_size: '100' })
  if (mediaType.value !== 'all') params.set('asset_type', mediaType.value)
  if (search.value.trim()) params.set('q', search.value.trim())
  const pid = projectId || (projectFilter.value === 'all' ? undefined : Number(projectFilter.value))
  if (pid) params.set('project_id', String(pid))
  if (favoriteFilter.value !== 'all') params.set('tag', favoriteFilter.value)
  if (dateFilter.value !== 'all') params.set('date_range', dateFilter.value)
  return params
}

async function fetchAssets(signal?: AbortSignal) {
  const user = getUser()
  if (!user?.id) return isDebugUser() ? mockFiltered() : []
  try {
    const response = await fetch(`/api/api-proxy/user/assets?${queryParams()}`, { signal })
    if (!response.ok) throw new Error()
    const data = await response.json()
    return data.assets || []
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    return isDebugUser() ? mockFiltered() : []
  }
}

async function loadProjects() {
  const user = getUser()
  if (!user?.id) { projects.value = isDebugUser() ? structuredClone(MOCK_PROJECTS) : []; return }
  try {
    const response = await fetch(`/api/api-proxy/projects?user_id=${user.id}`)
    if (!response.ok) throw new Error()
    const data = await response.json()
    projects.value = data.projects || []
  } catch { projects.value = isDebugUser() ? structuredClone(MOCK_PROJECTS) : [] }
}

async function loadWorkspace() {
  const version = ++loadVersion
  activeRequest?.abort()
  activeRequest = new AbortController()
  loading.value = true
  try {
    const loadedAssets = await filterByColorShare(await fetchAssets(activeRequest.signal))
    if (version !== loadVersion) return
    assets.value = loadedAssets
    void refreshDetectedColors(loadedAssets)
  } catch (error) {
    if (!(error instanceof DOMException && error.name === 'AbortError')) throw error
  } finally {
    if (version === loadVersion) loading.value = false
  }
}

function resetFilters() {
  search.value = ''
  projectFilter.value = 'all'
  favoriteFilter.value = 'all'
  dateFilter.value = 'all'
  colorFilterActive.value = false
}

function handleRecentWheel(event: WheelEvent) {
  const row = event.currentTarget as HTMLElement
  if (row.scrollWidth <= row.clientWidth) return
  event.preventDefault()
  row.scrollLeft += Math.abs(event.deltaY) > Math.abs(event.deltaX) ? event.deltaY : event.deltaX
}

async function createProject() {
  const name = newProjectName.value.trim()
  if (!name) return
  const user = getUser()
  let created = false
  creatingProject.value = true
  try {
    if (!user?.id) throw new Error()
    const response = await fetch('/api/api-proxy/projects', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_id: user.id, name }) })
    if (!response.ok) throw new Error()
    const data = await response.json()
    projects.value.push({ id: data.id, name: data.name, categories: [], asset_count:0, scope:'personal', role:'owner', member_count:1, cover_assets:[] })
    created = true
    openProject(projects.value[projects.value.length - 1])
  } catch {
    if (isDebugUser()) {
      const id=Date.now();projects.value.push({ id, name, categories: [], asset_count:0, scope:'personal', role:'owner', member_count:1, cover_assets:[] });openProject(projects.value[projects.value.length - 1])
      created = true
    } else {
      ElMessage.error('项目创建失败，请稍后重试')
      return
    }
  } finally {
    creatingProject.value = false
    if (created) {
      showCreateProject.value = false
      newProjectName.value = ''
    }
  }
}

function openAsset(asset: Asset) {
  previewAsset.value = asset
}

function prepareVideoThumb(event: Event) {
  const video = event.currentTarget as HTMLVideoElement
  if (Number.isFinite(video.duration) && video.duration > 0 && video.currentTime === 0) {
    video.currentTime = Math.min(0.12, video.duration / 10)
  }
}

function downloadAsset(asset: Asset) {
  const link = document.createElement('a')
  link.href = mediaUrl(asset.location)
  link.download = asset.name || 'asset'
  link.click()
}

function addToProject(asset: Asset) {
  managerAssetId.value = asset.id
  showProjectManager.value = true
}

async function setFavorite(asset: Asset, tag: 0 | 1 | 2 | 3 | 4) {
  const user = getUser()
  try {
    if (asset.id < 9000 && user?.id) await favoriteAsset(asset.id, user.id, tag)
    asset.tag = tag
  } catch { ElMessage.error('收藏更新失败') }
}

watch([mediaType, projectFilter, favoriteFilter, dateFilter, colorTarget, colorFilterActive, search], () => {
  clearTimeout(searchTimer)
  searchTimer = setTimeout(loadWorkspace, 280)
})

onMounted(async () => {
  await loadProjects()
  await loadWorkspace()
})

onUnmounted(() => {
  clearTimeout(searchTimer)
  activeRequest?.abort()
})
</script>

<template>
  <main class="workbench">
    <header class="topbar">
      <nav class="media-tabs" aria-label="媒体类型">
        <button :class="{ active: mediaType === 'all' }" @click="mediaType = 'all'">全部</button>
        <button :class="{ active: mediaType === 'picture' }" @click="mediaType = 'picture'">图片</button>
        <button :class="{ active: mediaType === 'video' }" @click="mediaType = 'video'">视频</button>
      </nav>
      <h1>工作台</h1>
    </header>

    <div class="top-actions">
      <ElInput v-model="search" class="search" :prefix-icon="Search" clearable placeholder="搜索资产、项目或分类" />
      <section class="filters" aria-label="筛选条件">
        <label>项目<ElSelect v-model="projectFilter" popper-class="workbench-select-popper"><ElOption label="全部项目" value="all" /><ElOption v-for="p in projects" :key="p.id" :label="p.name" :value="String(p.id)" /></ElSelect></label>
        <label>收藏<ElSelect v-model="favoriteFilter" popper-class="workbench-select-popper"><ElOption label="全部" value="all" /><ElOption label="未收藏" value="0" /><ElOption label="红色" value="1" /><ElOption label="黄色" value="2" /><ElOption label="绿色" value="3" /><ElOption label="蓝色" value="4" /></ElSelect></label>
        <label>时间<ElSelect v-model="dateFilter" popper-class="workbench-select-popper"><ElOption label="全部时间" value="all" /><ElOption label="最近 7 天" value="7" /><ElOption label="最近 30 天" value="30" /></ElSelect></label>
        <label class="color-share-filter">颜色占比<div class="color-filter-options" aria-label="自动识别的五个主色"><button v-for="color in detectedColors" :key="color.hex" :class="{ active: colorFilterActive && color.hex === colorTarget }" :style="{ backgroundColor: color.hex }" :title="`使用主色 ${color.hex}（${color.percentage.toFixed(1)}%）`" @click="useDetectedColor(color)" /><span class="custom-color-option" title="自选颜色"><input v-model="colorTarget" type="color" aria-label="自选筛选颜色" @change="colorFilterActive = true" /><span>+</span></span></div></label>
        <button v-if="hasFilters" class="clear-btn" @click="resetFilters">清除</button>
      </section>
      <button class="primary-btn" type="button" @click="showCreateProject = true">＋ 新建项目</button>
    </div>

    <section class="section-block recent-section">
      <div class="section-heading">
        <div><h2>最近生成</h2><span>{{ assets.length }} 项{{ mediaType === 'all' ? '素材' : mediaType === 'picture' ? '图片' : '视频' }}</span></div>
        <button v-if="assets.length > 8" class="text-btn" @click="recentExpanded = !recentExpanded">{{ recentExpanded ? '收起' : '查看全部' }}</button>
      </div>
      <div v-if="loading" class="state">正在整理素材…</div>
      <div v-else-if="recentAssets.length === 0" class="state">没有符合当前条件的素材</div>
      <div v-else :class="recentExpanded ? 'masonry' : 'recent-row'" @wheel="handleRecentWheel">
        <article v-for="asset in recentAssets" :key="asset.id" class="asset-card">
          <video v-if="asset.asset_type === 'video'" :src="mediaUrl(asset.location)" muted preload="metadata" @loadedmetadata="prepareVideoThumb" @click="openAsset(asset)" />
          <img v-else :src="mediaUrl(asset.location)" :alt="asset.name || '生成资产'" @click="openAsset(asset)" />
          <div class="asset-meta"><span>{{ asset.name || asset.location.split(/[/\\]/).pop() }}</span><small>{{ asset.created_at ? new Date(asset.created_at).toLocaleDateString() : '' }}</small></div>
          <div class="asset-actions"><button @click="addToProject(asset)">加入项目</button><button @click="downloadAsset(asset)">下载</button><FavoriteHeart :tag="asset.tag || 0" @change="tag => setFavorite(asset, tag)" /></div>
        </article>
      </div>
    </section>

    <section class="projects-area">
      <div class="projects-title"><h2>项目</h2><span>{{ projects.length }} 个</span><button v-if="projects.length>6" class="text-btn all-projects" @click="router.push('/projects')">查看全部</button></div>
      <div v-if="projects.length === 0" class="state">还没有项目，先创建一个开始整理素材</div>
      <div v-else class="project-grid"><ProjectCard v-for="project in visibleProjects" :key="project.id" :project="{...project,asset_count:project.asset_count??project.categories.flatMap(c=>c.assets).length}" :fallback-assets="projectFallbackAssets(project)" @open="openProject(project)" /></div>
    </section>

    <ElDialog v-model="showCreateProject" title="新建项目" width="380px" align-center>
      <ElInput v-model="newProjectName" placeholder="项目名称" @keyup.enter="createProject" />
      <template #footer><button class="clear-btn" @click="showCreateProject = false">取消</button><button class="primary-btn" :disabled="creatingProject" @click="createProject">创建</button></template>
    </ElDialog>

    <MediaViewer :visible="Boolean(previewAsset)" :item="viewerItem" @close="previewAsset = null" />
    <ProjectManager :visible="showProjectManager" :asset-id="managerAssetId" mode="add" @close="showProjectManager = false" />
  </main>
</template>

<style scoped>
.workbench { min-height: calc(100vh - 22px); padding: 36px 40px 80px; color: var(--color-text); background: linear-gradient(180deg, rgba(2,4,8,.66), rgba(2,4,8,.56) 48%, rgba(2,4,8,.72)); }
.topbar { display: flex; align-items: center; justify-content: space-between; gap: 28px; margin-bottom: 22px; }
h1 { margin: 0; font-size: 27px; font-weight: 600; } h2, h3 { margin: 0; font-weight: 560; }
.top-actions { display: flex; align-items: end; gap: 24px; margin: 18px 0 34px; }.search { flex: 1 1 260px; min-width: 200px; max-width: 380px; }
.primary-btn,.clear-btn,.text-btn { border: 0; cursor: pointer; font: inherit; }
.primary-btn { height: 40px; padding: 0 4px 0 14px; background: transparent; color: rgba(255,255,255,.82); font-size: 12px; font-weight: 500; }
.primary-btn:hover { color: #fff; }
.media-tabs { display: flex; gap: 28px; }
.media-tabs button { position: relative; padding: 0 2px 13px; border: 0; background: none; color: rgba(255,255,255,.4); cursor: pointer; }
.media-tabs button.active { color: #fff; }.media-tabs button.active::after { content:''; position:absolute; left:0; right:0; bottom:5px; height:1px; background:rgba(255,255,255,.72); }
.recent-section { margin-top: 0; }
.filters { display: flex; align-items: end; gap: 18px; margin: 0; padding: 0; overflow-x: auto; }
.filters label { display: grid; gap: 7px; flex: 0 0 auto; color: rgba(255,255,255,.4); font-size: 10px; }
.color-filter-options { display:flex; align-items:center; min-height:30px; gap:7px; }.color-filter-options > button,.custom-color-option { position:relative; width:22px; height:22px; padding:0; overflow:hidden; border:1px solid rgba(255,255,255,.24); border-radius:50%; cursor:pointer; box-shadow:0 0 0 1px transparent; }.color-filter-options > button.active { box-shadow:0 0 0 2px rgba(255,255,255,.75); }.custom-color-option { display:grid; place-items:center; border-style:dashed; color:rgba(255,255,255,.74); font-size:15px; line-height:1; }.custom-color-option:hover { border-color:rgba(255,255,255,.62); color:#fff; }.custom-color-option input { position:absolute; inset:0; width:100%; height:100%; padding:0; opacity:0; cursor:pointer; }
.filters select { min-width:112px; height:34px; padding:0 30px 0 2px; border:0; border-bottom:1px solid rgba(255,255,255,.14); border-radius:0; outline:0; appearance:none; -webkit-appearance:none; color:rgba(255,255,255,.76); font-size:12px; line-height:34px; cursor:pointer; color-scheme:dark; background-color:transparent; background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath d='M3 4.5 6 7.5 9 4.5' fill='none' stroke='%23858c98' stroke-width='1.25' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E"); background-repeat:no-repeat; background-position:right 5px center; transition:border-color .18s ease,color .18s ease; }
.filters select:hover { color:#fff; border-bottom-color:rgba(255,255,255,.3); }
.filters select:focus { color:#fff; border-bottom-color:var(--color-primary); }
.filters select option { background:#0c1017; color:rgba(255,255,255,.88); }
.filters :deep(.el-select) { width:112px; }
.filters :deep(.el-select__wrapper) { min-height:34px; padding:0 3px; border:0!important; border-bottom:1px solid rgba(255,255,255,.14)!important; border-radius:0!important; background:transparent!important; box-shadow:none!important; }
.filters :deep(.el-select__wrapper:hover) { border-bottom-color:rgba(255,255,255,.3)!important; }
.filters :deep(.el-select__wrapper.is-focused) { border-bottom-color:var(--color-primary)!important; }
.filters :deep(.el-select__selected-item) { color:rgba(255,255,255,.76); font-size:12px; }
.filters :deep(.el-select__caret) { color:rgba(255,255,255,.38); font-size:12px; }
:global(.workbench-select-popper.el-popper) { border:1px solid rgba(255,255,255,.1)!important; border-radius:7px!important; background:#0c1017!important; box-shadow:0 16px 44px rgba(0,0,0,.42)!important; }
:global(.workbench-select-popper .el-select-dropdown__item) { height:34px; padding:0 11px; color:rgba(255,255,255,.62); font-size:11px; line-height:34px; }
:global(.workbench-select-popper .el-select-dropdown__item:hover),:global(.workbench-select-popper .el-select-dropdown__item.is-hovering) { background:rgba(255,255,255,.055)!important; color:#fff; }
:global(.workbench-select-popper .el-select-dropdown__item.is-selected) { background:rgba(166,231,226,.08)!important; color:var(--color-primary); font-weight:500; }
:global(.workbench-select-popper .el-popper__arrow) { display:none; }
.clear-btn { height: 32px; padding: 0; border-radius: 0; background: transparent; color: rgba(255,255,255,.42); }
.section-block,.project-section { border: 0; padding-top: 0; }
.section-heading,.projects-title { display:flex; justify-content:space-between; align-items:center; gap:20px; margin-bottom:16px; }
.section-heading>div,.projects-title { display:flex; align-items:baseline; gap:12px; }.section-heading h2,.projects-title h2 { font-size:18px; }.section-heading h3 { font-size:16px; }
.section-heading span,.projects-title span { color:rgba(255,255,255,.3); font-size:11px; }.text-btn { background:none; color:var(--color-primary); font-size:12px; }
.recent-row { display:flex; gap:12px; overflow-x:auto; padding:2px 0 10px; }.recent-row .asset-card { flex:0 0 216px; }
.recent-row { scrollbar-width: none; }
.recent-row::-webkit-scrollbar { display: none; }
.masonry { columns: 4 230px; column-gap: 14px; }.asset-card { position:relative; break-inside:avoid; margin:0 0 18px; overflow:hidden; border:0; border-radius:7px; background:rgba(12,16,22,.48); box-shadow:0 8px 28px rgba(0,0,0,.1); }
.asset-card img,.asset-card video { display:block; width:100%; min-height:150px; max-height:360px; object-fit:cover; cursor:pointer; border-radius:7px; background:linear-gradient(145deg,#10151c,#080b10); opacity:.94; filter:brightness(.84) contrast(.94) saturate(.88); transition:opacity .22s ease,filter .22s ease; }
.asset-card:hover img,.asset-card:hover video { opacity:1; filter:brightness(.96) contrast(.98) saturate(.98); }
.recent-row .asset-card img,.recent-row .asset-card video { height:142px; }
.asset-meta { position:absolute; z-index:2; inset:auto 0 0; display:flex; justify-content:space-between; align-items:end; gap:10px; padding:28px 10px 10px; background:linear-gradient(180deg,transparent,rgba(0,0,0,.78)); opacity:0; transform:translateY(5px); pointer-events:none; transition:opacity .2s ease,transform .2s ease; }.asset-card:hover .asset-meta,.asset-card:focus-within .asset-meta { opacity:1; transform:none; }.asset-meta span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:11px; }.asset-meta small { flex:none; color:rgba(255,255,255,.5); font-size:9px; }
.asset-actions { position:absolute; z-index:2; top:9px; right:9px; display:flex; align-items:center; gap:6px; opacity:0; transition:opacity .2s; }.asset-card:hover .asset-actions,.asset-card:focus-within .asset-actions { opacity:1; }
.asset-actions button { height:27px; padding:0 9px; border:1px solid rgba(255,255,255,.18); border-radius:8px; background:rgba(0,0,0,.72); color:#fff; font-size:10px; cursor:pointer; }
.projects-area { margin-top:44px; }.projects-title { justify-content:flex-start; margin-bottom:18px; }.projects-title .all-projects{margin-left:auto}.project-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
.state,.project-empty { padding:48px 18px; border:1px dashed rgba(255,255,255,.1); border-radius:12px; color:rgba(255,255,255,.32); text-align:center; font-size:12px; }
.project-empty { padding:30px 18px; }.viewer { position:fixed; inset:0; z-index:2000; display:grid; place-items:center; padding:5vw; background:rgba(0,0,0,.9); }.viewer img { max-width:100%; max-height:90vh; object-fit:contain; }.viewer-close { position:fixed; top:24px; right:28px; border:0; background:none; color:#fff; font-size:34px; cursor:pointer; }
:deep(.search .el-input__wrapper) { border: 0 !important; border-bottom: 1px solid rgba(255,255,255,.13) !important; border-radius: 0 !important; background: transparent !important; }
@media (max-width: 980px){.project-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media (max-width: 760px) { .workbench { padding:28px 18px 60px; }.topbar { align-items:center; }.top-actions { width:100%; flex-wrap:wrap; }.search { width:100%; max-width:none; flex-basis:100%; }.media-tabs { gap:24px; }.masonry { columns:1; }.recent-row .asset-card { flex-basis:78vw; }.asset-actions,.asset-meta { opacity:1; transform:none; }.filters { width:100%; margin-right:-18px; }.project-grid{grid-template-columns:1fr} }
</style>
