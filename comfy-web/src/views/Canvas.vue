<script setup lang="ts">
import { normalizeAspectRatioParameters } from '@/constants/aspectRatios'
import { computed, markRaw, nextTick, onBeforeUnmount, onMounted, provide, reactive, ref, watch, Teleport, type Ref } from 'vue'
import { onBeforeRouteLeave, useRouter } from 'vue-router'
import { VueFlow, useVueFlow, SelectionMode, type Connection, type OnConnectStartParams, type ViewportTransform, type GraphEdge } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { MiniMap } from '@vue-flow/minimap'
import { ElButton, ElSelect, ElOption, ElMessage, ElDropdown, ElDropdownMenu, ElDropdownItem, ElInputNumber, ElTooltip } from 'element-plus'
import { Picture, VideoCamera, Document } from '@element-plus/icons-vue'
import { Focus, Folders, Hand, Info, LogOut, Magnet, Map, MousePointer2, MousePointerClick, Network, Plus as PlusIcon, Search, Workflow, RotateCcw, RotateCw } from '@lucide/vue'
import CanvasNodeComponent from '../components/CanvasNode.vue'
import AssetPicker from '../components/AssetPicker.vue'
import MediaViewer from '../components/MediaViewer.vue'
import AiChatPanel from '../components/AiChatPanel.vue'
import AiBlobWarpAvatar from '../components/AiBlobWarpAvatar.vue'
import { authFetch, createCanvas, deleteCanvas, getApiModels, getCanvas, listCanvases, renameCanvas, saveCanvas, uploadInputImage, type ApiModel, type CanvasSummary, type CanvasDocument } from '../api/apiService'
import { canvasActionsKey, canvasReferences, collectInputs, makeNode, nodeKinds, validConnection, type CanvasAsset, type CanvasNode, type CanvasEdge, type CanvasParameterValue, type PromptOptimizationTarget } from '../services/canvasGraph'
import { arrangeCanvas } from '../services/arrangeCanvas'
import { forgetCanvasTasks, refreshCanvasTasks, setActiveCanvas, subscribeCanvasTasks, trackCanvasTasks } from '../services/canvasTaskMonitor'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/minimap/dist/style.css'

const flow = useVueFlow({ id: 'creative-canvas' })
const router = useRouter()
const { removeEdges } = flow
const nodes = ref<CanvasNode[]>([])
const edges = ref<CanvasEdge[]>([])
const viewport = ref<ViewportTransform>({ x: 0, y: 0, zoom: 1 })
const boards = ref<CanvasSummary[]>([])
const loadingBoards = ref(true)
const activeId = ref<number>()
const name = ref('新画布')
const loading = ref(false)
const ready = ref(false)
const loadError = ref('')
const saveState = ref('')
const assets = ref<Record<number, CanvasAsset>>({})
const previewAsset = ref<CanvasAsset>()
const imageModels = ref<ApiModel[]>([])
const videoModels = ref<ApiModel[]>([])
const chatReferences = computed(() => canvasReferences(nodes.value, assets.value))
const pickerVisible = ref(false)
const pickerNode = ref<string>()
const fileInput = ref<HTMLInputElement>()
const uploadBusy = ref(false)
const creating = ref(false)
const chatPanelOpen = ref(false)
const chatPanel = ref<InstanceType<typeof AiChatPanel>>()
const chatBusy = ref(false)
const homeMode = ref(true)
const homeCanvasId = ref<number>()
let syncingGenerations = false
const menu = ref<{ x: number; y: number; position: { x: number; y: number } }>()
const connectionMenu = ref<{ x: number; y: number; position: { x: number; y: number }; nodeId: string; handleId: string; handleType: 'source' | 'target' }>()
const pendingConnection = ref<OnConnectStartParams>()
let ignorePaneClick = false
const showEdges = ref(true)
const snapEnabled = ref(false)
const showMap = ref(false)
const handMode = ref(false)
const submitting = reactive(new Set<string>())
let saveTimer: ReturnType<typeof setTimeout> | undefined
let saveQueue: Promise<void> = Promise.resolve()
const savedSnapshot = ref('')
let disposed = false
let arranging = false

// 简易撤销/重做历史（最多 50 步）
type HistorySnapshot = { nodes: string; edges: string }
const historyStack = ref<HistorySnapshot[]>([])
const historyIndex = ref(-1)
const MAX_HISTORY = 50

function takeSnapshot(): HistorySnapshot {
  return {
    nodes: JSON.stringify(nodes.value.map(n => ({ id: n.id, type: n.type, position: { x: n.position.x, y: n.position.y }, data: JSON.parse(JSON.stringify(n.data)) }))),
    edges: JSON.stringify(edges.value.map(e => ({ id: e.id, source: e.source, target: e.target, sourceHandle: e.sourceHandle, targetHandle: e.targetHandle, type: e.type }))),
  }
}

function pushHistory() {
  const snap = takeSnapshot()
  historyStack.value = historyStack.value.slice(0, historyIndex.value + 1)
  historyStack.value.push(snap)
  if (historyStack.value.length > MAX_HISTORY) historyStack.value.shift()
  historyIndex.value = historyStack.value.length - 1
}

function undo() {
  if (historyIndex.value <= 0) return
  historyIndex.value--
  applySnapshot(historyStack.value[historyIndex.value]!)
}

function redo() {
  if (historyIndex.value >= historyStack.value.length - 1) return
  historyIndex.value++
  applySnapshot(historyStack.value[historyIndex.value]!)
}

function applySnapshot(snap: HistorySnapshot) {
  nodes.value = JSON.parse(snap.nodes)
  edges.value = JSON.parse(snap.edges)
}

const canUndo = computed(() => historyIndex.value > 0)
const canRedo = computed(() => historyIndex.value < historyStack.value.length - 1)

// 连线点击断开
const edgeDisconnect = ref<{ id: string; x: number; y: number }>()

function showEdgeDisconnect(event: MouseEvent | TouchEvent, edgeId: string) {
  if (!(event instanceof MouseEvent)) return
  event.stopPropagation()
  edgeDisconnect.value = { id: edgeId, x: event.clientX, y: event.clientY }
}

