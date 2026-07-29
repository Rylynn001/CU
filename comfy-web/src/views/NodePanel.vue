<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import AssetSidebar from '../components/AssetSidebar.vue'
import ImageViewer from '../components/ImageViewer.vue'
import VideoPlayer from '../components/VideoPlayer.vue'
import MediaCoverflow, { type CoverflowItem } from '../components/MediaCoverflow.vue'
import NodeGenSidePanel from '../components/NodeGenSidePanel.vue'
import { type SourceAsset, type GeneratedAsset } from '../components/NodeGenerateDialog.vue'
import BoardSelector from '../components/BoardSelector.vue'
import { fetchHistoryByAsset } from '../api/apiService'
import { getCurrentUserId } from '../utils/user'
import {
  loadBoard, saveBoard, createBoard as apiBoardCreate,
  renameBoard as apiBoardRename, deleteBoard as apiBoardDelete,
  listBoards,
  type BoardMeta, type NodePanelSnapshot,
} from '../services/nodePanelStorage'

const router = useRouter()

interface Asset {
  id: number
  location: string
  asset_type?: string
  tag?: number
  isGenPlaceholder?: boolean  // 生成占位符标记
  genMode?: 'image' | 'video'
}

interface PanelState {
  ratio: number
  assets: Asset[]
  // 溯源覆盖层：非空时 coverflow 改显示这些参考资产，退出溯源恢复 assets
  traceAssets: Asset[] | null
}

const PANEL_COUNT = 3
const PANEL_MIN_HEIGHT = 150

// ── Board（工作区）管理 ──────────────────────────────────────────────────
const boards = ref<BoardMeta[]>([])
const selectedBoardId = ref<number | null>(null)

function resetGenStates() {
  genStates.value = []
  activeGenId.value = null
}

async function loadBoards() {
  const userId = getCurrentUserId()
  if (!userId) return
  try {
    boards.value = await listBoards(Number(userId))
  } catch {
    // 后端不可用时不阻断页面
  }
}

async function enterBoard(id: number) {
  resetGenStates()
  panels.value.forEach((p) => { p.assets = []; p.ratio = 1; p.traceAssets = null })
  clearTrace()
  selectedBoardId.value = id
  dirty.value = false
  await restoreSnapshot()
}

async function handleCreateBoard(name: string) {
  const userId = getCurrentUserId()
  if (!userId) { ElMessage.warning('未登录'); return }
  try {
    const board = await apiBoardCreate(Number(userId), name)
    boards.value.unshift(board)
    await enterBoard(board.id)
  } catch {
    ElMessage.error('创建工作区失败')
  }
}

async function handleRenameBoard(id: number, name: string) {
  const userId = getCurrentUserId()
  if (!userId) return
  try {
    await apiBoardRename(id, Number(userId), name)
    const b = boards.value.find((b) => b.id === id)
    if (b) b.name = name
  } catch {
    ElMessage.error('重命名失败')
  }
}

async function handleDeleteBoard(id: number) {
  const userId = getCurrentUserId()
  if (!userId) return
  try {
    await apiBoardDelete(id, Number(userId))
    boards.value = boards.value.filter((b) => b.id !== id)
    if (selectedBoardId.value === id) {
      selectedBoardId.value = null
      resetGenStates()
      panels.value.forEach((p) => { p.assets = []; p.ratio = 1; p.traceAssets = null })
      clearTrace()
    }
  } catch {
    ElMessage.error('删除失败')
  }
}

function exitToSelector() {
  if (dirty.value) handleSave()
  selectedBoardId.value = null
  resetGenStates()
  panels.value.forEach((p) => { p.assets = []; p.ratio = 1; p.traceAssets = null })
  clearTrace()
}

const panels = ref<PanelState[]>([
  { ratio: 1, assets: [], traceAssets: null },
  { ratio: 1, assets: [], traceAssets: null },
  { ratio: 1, assets: [], traceAssets: null },
])

const coverflowRefs = ref<Array<InstanceType<typeof MediaCoverflow> | null>>([])
const panelRefs = ref<Array<HTMLElement | null>>([])
const genDockTop = ref(0)

function syncGenDockTop() {
  genDockTop.value = panelRefs.value[1]?.offsetTop ?? 0
}

// ── 持久化 ──────────────────────────────────────────────────────────────
const saving = ref(false)
const dirty = ref(false)
const lastSavedAt = ref<number | null>(null)

function markDirty() { dirty.value = true }

// 快照当前面板 → 存储；只存 assetId 与 ratio
async function handleSave() {
  if (!selectedBoardId.value) return
  const userId = getCurrentUserId()
  if (!userId) return
  saving.value = true
  try {
    const snapshot: NodePanelSnapshot = {
      panels: panels.value.map((p) => ({
        assetIds: p.assets.map((a) => a.id),
        ratio: p.ratio,
      })),
      updatedAt: Date.now(),
    }
    await saveBoard(selectedBoardId.value, Number(userId), snapshot)
    // 同步更新 board 列表中的 updatedAt
    const board = boards.value.find((b) => b.id === selectedBoardId.value)
    if (board) board.updatedAt = snapshot.updatedAt
    dirty.value = false
    lastSavedAt.value = snapshot.updatedAt
    ElMessage.success('已保存')
  } catch {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

// 根据 assetId 列表拉回完整资产（复用 assets/by-ids）
async function fetchAssetsByIds(ids: number[]): Promise<Asset[]> {
  if (!ids.length) return []
  try {
    const res = await fetch('/api/api-proxy/assets/by-ids', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids }),
    })
    if (!res.ok) throw new Error()
    const data = await res.json()
    const map = new Map<number, Asset>((data.assets || []).map((a: Asset) => [a.id, a]))
    // 保持原有顺序
    return ids.map((id) => map.get(id)).filter(Boolean) as Asset[]
  } catch {
    return []
  }
}

async function restoreSnapshot() {
  if (!selectedBoardId.value) return
  const userId = getCurrentUserId()
  if (!userId) return
  const snap = await loadBoard(selectedBoardId.value, Number(userId))
  if (!snap) return
  for (let i = 0; i < PANEL_COUNT && i < snap.panels.length; i++) {
    const p = snap.panels[i]
    panels.value[i].ratio = p.ratio || 1
    panels.value[i].assets = await fetchAssetsByIds(p.assetIds)
  }
  lastSavedAt.value = snap.updatedAt
  dirty.value = false
}

// ── 拖拽视觉反馈 ────────────────────────────────────────────────────────
const isDragging = ref(false)
const dragOverIndex = ref<number | null>(null)
const genDragOverId = ref<number | null>(null)
function handleGlobalDragStart() { isDragging.value = true }
function handleGlobalDragEnd() {
  isDragging.value = false
  dragOverIndex.value = null
  genDragOverId.value = null
}

onMounted(() => {
  window.addEventListener('dragstart', handleGlobalDragStart)
  window.addEventListener('dragend', handleGlobalDragEnd)
  window.addEventListener('resize', syncGenDockTop)
  loadBoards()
})
onUnmounted(() => {
  window.removeEventListener('dragstart', handleGlobalDragStart)
  window.removeEventListener('dragend', handleGlobalDragEnd)
  window.removeEventListener('resize', syncGenDockTop)
  stopLineLoop()
})

const panelStyles = computed(() => panels.value.map((panel) => ({
  flexGrow: panel.ratio,
  flexBasis: 0,
})))

function getMediaUrl(location: string) {
  return `/api/api-proxy/output/${location.split(/[/\\]/).pop()}`
}

function isVideo(asset: Asset) {
  const ext = asset.location.split('.').pop()?.toLowerCase()
  return ['mp4', 'mov', 'avi', 'webm'].includes(ext || '')
}

// 视频首帧：加 #t=0.1 让 <video> 显示首帧画面而非黑屏
function getPoster(asset: Asset) {
  return `${getMediaUrl(asset.location)}#t=0.1`
}

// 接收 AssetSidebar 的 select 事件（payload 为数组）或拖放的单个资产
function handleSidebarSelect(payload: Asset | Asset[]) {
  const list = Array.isArray(payload) ? payload : [payload]
  addAssetToPanel(list)
}

function addAssetToPanel(payload: Asset | Asset[], index?: number) {
  const assets = Array.isArray(payload) ? payload : [payload]
  const targets = index === undefined ? panels.value : [panels.value[index]]
  targets.forEach((panel) => {
    assets.forEach((asset) => {
      if (!panel.assets.some((item) => item.id === asset.id)) panel.assets.push(asset)
    })
  })
  markDirty()
  ElMessage.success(assets.length > 1 ? `已添加 ${assets.length} 个素材` : '已添加到节点面板')
}

function getDraggedAssets(payload: any): Asset[] {
  const list = Array.isArray(payload.assets) ? payload.assets : [payload]
  return list
    .filter((item: any) => typeof item?.id === 'number' && typeof item?.location === 'string')
    .map((item: any) => ({
      id: item.id,
      location: item.location,
      asset_type: item.asset_type,
    }))
}

// 拖拽资产到指定面板（支持从 coverflow 跨面板移动）
function handlePanelDrop(e: DragEvent, index: number) {
  isDragging.value = false  // drop 触发时强制复位，防止 dragend 未触发导致遮罩残留
  dragOverIndex.value = null
  const data = e.dataTransfer?.getData('application/json')
  if (!data) return
  try {
    const payload = JSON.parse(data)
    const fromPanel: number = payload.fromPanelIndex ?? -1
    const assets = getDraggedAssets(payload)
    if (!assets.length) return
    const job = activeGenState.value
    if (
      job && !job.submitted && !job.generating &&
      index === job.panelIndex && fromPanel === job.refPanelIndex
    ) {
      const refIds = getValidGenRefIds(assets.map((asset) => asset.id), fromPanel, getGenMode(job))
      refIds.forEach((id) => addGenRef(id, fromPanel))
      return
    }
    addAssetToPanel(assets, index)
    // 从 coverflow 拖来的：跨面板则从来源面板移除（移动而非复制）
    if (fromPanel >= 0 && fromPanel !== index) {
      const movedIds = new Set(assets.map((asset) => asset.id))
      panels.value[fromPanel].assets = panels.value[fromPanel].assets.filter((asset) => !movedIds.has(asset.id))
      markDirty()
    }
  } catch {
    // 忽略非资产数据
  }
}