const nodeTypes = Object.fromEntries(nodeKinds.map(kind => [kind.type, markRaw(CanvasNodeComponent)]))
// 节点被选中或拖动时，连接到它的连线高亮并显示流动动画。
const defaultEdgeOptions = markRaw({
  type: 'simplebezier',
  animated: false,
  class: (edge: GraphEdge) => {
    const { sourceNode, targetNode } = edge
    if (!sourceNode?.selected && !sourceNode?.dragging && !targetNode?.selected && !targetNode?.dragging) return ''
    return 'edge-node-active animated'
  },
  focusable: false,
  interactionWidth: 40,
})
// 与 Toonflow 相同，只持久化文档字段，排除 Vue Flow 的测量及交互状态。
const document = computed<CanvasDocument>(() => ({
  version: 1,
  nodes: nodes.value.map(node => ({ id: node.id, type: node.type, position: { x: node.position.x, y: node.position.y }, data: node.data })),
  edges: edges.value.map(edge => ({ id: edge.id, source: edge.source, target: edge.target, sourceHandle: edge.sourceHandle, targetHandle: edge.targetHandle, type: 'simplebezier' })),
  viewport: viewport.value,
}))
const snapshot = computed(() => JSON.stringify({ name: name.value, document: document.value }))
const dirty = computed(() => ready.value && snapshot.value !== savedSnapshot.value)
const selectedCount = computed(() => nodes.value.filter(node => node.selected).length)
const canEdit = computed(() => ready.value && !loading.value)

function modelForNode(node: CanvasNode) {
  return (node.type === 'remote-videoGenerationNode' ? videoModels.value : imageModels.value).find(model => String(model.id) === String(node.data.model))
}

function syncModelParameters(node: CanvasNode, model?: ApiModel) {
  const fields = model?.parameters?.fields ?? []
  const mediaType = node.type === 'remote-videoGenerationNode' ? 'video' : 'image'
  const current = normalizeAspectRatioParameters(mediaType, node.data.parameters ?? {})
  const next: Record<string, CanvasParameterValue> = {}
  for (const field of fields) {
    if (field.key === 'aspect_ratio' || field.key === 'ratio' || field.key === 'size') continue
    if (current[field.key] !== undefined) next[field.key] = current[field.key]
    else if (field.default !== undefined) next[field.key] = field.default
  }
  next.aspect_ratio = current.aspect_ratio
  node.data.parameters = next
}

function normalizeNode(node: CanvasNode) {
  node.data.parameters ??= {}
  if (!node.data.parameters.aspect_ratio && node.data.ratio) node.data.parameters.aspect_ratio = node.data.ratio
  if (!node.data.parameters.quality && node.data.quality) node.data.parameters.quality = node.data.quality
  if (!node.data.parameters.resolution && node.data.resolution) node.data.parameters.resolution = node.data.resolution
  if (!node.data.parameters.duration && node.data.duration) node.data.parameters.duration = node.data.duration
  syncModelParameters(node, modelForNode(node))
  delete node.data.ratio
}

function message(error: unknown) { return error instanceof Error ? error.message : '操作失败，请重试' }

function persist(): Promise<void> {
  clearTimeout(saveTimer)
  const operation = saveQueue.catch(() => {}).then(async () => {
    if (!activeId.value || !ready.value || snapshot.value === savedSnapshot.value) return
    const id = activeId.value
    const current = snapshot.value
    saveState.value = '保存中…'
    try {
      const payload = JSON.parse(current)
      const base = savedSnapshot.value ? JSON.parse(savedSnapshot.value).document.nodes : []
      const result = await saveCanvas(id, { ...payload, base_node_ids: base.map((node: CanvasNode) => node.id) })
      if (activeId.value !== id || disposed) return
      mergeGenerationNodes(result.document.nodes as unknown as CanvasNode[], result.document.edges as unknown as CanvasEdge[])
      savedSnapshot.value = JSON.stringify({ name: payload.name, document: result.document })
      saveState.value = '已保存'
      const board = boards.value.find(item => item.id === id)
      if (board) board.name = name.value
    } catch (error) {
      saveState.value = '保存失败，请重试'
      throw error
    }
  })
  saveQueue = operation
  return operation
}

watch(snapshot, () => {
  if (!ready.value || loading.value) return
  if (activeId.value) trackCanvasTasks(activeId.value, name.value, nodes.value)
  if (!dirty.value) { saveState.value = '已保存'; return }
  saveState.value = '未保存'
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => { void persist().catch(() => {}) }, 700)
})

async function hydrateAssets() {
  const ids = [...new Set(nodes.value.flatMap(node => Object.values(node.data!.outputs).flatMap(output => typeof output.value === 'string' ? [] : output.value.assetIds)))]
  if (!ids.length) return
  const response = await authFetch('/api/api-proxy/assets/by-ids', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids }) })
  if (!response.ok) throw new Error('素材预览加载失败，可重新打开画布重试')
  const data = await response.json()
  for (const asset of data.assets ?? []) {
    const filename = String(asset.location).split(/[/\\]/).pop()!
    assets.value[asset.id] = { id: asset.id, type: asset.asset_type === 'video' ? 'video' : 'image', url: `/api/api-proxy/output/${encodeURIComponent(filename)}` }
  }
}

async function openBoard(id: number, preparing = false) {
  if (loading.value || submitting.size || uploadBusy.value || (chatBusy.value && !preparing)) return false
  loading.value = true
  try {
    await persist()
    const board = await getCanvas(id)
    ready.value = false
    nodes.value = board.document.nodes as unknown as CanvasNode[]
    nodes.value.forEach(normalizeNode)
    edges.value = board.document.edges as unknown as CanvasEdge[]
    viewport.value = board.document.viewport
    name.value = board.name
    activeId.value = id
    savedSnapshot.value = snapshot.value
    ready.value = true
    setActiveCanvas(id)
    trackCanvasTasks(id, board.name, nodes.value)
    saveState.value = '已保存'
    loadError.value = ''
    await nextTick()
    await flow.setViewport(viewport.value)
    historyStack.value = []
    historyIndex.value = -1
    pushHistory()
    await hydrateAssets().catch(error => ElMessage.warning(message(error)))
    void syncGenerationNodes(id)
    return true
  } catch (error) {
    loadError.value = message(error)
    ElMessage.error(message(error))
    return false
  } finally { loading.value = false }
}

async function enterBoard(id: number) {
  if (await openBoard(id)) homeMode.value = false
}

async function prepareChatCanvas(requestedName?: string): Promise<number> {
  if (homeMode.value) {
    let id = homeCanvasId.value
    if (!id) {
      const board = await createCanvas(requestedName?.trim() || '新画布')
      boards.value.unshift(board)
      homeCanvasId.value = board.id
      id = board.id
    }
    if (!await openBoard(id, true)) throw new Error('画布加载失败，请重试')
  }
  await persist()
  homeMode.value = false
  chatPanelOpen.value = true
  return activeId.value!
}