function handlePanelDragLeave(e: DragEvent, index: number) {
  const related = e.relatedTarget as Node | null
  if (!related || !(e.currentTarget as HTMLElement).contains(related)) {
    if (dragOverIndex.value === index) dragOverIndex.value = null
  }
}

function handleGenPanelDrop(e: DragEvent, job: GenState) {
  genDragOverId.value = null
  activeGenId.value = job.placeholderTempId
  handlePanelDrop(e, job.panelIndex)
}

function handleGenPanelDragLeave(e: DragEvent, id: number) {
  const related = e.relatedTarget as Node | null
  if (!related || !(e.currentTarget as HTMLElement).contains(related)) {
    if (genDragOverId.value === id) genDragOverId.value = null
  }
}

// 面板资产 → coverflow 数据；溯源激活时优先显示 traceAssets
const coverflowItems = computed(() =>
  panels.value.map((panel) => {
    const source = panel.traceAssets ?? panel.assets
    return source.map<CoverflowItem>((asset) => ({
      id: asset.id,
      url: asset.isGenPlaceholder ? '' : getMediaUrl(asset.location),
      poster: asset.isGenPlaceholder ? '' : getPoster(asset),
      isVideo: !asset.isGenPlaceholder && isVideo(asset),
      location: asset.location,
      isGenPlaceholder: asset.isGenPlaceholder,
      genMode: asset.genMode,
      isGenerating: genStates.value.some((job) => job.placeholderTempId === asset.id && job.generating),
    }))
  })
)

// 生成侧边面板：已选参考图的完整 SourceAsset 列表；只读基础资产，避免普通溯源覆盖影响生成任务
function getGenRefAssets(job: GenState): SourceAsset[] {
  if (!job.refAssetIds.length) return []
  const upper = panels.value[job.refPanelIndex]
  if (!upper) return []
  return job.refAssetIds
    .map((id) => upper.assets.find((a) => a.id === id))
    .filter(Boolean)
    .map((a) => ({
      id: a!.id,
      url: getMediaUrl(a!.location),
      isVideo: a!.asset_type === 'video' || isVideo(a!),
    }))
}

// 当前激活的生成任务，用于参考图选择和参数面板显示
const activeGenState = computed(() =>
  genStates.value.find((job) => job.placeholderTempId === activeGenId.value) ?? null,
)
const openGenState = computed(() => activeGenState.value?.panelOpen ? activeGenState.value : null)
const displayedCoverflowItems = computed(() => {
  const job = openGenState.value
  if (!job) return coverflowItems.value
  return coverflowItems.value.map((items, index) => {
    if (index === job.panelIndex) {
      return items.filter((item) => item.id === job.placeholderTempId)
    }
    return index > job.panelIndex ? [] : items
  })
})
const genDockStyle = computed(() => ({ top: `${genDockTop.value}px` }))
const hasGenLinks = computed(() => genStates.value.some((job) => job.refAssetIds.length > 0))

function findGenState(id: number) {
  return genStates.value.find((job) => job.placeholderTempId === id)
}

function removeGenLinks(id: number) {
  if (trace.value) {
    const remaining = trace.value.links.filter((link) => link.fromId !== id)
    trace.value = remaining.length ? { ...trace.value, links: remaining } : null
  }
}

function removeAssetById(id: number, index: number) {
  panels.value[index].assets = panels.value[index].assets.filter((item) => item.id !== id)
  markDirty()
  // 移除的资产若正处于溯源链中，清空溯源
  if (trace.value) clearTrace()
  clearGenState(id)
}

// ── 生成占位符 ────────────────────────────────────────────────────────────
let genTempIdCounter = -1

interface GenState {
  placeholderTempId: number
  panelIndex: number
  refAssetIds: number[]   // Fix3: 改为多选数组
  refPanelIndex: number   // 参考图所在面板（固定为 panelIndex - 1）
  prompt: string
  submitted: boolean
  generating: boolean
  panelOpen: boolean
}
const genStates = ref<GenState[]>([])
const activeGenId = ref<number | null>(null)

function getGenMode(job: GenState): 'image' | 'video' {
  return panels.value[job.panelIndex]?.assets.find(
    (asset) => asset.id === job.placeholderTempId,
  )?.genMode ?? 'image'
}

function getValidGenRefIds(
  refAssetIds: number[],
  refPanelIndex: number,
  mode: 'image' | 'video',
) {
  if (mode !== 'image') return refAssetIds
  const refPanel = panels.value[refPanelIndex]
  const validIds = refAssetIds.filter((id) => {
    const asset = refPanel?.assets.find((item) => item.id === id)
    return asset && asset.asset_type !== 'video' && !isVideo(asset)
  })
  if (validIds.length !== refAssetIds.length) {
    ElMessage.warning('图片生成不支持视频参考，已忽略视频素材')
  }
  return validIds
}

function addGenPlaceholder(panelIndex: number, mode: 'image' | 'video') {
  if (panelIndex !== 1) return
  const tempId = genTempIdCounter--
  panels.value[panelIndex].assets.push({
    id: tempId,
    location: '',
    asset_type: mode === 'video' ? 'video' : 'picture',
    isGenPlaceholder: true,
    genMode: mode,
  })
  markDirty()
}

// 激活生成模式（点击占位符）
function activateGen(item: CoverflowItem, panelIndex: number) {
  if (panelIndex <= 0) return
  const existing = findGenState(item.id)
  if (existing) {
    activeGenId.value = item.id
    existing.panelOpen = true
    nextTick(syncGenDockTop)
    return
  }
  const job: GenState = {
    placeholderTempId: item.id,
    panelIndex,
    refAssetIds: [],
    refPanelIndex: panelIndex - 1,
    prompt: '',
    submitted: false,
    generating: false,
    panelOpen: true,
  }
  genStates.value.push(job)
  activeGenId.value = item.id
  nextTick(syncGenDockTop)
}

function handleGenPlaceholderDrop(e: DragEvent, item: CoverflowItem, panelIndex: number) {
  const data = e.dataTransfer?.getData('application/json')
  if (!data) return
  try {
    const payload = JSON.parse(data)
    const fromPanel: number = payload.fromPanelIndex ?? -1
    const assets = getDraggedAssets(payload)
    if (!assets.length) return
    if (fromPanel !== panelIndex - 1) {
      handlePanelDrop(e, panelIndex)
      return
    }
    const refIds = getValidGenRefIds(assets.map((asset) => asset.id), fromPanel, item.genMode ?? 'image')
    if (!refIds.length) return
    isDragging.value = false
    dragOverIndex.value = null
    activateGen(item, panelIndex)
    refIds.forEach((id) => addGenRef(id, fromPanel))
  } catch {
    // 忽略非资产数据
  }
}

function addGenRef(refAssetId: number, refPanelIndex: number) {
  const job = activeGenState.value
  if (!job || job.submitted || job.generating) return
  const asset = panels.value[refPanelIndex]?.assets.find((item) => item.id === refAssetId)
  if (!asset || asset.isGenPlaceholder) return
  if (getGenMode(job) === 'image' && (asset.asset_type === 'video' || isVideo(asset))) {
    ElMessage.warning('图片生成不支持视频参考')
    return
  }
  if (!job.refAssetIds.includes(refAssetId)) {
    job.refAssetIds = [...job.refAssetIds, refAssetId]
  }
  job.refPanelIndex = refPanelIndex
  nextTick().then(() => startLineLoop())
}

function removeGenRef(job: GenState, refAssetId: number) {
  if (job.submitted || job.generating) return
  job.refAssetIds = job.refAssetIds.filter((id) => id !== refAssetId)
  updateLines()
  if (!trace.value && !hasGenLinks.value) stopLineLoop()
}

// toggle 多选参考图，多条连线
function selectGenRef(refAssetId: number, refPanelIndex: number) {
  const job = activeGenState.value
  if (!job || job.submitted || job.generating) return
  if (job.refAssetIds.includes(refAssetId)) {
    removeGenRef(job, refAssetId)
  } else {
    addGenRef(refAssetId, refPanelIndex)
  }
}

function clearGenState(pid: number) {
  genStates.value = genStates.value.filter((job) => job.placeholderTempId !== pid)
  removeGenLinks(pid)
  if (activeGenId.value === pid) {
    const next = genStates.value[genStates.value.length - 1]
    activeGenId.value = next?.placeholderTempId ?? null
  }
  updateLines()
  if (!trace.value && !hasGenLinks.value) stopLineLoop()
}

// 只关闭参数面板 UI，标记已提交，保留 genState 让生成任务在后台继续
function closeGenPanel() {
  const job = activeGenState.value
  if (!job) return
  job.panelOpen = false
  job.submitted = job.generating
  if (!job.generating) activeGenId.value = null
  if (job.refAssetIds.length > 0) {
    startLineLoop()
  }
}

// 生成完成：用真实资产替换占位符
function onGenCompleted(pid: number, asset: GeneratedAsset) {
  const job = findGenState(pid)
  if (!job) return
  const idx = panels.value[job.panelIndex].assets.findIndex(
    (a) => a.id === job.placeholderTempId
  )
  if (idx >= 0) {
    const filename = asset.url.split(/[/\\?]/).pop() || `${asset.id}`
    panels.value[job.panelIndex].assets.splice(idx, 1, {
      id: asset.id,
      location: filename,
      asset_type: asset.isVideo ? 'video' : 'picture',
    })
  }
  clearGenState(pid)
  markDirty()
}

function onGenGenerating(pid: number, value: boolean) {
  const job = findGenState(pid)
  if (job) job.generating = value
}

// ── 溯源 ────────────────────────────────────────────────────────────────
// 每条连线：下层选中卡片 → 上层某张参考卡片
interface TraceLink {
  fromPanel: number
  fromId: number
  toPanel: number
  toId: number
}
const trace = ref<{ links: TraceLink[]; savedRatios: number[] } | null>(null)
const linePaths = ref<string[]>([])