async function renameBoard(id: number, boardName: string) {
  const nextName = boardName.trim()
  if (!nextName) return
  await renameCanvas(id, nextName)
  const board = boards.value.find(item => item.id === id)
  if (board) board.name = nextName
  if (activeId.value === id) {
    const saved = JSON.parse(savedSnapshot.value)
    saved.name = nextName
    savedSnapshot.value = JSON.stringify(saved)
    name.value = nextName
  }
}

async function removeBoard(id: number) {
  await deleteCanvas(id)
  forgetCanvasTasks(id)
  boards.value = boards.value.filter(item => item.id !== id)
  if (homeCanvasId.value === id) homeCanvasId.value = undefined
  if (activeId.value === id) {
    activeId.value = undefined
    ready.value = false
    nodes.value = []
    edges.value = []
    homeMode.value = true
    chatPanelOpen.value = false
  }
}

async function returnToCanvases() {
  if (loading.value || submitting.size || uploadBusy.value || chatBusy.value) return
  try {
    await persist()
    boards.value = await listCanvases()
    homeCanvasId.value = undefined
    homeMode.value = true
    chatPanelOpen.value = false
  } catch (error) { ElMessage.error(message(error)) }
}

async function newBoard() {
  if (loading.value || creating.value || submitting.size || uploadBusy.value || chatBusy.value) return
  if (typeof chatPanel !== 'undefined' && chatPanel.value) {
    chatPanel.value.openCreateCanvasDialog()
    return
  }
  creating.value = true
  try {
    await persist()
    const board = await createCanvas()
    boards.value.unshift(board)
    await enterBoard(board.id)
  } catch (error) { ElMessage.error(message(error)) }
  finally { creating.value = false }
}

async function createNamedBoard(boardName: string) {
  if (loading.value || creating.value || submitting.size || uploadBusy.value || chatBusy.value) return
  creating.value = true
  try {
    await persist()
    const board = await createCanvas(boardName.trim() || '新画布')
    boards.value.unshift(board)
    await enterBoard(board.id)
  } finally { creating.value = false }
}

function addNode(type: string, position?: { x: number; y: number }) {
  if (!canEdit.value) return
  const element = window.document.querySelector('.canvas-workspace')!.getBoundingClientRect()
  const point = position ?? flow.screenToFlowCoordinate({ x: element.left + element.width / 2 - 150, y: element.top + element.height / 2 - 120 })
  if (!position) {
    while (nodes.value.some(node => Math.abs(node.position.x - point.x) < 340 && Math.abs(node.position.y - point.y) < 300)) point.x += 360
  }
  const node = makeNode(type, point)
  if (type.includes('Generation')) {
    node.data!.model = String((type.includes('video') ? videoModels : imageModels).value[0]?.id ?? '')
    syncModelParameters(node, modelForNode(node))
  }
  nodes.value.forEach(item => { item.selected = false })
  node.selected = true
  nodes.value.push(node)
  menu.value = undefined
  pushHistory()
  return node
}

function connect(connection: Connection) {
  if (!canEdit.value || !validConnection(connection, nodes.value, edges.value)) return
  edges.value.push({ ...connection, id: crypto.randomUUID(), type: 'simplebezier' })
  pendingConnection.value = undefined
  connectionMenu.value = undefined
  pushHistory()
}

function connectStart(start: OnConnectStartParams) {
  if (!canEdit.value || !start.nodeId || !start.handleId || !start.handleType) return
  pendingConnection.value = start
  connectionMenu.value = undefined
}

function isCompatible(left: CanvasNode['data']['handles'][number]['dataType'], right: CanvasNode['data']['handles'][number]['dataType']) {
  const leftTypes = Array.isArray(left) ? left : [left]
  const rightTypes = Array.isArray(right) ? right : [right]
  return leftTypes.some(type => rightTypes.includes(type))
}

function connectionCandidates() {
  const pending = connectionMenu.value
  const start = pending ? { nodeId: pending.nodeId, handleId: pending.handleId, handleType: pending.handleType } : pendingConnection.value
  if (!start?.nodeId || !start.handleId || !start.handleType) return []
  const source = nodes.value.find(node => node.id === start.nodeId)?.data.handles.find(handle => handle.id === start.handleId && handle.type === start.handleType)
  if (!source) return []
  return nodeKinds.filter(kind => {
    const handles = makeNode(kind.type, { x: 0, y: 0 }).data.handles
    return handles.some(handle => handle.type !== source.type && isCompatible(source.dataType, handle.dataType))
  })
}

function connectEnd(event?: MouseEvent | TouchEvent) {
  const start = pendingConnection.value
  pendingConnection.value = undefined
  if (!start?.nodeId || !start.handleId || !start.handleType || !event) return
  if (event.type === 'touchcancel' || flow.connectionStatus.value === 'valid') return
  const point = 'changedTouches' in event ? event.changedTouches[0] : event
  if (!point) return
  const element = window.document.elementFromPoint(point.clientX, point.clientY)
  if (!element?.closest('.vue-flow__pane')) return
  const position = flow.screenToFlowCoordinate({ x: point.clientX, y: point.clientY })
  connectionMenu.value = { x: point.clientX, y: point.clientY, position, nodeId: start.nodeId, handleId: start.handleId, handleType: start.handleType }
  if (!connectionCandidates().length) connectionMenu.value = undefined
  ignorePaneClick = !!connectionMenu.value
}

function paneClick() {
  if (ignorePaneClick) { ignorePaneClick = false; return }
  menu.value = undefined
  connectionMenu.value = undefined
  edgeDisconnect.value = undefined
}

function addConnectedNode(type: string) {
  const pending = connectionMenu.value
  if (!pending) return
  const node = addNode(type, pending.position)
  if (!node) return
  const startNode = nodes.value.find(item => item.id === pending.nodeId)
  const startHandle = startNode?.data.handles.find(handle => handle.id === pending.handleId && handle.type === pending.handleType)
  const targetHandle = node.data.handles.find(handle => handle.type !== pending.handleType && startHandle && isCompatible(startHandle.dataType, handle.dataType))
  if (startNode && startHandle && targetHandle) {
    const connection: Connection = pending.handleType === 'source'
      ? { source: startNode.id, target: node.id, sourceHandle: startHandle.id, targetHandle: targetHandle.id }
      : { source: node.id, target: startNode.id, sourceHandle: targetHandle.id, targetHandle: startHandle.id }
    if (validConnection(connection, nodes.value, edges.value)) edges.value.push({ ...connection, id: crypto.randomUUID(), type: 'simplebezier' })
  }
  connectionMenu.value = undefined
}

function openCenterNodeMenu() {
  const workspace = window.document.querySelector('.canvas-workspace')!.getBoundingClientRect()
  contextMenu({ clientX: workspace.left + workspace.width / 2, clientY: workspace.top + workspace.height / 2 } as MouseEvent)
}