// 每个面板当前高亮的资产 id（连线端点）
const highlightIds = computed<number[][]>(() => {
  const arr: number[][] = [[], [], []]
  if (trace.value) {
    for (const link of trace.value.links) {
      arr[link.fromPanel]?.push(link.fromId)
      arr[link.toPanel]?.push(link.toId)
    }
  }
  // gen 占位符及其参考图始终高亮，不受 trace 清除影响
  for (const job of genStates.value) {
    arr[job.panelIndex]?.push(job.placeholderTempId)
    for (const refId of job.refAssetIds) {
      arr[job.refPanelIndex]?.push(refId)
    }
  }
  return arr
})

// Fix1: 溯源根节点（最深层触发溯源的面板及卡片）
const traceRoot = computed<{ panelIndex: number; cardId: number } | null>(() => {
  if (!trace.value?.links.length) return null
  // 只看普通溯源链路（fromId >= 0 排除 gen 占位符负数 id）
  const traceLinks = trace.value.links.filter((l) => l.fromId >= 0)
  if (!traceLinks.length) return null
  const deepest = traceLinks.reduce((a, b) => a.fromPanel > b.fromPanel ? a : b)
  return { panelIndex: deepest.fromPanel, cardId: deepest.fromId }
})

// 点击某面板资产 → 溯源它的参考素材，或处理生成模式
async function handleCardSelect(item: CoverflowItem, panelIndex: number) {
  // ① 生成模式 — 上层面板被点击作为参考图（仅未提交时）
  if (activeGenState.value && !activeGenState.value.submitted && !activeGenState.value.generating && panelIndex === activeGenState.value.panelIndex - 1) {
    if (!item.isGenPlaceholder) {
      selectGenRef(item.id, panelIndex)
    }
    return
  }

  // ② 点击的是占位符 → 激活生成模式
  if (item.isGenPlaceholder) {
    activateGen(item, panelIndex)
    return
  }

  // ③ 普通溯源（第 1 面板无上层）
  if (panelIndex <= 0) return

  const userId = getCurrentUserId()
  if (!userId) { ElMessage.warning('未登录'); return }

  try {
    const record = await fetchHistoryByAsset(item.id, userId)
    const inputIds = record?.input_asset_ids ?? []
    if (!inputIds.length) {
      ElMessage.info('该资产没有参考素材')
      return
    }
    const refAssets = await fetchAssetsByIds(inputIds)
    if (!refAssets.length) {
      ElMessage.info('参考素材已不可用')
      return
    }

    const upper = panelIndex - 1

    // 上层链路失效：清空 upper 及其以上所有面板的溯源覆盖
    for (let t = upper; t >= 0; t--) {
      panels.value[t].traceAssets = null
    }
    // 上一面板显示本次参考素材（覆盖态）
    panels.value[upper].traceAssets = refAssets

    // 链路：保留下层（toPanel >= panelIndex），丢弃本层及以上（toPanel <= upper），再追加新链路
    const kept = (trace.value?.links ?? []).filter((l) => l.toPanel >= panelIndex)
    const added: TraceLink[] = refAssets.map((r) => ({
      fromPanel: panelIndex,
      fromId: item.id,
      toPanel: upper,
      toId: r.id,
    }))
    // 首次激活溯源时保存各面板 ratio，并均分高度确保所有面板可见
    const savedRatios = trace.value?.savedRatios ?? panels.value.map((p) => p.ratio)
    if (!trace.value) {
      panels.value.forEach((p) => { p.ratio = 1 })
    }
    trace.value = { links: [...kept, ...added], savedRatios }

    await nextTick()
    startLineLoop()
  } catch {
    ElMessage.error('溯源失败')
  }
}

function clearTrace() {
  // 恢复溯源前的面板高度
  if (trace.value?.savedRatios) {
    panels.value.forEach((p, i) => { p.ratio = trace.value!.savedRatios[i] })
  }
  trace.value = null
  linePaths.value = []
  panels.value.forEach((p) => { p.traceAssets = null })
  // gen 连线还在时不停 loop，让 updateLines 继续渲染 gen 连线
  if (hasGenLinks.value) {
    return
  }
  stopLineLoop()
}

// ── 连线绘制：rAF 循环，每帧从 coverflow 查卡片中心，更新 SVG path ──────
let lineRaf = 0
const overlayRef = ref<SVGSVGElement | null>(null)

function startLineLoop() {
  if (lineRaf) return
  const loop = () => {
    updateLines()
    lineRaf = requestAnimationFrame(loop)
  }
  lineRaf = requestAnimationFrame(loop)
}

function stopLineLoop() {
  if (lineRaf) { cancelAnimationFrame(lineRaf); lineRaf = 0 }
}

function buildCurvePath(fromCf: any, toCf: any, fromId: number, toId: number): string | null {
  const from = fromCf?.getCardAnchor(fromId, 'top')
  const to = toCf?.getCardAnchor(toId, 'bottom')
  if (!from || !to) return null
  const dy = Math.abs(from.y - to.y)
  const pull = Math.max(30, dy * 0.4)
  return `M ${from.x} ${from.y} C ${from.x} ${from.y - pull}, ${to.x} ${to.y + pull}, ${to.x} ${to.y}`
}

function updateLines() {
  const hasTrace = !!trace.value
  if (!hasTrace && !hasGenLinks.value) { linePaths.value = []; return }

  const paths: string[] = []

  // 溯源连线
  if (trace.value) {
    for (const link of trace.value.links) {
      const p = buildCurvePath(
        coverflowRefs.value[link.fromPanel],
        coverflowRefs.value[link.toPanel],
        link.fromId, link.toId,
      )
      if (p) paths.push(p)
    }
  }

  // gen 参考连线：独立渲染，不受 trace 清除影响
  for (const job of genStates.value) {
    if (job.panelOpen || !job.refAssetIds.length) continue
    const fromCf = coverflowRefs.value[job.panelIndex]
    const toCf = coverflowRefs.value[job.refPanelIndex]
    for (const refId of job.refAssetIds) {
      const p = buildCurvePath(fromCf, toCf, job.placeholderTempId, refId)
      if (p) paths.push(p)
    }
  }

  linePaths.value = paths
}

// ── 预览（双击） ────────────────────────────────────────────────────────
const showImageViewer = ref(false)
const previewUrl = ref('')
const showVideoPlayer = ref(false)
const activeVideoUrl = ref('')
const activeVideoId = ref<number | undefined>(undefined)

function openPreview(item: CoverflowItem) {
  if (item.isVideo) {
    activeVideoUrl.value = item.url
    activeVideoId.value = item.id
    showVideoPlayer.value = true
  } else {
    previewUrl.value = item.url
    showImageViewer.value = true
  }
}

// ── 面板高度拖拽 ────────────────────────────────────────────────────────
const resizing = ref<{
  index: number
  startY: number
  first: number
  second: number
  pixelsPerRatio: number
} | null>(null)

function startResize(index: number, event: PointerEvent) {
  const first = panels.value[index]
  const second = panels.value[index + 1]
  const firstEl = panelRefs.value[index]
  const secondEl = panelRefs.value[index + 1]
  if (!first || !second || !firstEl || !secondEl) return
  const total = first.ratio + second.ratio
  const pixelsPerRatio = (firstEl.offsetHeight + secondEl.offsetHeight) / total
  resizing.value = { index, startY: event.clientY, first: first.ratio, second: second.ratio, pixelsPerRatio }
  window.addEventListener('pointermove', handleResize)
  window.addEventListener('pointerup', stopResize)
}

function handleResize(event: PointerEvent) {
  if (!resizing.value) return
  const { index, startY, first, second, pixelsPerRatio } = resizing.value
  const delta = (event.clientY - startY) / pixelsPerRatio
  const total = first + second
  const minRatio = Math.min(PANEL_MIN_HEIGHT / pixelsPerRatio, total / 2)
  const nextFirst = Math.min(Math.max(first + delta, minRatio), total - minRatio)
  panels.value[index].ratio = nextFirst
  panels.value[index + 1].ratio = total - nextFirst
  requestAnimationFrame(syncGenDockTop)
}

function stopResize() {
  if (resizing.value) markDirty()
  resizing.value = null
  window.removeEventListener('pointermove', handleResize)
  window.removeEventListener('pointerup', stopResize)
}
</script>