function duplicate(id: string) {
  const source = nodes.value.find(node => node.id === id)
  if (!source || !canEdit.value) return
  const copy = JSON.parse(JSON.stringify({ id: source.id, type: source.type, position: source.position, data: source.data })) as CanvasNode
  copy.id = crypto.randomUUID()
  copy.position = { x: source.position.x + 40, y: source.position.y + 60 }
  delete copy.data!.task
  nodes.value.forEach(node => { node.selected = false })
  copy.selected = true
  nodes.value.push(copy)
  pushHistory()
}

function remove(id: string) {
  if (!canEdit.value) return
  if (nodes.value.find(node => node.id === id)?.data?.task?.state === 'pending' || submitting.has(id)) {
    ElMessage.warning('请等待节点生成完成后再移除')
    return
  }
  nodes.value = nodes.value.filter(node => node.id !== id)
  edges.value = edges.value.filter(edge => edge.source !== id && edge.target !== id)
  pushHistory()
}

function deleteSelection() {
  nodes.value.filter(node => node.selected).forEach(node => remove(node.id))
  edges.value = edges.value.filter(edge => !edge.selected)
}

// 整理画布前的位置快照，用于撤销。
const arrangeSnapshot = ref<Array<{ id: string; position: { x: number; y: number } }>>()
let arrangeController: AbortController | undefined

async function arrangeNodes() {
  if (!canEdit.value || !nodes.value.length || arranging) return
  arranging = true
  arrangeController = new AbortController()
  try {
    await arrangeCanvas(flow, arrangeController.signal)
    arrangeSnapshot.value = nodes.value.map(node => ({ id: node.id, position: { x: node.position.x, y: node.position.y } }))
    saveState.value = '未保存'
  } catch (error) {
    if (!arrangeController.signal.aborted) ElMessage.error(message(error))
  } finally {
    arrangeController = undefined
    arranging = false
  }
}

function undoArrange() {
  const snapshot = arrangeSnapshot.value
  if (!snapshot) return
  const ids = new Set(nodes.value.map(node => node.id))
  for (const item of snapshot) {
    if (ids.has(item.id)) {
      const node = nodes.value.find(n => n.id === item.id)
      if (node) node.position = { ...item.position }
    }
  }
  arrangeSnapshot.value = undefined
  saveState.value = '未保存'
}

function pick(id?: string) { pickerNode.value = id; pickerVisible.value = true }

function applyAssets(selected: Array<{ id: number; location: string; asset_type?: string }>) {
  const target = nodes.value.find(node => node.id === pickerNode.value)
  for (const asset of selected) {
    const video = asset.asset_type === 'video'
    if (target && (target.type === 'remote-videoNode') !== video) { ElMessage.warning('素材类型与节点不匹配'); continue }
    const node = target ?? addNode(video ? 'remote-videoNode' : 'remote-imageNode', { x: 100 + nodes.value.length * 36, y: 120 + nodes.value.length * 32 })
    if (!node) continue
    const port = video ? 'video' : 'image'
    node.data!.outputs[port] = { dataType: video ? 'VIDEO' : 'IMAGE', value: { assetIds: [asset.id] } }
  }
  void hydrateAssets().catch(error => ElMessage.warning(message(error)))
}

async function upload(event: Event) {
  const input = event.target as HTMLInputElement
  uploadBusy.value = true
  try {
    for (const file of Array.from(input.files ?? [])) {
      const asset = await uploadInputImage(file)
      applyAssets([{ ...asset, asset_type: file.type.startsWith('video/') ? 'video' : 'picture' }])
    }
  } catch (error) { ElMessage.error(message(error)) }
  finally { input.value = ''; uploadBusy.value = false }
}

function dragover(event: DragEvent) {
  if (!canEdit.value) return
  const files = Array.from(event.dataTransfer?.items ?? [])
  if (files.some(item => item.kind === 'file' && (item.type.startsWith('image/') || item.type.startsWith('video/')))) {
    event.dataTransfer!.dropEffect = 'copy'
  }
}

async function drop(event: DragEvent) {
  if (!canEdit.value) return
  const files = Array.from(event.dataTransfer?.files ?? []).filter(f => f.type.startsWith('image/') || f.type.startsWith('video/'))
  if (!files.length) return
  uploadBusy.value = true
  try {
    for (const file of files) {
      const asset = await uploadInputImage(file)
      applyAssets([{ ...asset, asset_type: file.type.startsWith('video/') ? 'video' : 'picture' }])
    }
  } catch (error) { ElMessage.error(message(error)) }
  finally { uploadBusy.value = false }
}