<template>
  <!-- Board 选择界面 -->
  <BoardSelector
    v-if="!selectedBoardId"
    :boards="boards"
    @enter="enterBoard"
    @create="handleCreateBoard"
    @delete="handleDeleteBoard"
    @rename="handleRenameBoard"
  />

  <!-- 工作区 -->
  <div v-else class="node-panel-page" :class="{ dragging: isDragging }">
    <div class="node-orb node-orb-2" />

    <!-- 顶部工具栏：返回 / 保存 -->
    <header class="node-toolbar">
      <button type="button" class="tb-btn" @click="exitToSelector">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="15 18 9 12 15 6" />
        </svg>
        工作区
      </button>

      <span class="tb-doc">{{ boards.find(b => b.id === selectedBoardId)?.name ?? '节点面板' }}</span>

      <div class="tb-right">
        <span class="tb-status" :class="{ dirty }">{{ dirty ? '未保存' : '已保存' }}</span>
        <button type="button" class="tb-btn primary" :disabled="saving" @click="handleSave">
          {{ saving ? '保存中...' : '保存' }}
        </button>
      </div>
    </header>

    <main class="panel-workspace">
      <section class="panel-shell" aria-label="节点预览面板">
        <div class="panel-stack" :class="{ 'is-gen-editing': openGenState }">
          <div class="panel-column">
            <template v-for="(panel, index) in panels" :key="index">
              <article
                :ref="(el) => { panelRefs[index] = el as HTMLElement }"
                class="preview-panel"
                :class="{
                  'drag-over': dragOverIndex === index,
                  'is-trace': panel.traceAssets !== null,
                  'is-gen-ref': activeGenState && !activeGenState.submitted && !activeGenState.generating && index === activeGenState.panelIndex - 1,
                  'is-gen-dim': activeGenState && !activeGenState.submitted && !activeGenState.generating && index < activeGenState.panelIndex - 1,
                  'is-gen-hidden': openGenState && index >= openGenState.panelIndex,
                }"
                :style="panelStyles[index]"
                @dragover.prevent
                @dragenter.prevent="dragOverIndex = index"
                @dragleave.prevent="handlePanelDragLeave($event, index)"
                @drop.prevent="handlePanelDrop($event, index)"
              >
                <!-- 面板标记 -->
                <div class="panel-tag">
                  面板 {{ index + 1 }}
                  <span v-if="panel.traceAssets !== null" class="trace-tag">溯源中</span>
                  <span v-if="activeGenState && !activeGenState.submitted && !activeGenState.generating && index === activeGenState.panelIndex - 1" class="gen-ref-tag">选择参考图</span>
                </div>

                <!-- 第三面板只展示生成结果，生成入口仅放在第二面板 -->
                <div v-if="index === 1 && !openGenState" class="panel-gen-btns">
                  <button type="button" class="gen-btn" @click="addGenPlaceholder(index, 'image')">＋图片生成</button>
                  <button type="button" class="gen-btn" @click="addGenPlaceholder(index, 'video')">＋视频生成</button>
                </div>

                <MediaCoverflow
                  v-if="displayedCoverflowItems[index].length > 0"
                  :ref="(el) => { coverflowRefs[index] = el as any }"
                  :items="displayedCoverflowItems[index]"
                  :highlight-ids="highlightIds[index]"
                  :panel-index="index"
                  :trace-root-id="traceRoot?.panelIndex === index ? traceRoot?.cardId : undefined"
                  @remove="(id) => removeAssetById(id, index)"
                  @open="openPreview"
                  @select="(item) => handleCardSelect(item, index)"
                  @drop-asset="(event) => handlePanelDrop(event, index)"
                  @drop-on-gen="(event, item) => handleGenPlaceholderDrop(event, item, index)"
                  @exit-trace="clearTrace"
                />
                <div v-else-if="!openGenState || index < openGenState.panelIndex" class="panel-empty">拖拽资产到此处</div>
              </article>

              <button
                v-if="index < panels.length - 1"
                :key="`resize-${index}`"
                type="button"
                class="resize-handle"
                :class="{ 'is-gen-hidden': openGenState && index >= openGenState.panelIndex }"
                aria-label="调整面板高度"
                @pointerdown.prevent="startResize(index, $event)"
              />
            </template>
          </div>

          <!-- 参数区位于 panel-stack 内部，并覆盖第二、三面板 -->
          <template v-for="job in genStates" :key="job.placeholderTempId">
            <aside
              class="gen-panel-dock"
              :class="{
                'is-open': job.panelOpen && activeGenId === job.placeholderTempId,
                'is-drag-over': genDragOverId === job.placeholderTempId,
              }"
              :style="genDockStyle"
              @dragover.prevent
              @dragenter.prevent="genDragOverId = job.placeholderTempId"
              @dragleave.prevent="handleGenPanelDragLeave($event, job.placeholderTempId)"
              @drop.prevent.stop="handleGenPanelDrop($event, job)"
            >
              <NodeGenSidePanel
                :mode="panels[job.panelIndex]?.assets.find(a => a.id === job.placeholderTempId)?.genMode ?? 'image'"
                :ref-assets="getGenRefAssets(job)"
                :prompt="job.prompt"
                @update:prompt="job.prompt = $event"
                @remove-ref="(id) => removeGenRef(job, id)"
                @close="closeGenPanel"
                @generating="(value) => onGenGenerating(job.placeholderTempId, value)"
                @generated="(asset) => onGenCompleted(job.placeholderTempId, asset)"
              />
            </aside>
          </template>

          <!-- 溯源退出按钮已移至根节点卡片上（见 MediaCoverflow traceRootId）-->
        </div>
      </section>

      <AssetSidebar @select="handleSidebarSelect" />
    </main>

    <!-- 溯源连线覆盖层 -->
    <Teleport to="body">
      <svg v-if="trace || hasGenLinks" ref="overlayRef" class="line-overlay" aria-hidden="true">
        <template v-for="(d, i) in linePaths" :key="i">
          <path :d="d" class="trace-line-base" />
          <path :d="d" class="trace-line-dot" />
        </template>
      </svg>
    </Teleport>

    <ImageViewer :visible="showImageViewer" :src="previewUrl" @close="showImageViewer = false" />
    <VideoPlayer :visible="showVideoPlayer" :src="activeVideoUrl" :asset-id="activeVideoId" @close="showVideoPlayer = false" />
  </div>
</template>

<style scoped>
.node-panel-page {
  position: relative;
  height: 100vh;
  overflow: hidden;
  background: transparent;
  animation: page-enter 0.45s ease both;
  display: flex;
  flex-direction: column;
}

.node-panel-page.dragging::after {
  content: '';
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  pointer-events: none;
  z-index: 200;
}

.node-orb {
  position: fixed;
  z-index: 0;
  border-radius: 50%;
  filter: blur(80px);
  pointer-events: none;
}

.node-orb-2 {
  right: 60px;
  bottom: -100px;
  width: 440px;
  height: 440px;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.07) 0%, transparent 70%);
}

/* ── 工具栏 ── */
.node-toolbar {
  position: relative;
  z-index: 2;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 16px;
}
.tb-doc {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.45);
  letter-spacing: 0.5px;
}
.tb-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
}
.tb-status {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.35);
}
.tb-status.dirty { color: #f0b429; }
.tb-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 9px;
  border: 1px solid var(--color-border);
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.75);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.tb-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  color: #fff;
}
.tb-btn.primary {
  background: rgba(255, 255, 255, 0.14);
  border-color: rgba(255, 255, 255, 0.28);
  color: #fff;
}
.tb-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.panel-workspace {
  position: relative;
  z-index: 1;
  display: flex;
  gap: 14px;
  flex: 1;
  min-height: 0;
  padding: 0 14px 14px;
}