async function run(id: string) {
  const node = nodes.value.find(item => item.id === id)
  if (!node || !canEdit.value || submitting.has(id) || node.data?.task?.state === 'pending') return
  submitting.add(id)
  try {
    const data = node.data!
    const input = collectInputs(id, nodes.value, edges.value)
    const prompt = [...input.texts, data.prompt].filter(Boolean).join('\n').trim()
    if (!prompt) throw new Error('请填写提示词或连接文本节点')
    if (!data.model) throw new Error('请选择模型')
    await persist()
    const response = await authFetch(`/api/api-proxy/canvases/${activeId.value}/nodes/${id}/generate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: Number(data.model), prompt, parameters: data.parameters, input_asset_ids: [...new Set([...input.assetIds, ...(data.inputAssetIds ?? [])])] }),
    })
    const result = await response.json()
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : '任务提交失败')
    data.executionId = result.execution_id
    data.task = { taskId: result.task_id, historyId: result.history_id, state: 'pending' }
    trackCanvasTasks(activeId.value!, name.value, nodes.value)
    // 先保存任务归属，离开页面后也能通过历史记录恢复结果。
    await persist()
    void syncGenerationNodes(activeId.value)
  } catch (error) { ElMessage.error(message(error)); void syncGenerationNodes(activeId.value) }
  finally { submitting.delete(id) }
}

function mergeGenerationNodes(incoming: CanvasNode[], incomingEdges: CanvasEdge[] = []) {
  const added: string[] = []
  const known = new Set<string>(savedSnapshot.value ? JSON.parse(savedSnapshot.value).document.nodes.map((node: CanvasNode) => node.id) : [])
  for (const serverNode of incoming) {
    const local = nodes.value.find(node => node.id === serverNode.id)
    if (!local) {
      // 已加载后被用户删除的节点不再补回；只补入助手新建的节点。
      if (!known.has(serverNode.id)) { nodes.value.push(serverNode); added.push(serverNode.id) }
    } else if (serverNode.data.executionId) {
      local.data.executionId = serverNode.data.executionId
      if (serverNode.data.task) local.data.task = serverNode.data.task
      if (serverNode.data.task?.state === 'completed') local.data.outputs = serverNode.data.outputs
    }
  }
  const nodeIds = new Set(nodes.value.map(node => node.id))
  for (const edge of incomingEdges) {
    if (added.includes(edge.target) && nodeIds.has(edge.source) && !edges.value.some(local => local.id === edge.id)) edges.value.push(edge)
  }
  return added
}

async function syncGenerationNodes(canvasId?: number, incoming?: Awaited<ReturnType<typeof getCanvas>>) {
  if (!canvasId || canvasId !== activeId.value || !ready.value || loading.value || syncingGenerations || disposed) return
  syncingGenerations = true
  try {
    const board = incoming ?? await refreshCanvasTasks(canvasId)
    if (canvasId !== activeId.value || disposed || loading.value) return
    const added = mergeGenerationNodes(board.document.nodes as unknown as CanvasNode[], board.document.edges as unknown as CanvasEdge[])
    if (added.length) {
      await nextTick()
      await flow.fitView({ nodes: added, maxZoom: 1, padding: .3, duration: 250 })
    }
    const missingAssets = nodes.value.some(node => Object.values(node.data.outputs).some(output =>
      typeof output.value !== 'string' && output.value.assetIds.some(id => !assets.value[id])))
    if (missingAssets) await hydrateAssets()
  } catch (error) {
    if (canvasId === activeId.value && chatBusy.value) saveState.value = message(error)
  } finally { syncingGenerations = false }
}

function contextMenu(event: MouseEvent) {
  if (!canEdit.value) return
  menu.value = { x: Math.min(event.clientX, window.innerWidth - 180), y: Math.min(event.clientY, window.innerHeight - 220), position: flow.screenToFlowCoordinate({ x: event.clientX, y: event.clientY }) }
}

function keydown(event: KeyboardEvent) {
  if (previewAsset.value) return
  if ((event.target as HTMLElement).closest('input,textarea,select,[contenteditable="true"],.el-dialog')) return
  if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); deleteSelection() }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'd') { event.preventDefault(); nodes.value.filter(node => node.selected).forEach(node => duplicate(node.id)) }
  if ((event.ctrlKey || event.metaKey) && !event.shiftKey && event.key.toLowerCase() === 'z') { event.preventDefault(); undo() }
  if ((event.ctrlKey || event.metaKey) && (event.shiftKey && event.key.toLowerCase() === 'z' || event.key.toLowerCase() === 'y')) { event.preventDefault(); redo() }
}

function beforeUnload(event: BeforeUnloadEvent) { if (dirty.value || submitting.size || uploadBusy.value || chatBusy.value) { event.preventDefault(); event.returnValue = '' } }
onBeforeRouteLeave(async () => {
  if (submitting.size || uploadBusy.value || chatBusy.value) { ElMessage.warning('请等待任务提交或素材上传完成后再离开'); return false }
  try { await persist(); return true } catch (error) { ElMessage.error(message(error)); return false }
})
async function optimizePrompt(id: string, skillId?: string) {
  const node = nodes.value.find(item => item.id === id)
  if (!node || !activeId.value || !node.data.prompt.trim()) return false
  return !!await chatPanel.value?.startPromptOptimization({
    canvasId: activeId.value, nodeId: id, label: node.data.label, prompt: node.data.prompt,
    mediaType: node.type.includes('video') ? 'video' : 'image', parameters: { ...node.data.parameters },
    references: canvasReferences(nodes.value, assets.value, edges.value, id),
  }, skillId)
}

function applyOptimizedPrompt(target: PromptOptimizationTarget, prompt: string) {
  const node = nodes.value.find(item => item.id === target.nodeId)
  if (target.canvasId !== activeId.value || !node) { ElMessage.warning('原节点已移除或画布已切换，无法回填'); return }
  if (submitting.has(node.id) || node.data.task?.state === 'pending') { ElMessage.warning('节点正在生成，请完成后再应用'); return }
  if (node.data.prompt !== target.prompt) { ElMessage.warning('原提示词已修改，请重新发起优化，避免覆盖你的编辑'); return }
  node.data.prompt = prompt
  target.prompt = prompt
  ElMessage.success('已应用到原节点提示词')
}

provide(canvasActionsKey, {
  assets,
  imageModels,
  videoModels,
  setModel: (id, model) => {
    const node = nodes.value.find(item => item.id === id)
    if (!node) return
    node.data.model = model
    syncModelParameters(node, modelForNode(node))
  },
  isSubmitting: id => submitting.has(id),
  optimizePrompt,
  run: id => { void run(id) },
  pick,
  preview: asset => { previewAsset.value = asset },
  duplicate,
  remove,
})
const unsubscribeTasks = subscribeCanvasTasks(board => { void syncGenerationNodes(board.id, board) })
onMounted(async () => {
  window.addEventListener('keydown', keydown)
  window.addEventListener('beforeunload', beforeUnload)
  try {
    boards.value = await listCanvases()
  } catch (error) { loadError.value = `${message(error)}。请确认已执行画布建表 SQL 并更新后端。` }
  finally { loadingBoards.value = false }
  const results = await Promise.allSettled([getApiModels('image'), getApiModels('video')])
  if (results[0].status === 'fulfilled') imageModels.value = results[0].value
  if (results[1].status === 'fulfilled') videoModels.value = results[1].value
  if (results.some(result => result.status === 'rejected')) ElMessage.warning('部分模型加载失败，请刷新页面重试')
  nodes.value.forEach(normalizeNode)
})
onBeforeUnmount(() => { disposed = true; clearTimeout(saveTimer); unsubscribeTasks(); setActiveCanvas(); window.removeEventListener('keydown', keydown); window.removeEventListener('beforeunload', beforeUnload) })
</script>

<template>
  <main class="canvas-page" :class="{ 'canvas-home': homeMode }">
    <button v-if="homeMode" type="button" class="canvas-home-back" @click="router.push('/')"><LogOut :size="16" />返回首页</button>
    <header v-if="!homeMode" class="canvas-topbar">
      <button type="button" class="canvas-exit" aria-label="返回画布列表" title="返回画布列表" @click="returnToCanvases">
        <LogOut :size="16" />
      </button>
      <ElSelect :model-value="activeId" :disabled="loading || submitting.size > 0 || uploadBusy || chatBusy" placeholder="选择画布" class="board-select" @change="openBoard">
        <ElOption v-for="board in boards" :key="board.id" :value="board.id" :label="board.name" />
      </ElSelect>
    </header>
    <div v-show="!homeMode" class="canvas-workspace" :class="{ 'hand-mode': handMode }" @contextmenu.prevent="contextMenu" @pointerdown.capture="ignorePaneClick = false" @dragover.prevent="dragover" @drop.prevent="drop">
      <VueFlow v-model:nodes="nodes" v-model:edges="edges" id="creative-canvas" :node-types="nodeTypes" :default-edge-options="defaultEdgeOptions" :min-zoom="0.2" :max-zoom="8" :pan-on-drag="handMode ? true : [1, 2]" :selection-mode="SelectionMode.Partial" selection-on-drag :snap-to-grid="snapEnabled" :snap-grid="[16, 16]" :delete-key-code="null" :zoom-on-double-click="false" :zoom-on-scroll="false" pan-on-scroll zoom-activation-key-code="Control" :nodes-draggable="canEdit" :nodes-connectable="canEdit" :connect-on-click="false" :is-valid-connection="(connection) => validConnection(connection, nodes, edges)" :class="{ 'edges-hidden': !showEdges }" @connect="connect" @connect-start="connectStart" @connect-end="connectEnd" @edge-click="({ event, edge }) => showEdgeDisconnect(event, edge.id)" @move-end="({ flowTransform }) => viewport = flowTransform" @pane-click="paneClick">
        <Background :gap="16" pattern-color="var(--color-border)" />
        <MiniMap v-if="showMap && nodes.length" class="canvas-map" pannable zoomable :width="180" :height="120" />
      </VueFlow>
      <input ref="fileInput" hidden type="file" accept="image/*,video/*" multiple @change="upload" />
      <div v-if="!ready || !nodes.length" class="canvas-empty">
        <template v-if="ready">
          <div class="empty-hint"><MousePointerClick :size="24" aria-hidden="true" /><span>双击画布 自由生成节点</span></div>
          <div class="empty-actions">
            <button type="button" @click="addNode('remote-imageGenerationNode')"><span class="action-icon"><Picture /></span><span>图片生成</span></button>
            <button type="button" @click="addNode('remote-videoGenerationNode')"><span class="action-icon"><VideoCamera /></span><span>视频生成</span></button>
            <button type="button" @click="addNode('remote-textNode')"><span class="action-icon"><Document /></span><span>文本</span></button>
          </div>
        </template>
        <template v-else>
          <span class="empty-symbol">✦</span><h2>你的创作工作台</h2>
          <p v-if="loadError" role="alert">{{ loadError }}</p>
          <p v-else>把文本、图片和视频节点组合成自己的工作流。</p>
        </template>
        <ElButton v-if="!ready" type="primary" :disabled="loading" @click="newBoard">新建画布</ElButton>
      </div>
      <footer class="canvas-status"><span>{{ nodes.length }} 个节点 · {{ edges.length }} 条连线</span><span v-if="selectedCount">已选 {{ selectedCount }} 个节点</span></footer>
      <div class="canvas-controls canvas-controls-left" aria-label="画布控制">
        <el-tooltip content="素材库" placement="top" :show-after="400" :hide-after="0" :enterable="false">
          <ElButton text aria-label="素材库" @click="pick()"><Folders :size="18" /></ElButton>
        </el-tooltip>
        <el-tooltip content="整理画布" placement="top" :show-after="400" :hide-after="0" :enterable="false">
          <ElButton text aria-label="整理画布" @click="arrangeNodes"><Network :size="18" /></ElButton>
        </el-tooltip>
        <el-tooltip v-if="arrangeSnapshot" content="撤销整理" placement="top" :show-after="400" :hide-after="0" :enterable="false">
          <ElButton text aria-label="撤销整理" @click="undoArrange"><Network :size="18" style="opacity:.45" /></ElButton>
        </el-tooltip>
        <el-tooltip :content="showMap ? '隐藏地图' : '显示地图'" placement="top" :show-after="400" :hide-after="0" :enterable="false">
          <ElButton text :type="showMap ? 'primary' : undefined" aria-label="显示地图" @click="showMap = !showMap"><Map :size="18" /></ElButton>
        </el-tooltip>
        <el-tooltip :content="snapEnabled ? '关闭网格吸附（节点拖动时自动对齐）' : '开启网格吸附（节点拖动时自动对齐）'" placement="top" :show-after="400" :hide-after="0" :enterable="false">
          <ElButton text :type="snapEnabled ? 'primary' : undefined" aria-label="网格吸附" @click="snapEnabled = !snapEnabled"><Magnet :size="18" /></ElButton>
        </el-tooltip>
        <el-tooltip :content="showEdges ? '隐藏连线' : '显示连线'" placement="top" :show-after="400" :hide-after="0" :enterable="false">
          <ElButton text :type="showEdges ? 'primary' : undefined" aria-label="显示连线" @click="showEdges = !showEdges"><Workflow :size="18" /></ElButton>
        </el-tooltip>
        <el-tooltip content="适应视图" placement="top" :show-after="400" :hide-after="0" :enterable="false">
          <ElButton text aria-label="适应视图" @click="flow.fitView({ padding: .3 })"><Focus :size="18" /></ElButton>
        </el-tooltip>
        <ElDropdown trigger="click" placement="top-start" :show-timeout="0" :hide-timeout="0">
          <el-tooltip content="缩放菜单（点击调整缩放比例）" placement="top" :show-after="400" :hide-after="0" :enterable="false">
            <ElButton text aria-label="缩放菜单" class="zoom-pct-btn">{{ Math.round(viewport.zoom * 100) }}%</ElButton>
          </el-tooltip>
          <template #dropdown>
            <ElDropdownMenu>
              <div class="zoom-menu">
                <ElInputNumber :model-value="Math.round(viewport.zoom * 100)" :min="20" :max="800" :controls="false" aria-label="缩放百分比" @change="(v: number | null) => v !== null && flow.zoomTo(v / 100)" /><span class="zoom-suffix">%</span>
              </div>
              <ElDropdownItem @click="flow.zoomIn()">放大</ElDropdownItem>
              <ElDropdownItem @click="flow.zoomOut()">缩小</ElDropdownItem>
              <ElDropdownItem @click="flow.fitView({ padding: .3, duration: 250 })">适合屏幕</ElDropdownItem>
            </ElDropdownMenu>
          </template>
        </ElDropdown>
      </div>
      <div class="canvas-controls canvas-controls-center" aria-label="画布工具">
        <el-tooltip content="撤销 (Ctrl+Z)" placement="top" :show-after="400" :hide-after="0" :enterable="false">
          <ElButton text :disabled="!canUndo" aria-label="撤销" @click="undo"><RotateCcw :size="18" /></ElButton>
        </el-tooltip>
        <el-tooltip content="重做 (Ctrl+Y)" placement="top" :show-after="400" :hide-after="0" :enterable="false">
          <ElButton text :disabled="!canRedo" aria-label="重做" @click="redo"><RotateCw :size="18" /></ElButton>
        </el-tooltip>
        <el-tooltip content="添加节点" placement="top" :show-after="400" :hide-after="0" :enterable="false">
          <ElButton text aria-label="添加节点" @click="openCenterNodeMenu"><PlusIcon :size="18" /></ElButton>
        </el-tooltip>
        <el-tooltip :content="handMode ? '切换到移动工具' : '切换到抓手工具'" placement="top" :show-after="400" :hide-after="0" :enterable="false">
          <ElButton text :type="handMode ? 'primary' : undefined" aria-label="移动工具" @click="handMode = !handMode"><component :is="handMode ? Hand : MousePointer2" :size="18" /></ElButton>
        </el-tooltip>
        <el-tooltip content="适应视图" placement="top" :show-after="400" :hide-after="0" :enterable="false">
          <ElButton text aria-label="定位节点" @click="flow.fitView({ padding: .3 })"><Search :size="18" /></ElButton>
        </el-tooltip>
        <el-tooltip content="双击画布添加节点；从端口拖出可自动创建兼容节点" placement="top" :show-after="400" :hide-after="0" :enterable="false">
          <ElButton text aria-label="画布提示"><Info :size="18" /></ElButton>
        </el-tooltip>
      </div>
      <button type="button" class="ai-orb" :class="{ active: chatPanelOpen }" aria-label="打开若晴AI" :aria-expanded="chatPanelOpen" title="打开若晴AI" @click="chatPanelOpen = !chatPanelOpen">
        <AiBlobWarpAvatar class="ai-orb-avatar" />
      </button>
    </div>
    <div v-if="menu" class="canvas-menu" :style="{ left: `${menu.x}px`, top: `${menu.y}px` }" @mouseleave="menu = undefined">
      <button @click="pick(); menu = undefined">打开资产库</button>
      <button @click="fileInput?.click(); menu = undefined">上传素材</button>
      <span class="canvas-menu-divider" />
      <button v-for="kind in nodeKinds" :key="kind.type" @click="addNode(kind.type, menu?.position)">{{ kind.label }}</button>
    </div>
    <div v-if="connectionMenu" class="canvas-menu connection-menu" :style="{ left: `${connectionMenu.x}px`, top: `${connectionMenu.y}px` }" @click.stop>
      <p class="connection-menu-title">连接到节点</p>
      <button v-for="kind in connectionCandidates()" :key="kind.type" @click="addConnectedNode(kind.type)">{{ kind.label }}</button>
    </div>
    <AssetPicker v-model:visible="pickerVisible" :max-select="pickerNode ? 1 : 20" allow-video @select="applyAssets" />
    <MediaViewer :visible="!!previewAsset" :src="previewAsset?.url ?? ''" :type="previewAsset?.type" :asset-id="previewAsset?.id" @close="previewAsset = undefined" />
    <AiChatPanel v-if="homeMode || ready" ref="chatPanel" v-model="chatPanelOpen" :canvas-id="homeMode ? homeCanvasId : activeId" :prepare-canvas="prepareChatCanvas" :references="homeMode ? [] : chatReferences" :boards="boards" :home-mode="homeMode" :home-loading="loadingBoards || loading || creating" :home-error="loadError" :rename-canvas="renameBoard" :delete-canvas="removeBoard" :create-canvas="createNamedBoard"
      @apply-prompt="applyOptimizedPrompt"
      @create-canvas="newBoard" @select-canvas="homeCanvasId = $event" @open-canvas="enterBoard" @canvas-changed="syncGenerationNodes" @busy-change="chatBusy = $event" />
    <Teleport to="body">
      <ElButton
        v-if="edgeDisconnect && flow.findEdge(edgeDisconnect.id)"
        class="edge-disconnect-btn"
        type="danger"
        circle
        aria-label="断开连接"
        title="断开连接"
        :style="{ left: `${edgeDisconnect.x}px`, top: `${edgeDisconnect.y}px` }"
        @click.stop="removeEdges(edgeDisconnect.id); edgeDisconnect = undefined"
        @mouseleave="edgeDisconnect = undefined"
      >×</ElButton>
    </Teleport>
  </main>
</template>

<style scoped>
.canvas-page { position: relative; height: 100vh; background: transparent; color: var(--color-text); }
.canvas-page.canvas-home { min-height: 100vh; height: auto; padding: clamp(100px, 15vh, 160px) clamp(24px, 7vw, 80px) 60px; }
.canvas-home-back { position: fixed; top: 20px; left: 24px; z-index: 10; display: inline-flex; align-items: center; gap: 7px; border: 0; background: transparent; color: var(--color-muted); font-size: 12px; cursor: pointer; }
.canvas-home-back:hover { color: var(--color-text); }
.canvas-topbar { position: absolute; top: 16px; left: 16px; z-index: 20; display: flex; align-items: center; gap: 8px; }
.canvas-exit { display: grid; width: 36px; height: 36px; place-items: center; border: 1px solid var(--color-border); border-radius: 12px; background: color-mix(in srgb, var(--color-surface-base) 84%, transparent); color: var(--color-muted); backdrop-filter: blur(18px); cursor: pointer; transition: color .2s, border-color .2s, background .2s; }
.canvas-exit:hover { border-color: var(--color-border-strong); background: var(--color-surface); color: var(--color-text); }
.board-select { width: 168px; flex-shrink: 0; }
.board-select :deep(.el-select__wrapper) { min-height: 36px; padding: 0 12px; border-radius: 999px !important; background: color-mix(in srgb, var(--color-surface-base) 84%, transparent) !important; border-color: var(--color-border) !important; backdrop-filter: blur(18px); box-shadow: none !important; }
.board-select :deep(.el-select__selected-item) { color: var(--color-text); font-size: 13px; font-weight: 600; }
.canvas-workspace { position: relative; width: 100%; height: 100%; min-height: 0; container-type: inline-size; }
.canvas-workspace.hand-mode :deep(.vue-flow__pane) { cursor: grab; }
.canvas-workspace.hand-mode :deep(.vue-flow__pane:active) { cursor: grabbing; }
.canvas-workspace.hand-mode :deep(.vue-flow__node) { pointer-events: none; }
.canvas-controls :deep(.el-button) { width: 28px; height: 28px; margin-left: 0; padding: 0; color: var(--color-muted); font-size: 12px; font-variant-numeric: tabular-nums; }.canvas-controls :deep(.el-button:hover) { color: var(--color-text); background: var(--color-surface-soft); }.canvas-controls :deep(.el-button.is-text.is-has-bg), .canvas-controls :deep(.el-button--primary.is-text) { color: var(--color-primary); }
.canvas-empty { pointer-events: none; position: absolute; inset: 0; z-index: 4; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 32px; padding: 24px; user-select: none; }.canvas-empty > :deep(.el-button) { pointer-events: auto; margin-top: 20px; }
.empty-hint { display: flex; align-items: center; gap: 12px; color: var(--color-muted); font-size: 14px; font-weight: 500; }.empty-actions { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; max-width: 100%; pointer-events: auto; }.empty-actions button { display: flex; align-items: center; gap: 16px; width: 200px; max-width: 100%; min-height: 56px; padding: 6px 8px; border: 1px solid var(--color-border); border-radius: 16px; background: var(--color-surface-soft); color: var(--color-text); font: inherit; font-size: 14px; font-weight: 600; text-align: left; cursor: pointer; transition: background-color .15s, border-color .15s; }.empty-actions button:hover { border-color: var(--color-border-strong); background: var(--color-surface); }.action-icon { display: flex; flex: 0 0 40px; width: 40px; height: 40px; align-items: center; justify-content: center; border-radius: 12px; background: color-mix(in srgb, var(--color-surface-soft) 70%, var(--color-border)); }.action-icon :deep(svg) { width: 22px; height: 22px; color: var(--color-muted); }
.canvas-status { position: absolute; bottom: 16px; left: 18px; display: flex; gap: 18px; color: var(--color-muted); font-size: 11px; pointer-events: none; }
.canvas-controls { position: absolute; z-index: 5; bottom: 16px; display: flex; align-items: center; gap: 2px; padding: 2px 4px; border: 1px solid var(--color-border); border-radius: 6px; background: color-mix(in srgb, var(--color-surface-base) 88%, transparent); backdrop-filter: blur(18px); box-shadow: var(--shadow-soft); }.canvas-controls-left { left: 16px; }.canvas-controls-center { left: 50%; transform: translateX(-50%); }.canvas-controls span { min-width: 42px; color: var(--color-muted); font-size: 11px; text-align: center; }
.canvas-menu { position: fixed; z-index: 200; width: 180px; padding: 4px; border: 1px solid var(--color-border); border-radius: 4px; background: var(--color-surface-base); box-shadow: var(--shadow-soft); }.canvas-menu button { display: block; width: 100%; text-align: left; border: 0; border-radius: 3px; background: transparent; color: var(--color-text); padding: 8px 10px; cursor: pointer; font-size: 13px; }.canvas-menu button:hover { background: var(--color-surface-soft); }.canvas-menu-divider { display: block; height: 1px; margin: 4px 6px; background: var(--color-border); }.connection-menu-title { margin: 4px 8px 6px; color: var(--color-muted); font-size: 11px; }
:deep(.vue-flow__node) { background: transparent; border: 0; padding: 0; }:deep(.vue-flow__node:hover .handle-icon) { opacity: 1; }:deep(.vue-flow__edge-path) { stroke: var(--color-primary); stroke-width: 2; }:deep(.vue-flow__edge.selected .vue-flow__edge-path) { stroke: var(--color-info); stroke-width: 3; }:deep(.vue-flow__edge.edge-node-active .vue-flow__edge-path) { stroke: var(--color-primary); }:deep(.vue-flow.edges-hidden .vue-flow__edge) { opacity: 0; pointer-events: none; }:deep(.vue-flow__minimap) { border: 1px solid var(--color-border); border-radius: 10px; background: color-mix(in srgb, var(--color-surface-base) 90%, transparent); margin: 16px; overflow: hidden; }:deep(.vue-flow__minimap-mask) { fill: var(--color-surface); }:deep(.vue-flow__minimap-node) { fill: var(--color-muted); }
.canvas-page { --el-bg-color: var(--color-surface-base); --el-bg-color-overlay: var(--color-surface-base); --el-fill-color-blank: var(--color-surface-base); --el-text-color-regular: var(--color-text); --el-text-color-primary: var(--color-text); --el-text-color-placeholder: var(--color-muted); --el-border-color: var(--color-border); --el-border-color-light: var(--color-border); --el-fill-color-light: var(--color-surface-soft); }
:deep(.el-textarea__inner) { background: var(--color-surface-soft); color: var(--color-text); }:deep(.el-button) { background: var(--color-surface-soft); color: var(--color-text); border-color: var(--color-border); }:deep(.el-button:hover) { border-color: var(--color-border-strong); background: var(--color-surface-soft); }:deep(.el-button.is-disabled) { color: var(--color-faint); }
@media (max-width: 600px) { .canvas-topbar { top: 12px; left: 12px; }.board-select { width: 140px; }.canvas-controls-left { left: 12px; max-width: calc(100% - 24px); overflow-x: auto; }.canvas-controls-center { right: 12px; left: auto; transform: none; } }
.zoom-menu { display: flex; align-items: center; gap: 4px; padding: 8px 12px 4px; }
.zoom-menu :deep(.el-input-number) { width: 90px; }
.zoom-suffix { font-size: 12px; color: var(--color-muted); }
.canvas-controls :deep(.zoom-pct-btn) { min-width: 42px; width: auto; padding: 0 4px; }
.edge-disconnect-btn { position: fixed; z-index: 1000; width: 28px; height: 28px; padding: 0; transform: translate(-50%, -50%); font-size: 16px; line-height: 1; }
.ai-orb { position: absolute; left: calc(50% + 124px); bottom: 16px; width: 34px; height: 34px; padding: 0; border-radius: 50%; background: color-mix(in srgb, var(--color-surface-base) 92%, transparent); border: 1px solid var(--color-border); backdrop-filter: blur(16px); cursor: pointer; z-index: 10; display: grid; place-items: center; transition: transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.2s, border-color 0.2s; box-shadow: 0 4px 18px rgba(0,0,0,0.28); }
.ai-orb:hover { transform: scale(1.06); box-shadow: 0 6px 26px rgba(0,0,0,0.38); }
.ai-orb.active { border-color: var(--color-primary); box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-primary) 28%, transparent), 0 4px 18px rgba(0,0,0,0.28); }
.ai-orb-avatar { width: 24px; height: 24px; pointer-events: none; }
.canvas-home .ai-orb { display: none; }
@media (max-width: 600px) { .ai-orb { left: auto; right: 12px; bottom: 64px; } }
</style>