.panel-shell {
  position: relative;
  flex: 0 0 74%;
  min-width: 0;
  min-height: 0;
}

.panel-stack {
  position: relative;
  height: 100%;
  width: 100%;
  min-height: 0;
}

.panel-column {
  height: 100%;
  width: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.preview-panel {
  width: 100%;
  position: relative;
  min-height: 150px;
  overflow: hidden;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: rgba(7, 9, 15, 0.24);
  backdrop-filter: var(--glass-blur);
  -webkit-backdrop-filter: var(--glass-blur);
  box-shadow: var(--shadow-soft);
  transition: border-color 0.2s, background 0.2s;
}

.preview-panel.is-gen-hidden,
.resize-handle.is-gen-hidden {
  visibility: hidden;
  pointer-events: none;
}

.preview-panel.drag-over {
  border-color: rgba(166, 231, 226, 0.5);
  background: rgba(166, 231, 226, 0.08);
}
.preview-panel.is-trace {
  border-color: rgba(166, 231, 226, 0.4);
}

.panel-tag {
  position: absolute;
  top: 10px;
  left: 12px;
  z-index: 5;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.35);
  letter-spacing: 1px;
  pointer-events: none;
}
.trace-tag {
  padding: 2px 8px;
  border-radius: 6px;
  background: rgba(166, 231, 226, 0.16);
  color: #a6e7e2;
  letter-spacing: 0;
}

.panel-gen-btns {
  position: absolute;
  top: 10px;
  right: 12px;
  z-index: 5;
  display: flex;
  gap: 8px;
}
.gen-btn {
  padding: 5px 12px;
  border-radius: 8px;
  border: 1px solid var(--color-border);
  background: rgba(0, 0, 0, 0.4);
  color: rgba(255, 255, 255, 0.75);
  font-size: 12px;
  cursor: pointer;
  backdrop-filter: blur(6px);
  transition: all 0.2s;
}
.gen-btn:hover {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.28);
  color: #fff;
}

.panel-empty {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.25);
  letter-spacing: 1px;
}

.resize-handle {
  position: relative;
  height: 10px;
  flex: 0 0 10px;
  border: 0;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(255, 255, 255, 0.02);
  cursor: row-resize;
}

.resize-handle::after {
  content: '';
  position: absolute;
  left: 50%;
  top: 50%;
  width: 44px;
  height: 2px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.22);
  transform: translate(-50%, -50%);
}

.resize-handle:hover,
.resize-handle:focus-visible {
  background: rgba(255, 255, 255, 0.1);
}

/* ── 生成参考模式高亮 ── */
.preview-panel.is-gen-ref {
  border-color: rgba(255, 255, 255, 0.28);
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.08);
}
.gen-ref-tag {
  padding: 2px 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.65);
  letter-spacing: 0;
}

/* 生成模式下不相关面板变暗 */
.preview-panel.is-gen-dim::after {
  content: '';
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.52);
  z-index: 6;
  pointer-events: none;
  border-radius: inherit;
  transition: background 0.3s;
}

/* ── 生成参数面板（覆盖第二、三面板） ── */
.gen-panel-dock {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  width: 100%;
  z-index: 10;
  border-radius: var(--radius-lg);
  overflow: hidden;
  transform: translateY(18px);
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
  transition:
    transform 0.38s cubic-bezier(0.22, 1, 0.36, 1),
    opacity 0.24s ease,
    visibility 0s linear 0.38s;
}

.gen-panel-dock.is-open {
  transform: translateY(0);
  opacity: 1;
  visibility: visible;
  pointer-events: auto;
  transition-delay: 0s;
}

.gen-panel-dock.is-drag-over {
  outline: 2px solid rgba(166, 231, 226, 0.72);
  outline-offset: -2px;
}

@media (prefers-reduced-motion: reduce) {
  .preview-panel,
  .gen-panel-dock {
    transition-duration: 0.01ms;
  }
}

/* ── 连线覆盖层 ── */
.line-overlay {
  position: fixed;
  inset: 0;
  width: 100vw;
  height: 100vh;
  z-index: 150;
  pointer-events: none;
}
/* 实线轨道 */
.trace-line-base {
  fill: none;
  stroke: rgba(255, 255, 255, 0.25);
  stroke-width: 1;
  stroke-linecap: round;
  filter: drop-shadow(0 0 2px rgba(255, 255, 255, 0.15));
}
/* 移动光点：dasharray 3/500，gap 够大确保线上只有一个点，period=503 */
.trace-line-dot {
  fill: none;
  stroke: #ffffff;
  stroke-width: 4;
  stroke-linecap: round;
  stroke-dasharray: 3 500;
  filter: drop-shadow(0 0 8px rgba(255, 255, 255, 1)) drop-shadow(0 0 16px rgba(255, 255, 255, 0.5));
  animation: trace-dot 2s linear infinite;
}
@keyframes trace-dot {
  to { stroke-dashoffset: -503; }
}
</style>
