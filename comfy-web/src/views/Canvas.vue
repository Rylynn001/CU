<script setup lang="ts">
import { computed, markRaw, nextTick, onBeforeUnmount, onMounted, provide, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { VueFlow, useVueFlow, SelectionMode, type Connection, type OnConnectStartParams, type ViewportTransform } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { MiniMap } from '@vue-flow/minimap'
import { ElButton, ElSelect, ElOption, ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Picture, VideoCamera, Document, Delete } from '@element-plus/icons-vue'
import { Focus, Folders, Info, Magnet, Map, MousePointer2, Network, Plus as PlusIcon, Search, Workflow } from '@lucide/vue'
import CanvasNodeComponent from '../components/CanvasNode.vue'
import AssetPicker from '../components/AssetPicker.vue'
import { apiGenerate, apiVideoGenerate, authFetch, createCanvas, getApiModels, getCanvas, listCanvases, saveCanvas, uploadInputImage, type ApiModel, type CanvasSummary, type CanvasDocument } from '../api/apiService'
import { canvasActionsKey, collectInputs, makeNode, nodeKinds, validConnection, type CanvasAsset, type CanvasNode, type CanvasEdge, type CanvasParameterValue } from '../services/canvasGraph'
import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/minimap/dist/style.css'

const flow = useVueFlow({ id: 'creative-canvas' })
const nodes = ref<CanvasNode[]>([])
const edges = ref<CanvasEdge[]>([])
const viewport = ref<ViewportTransform>({ x: 0, y: 0, zoom: 1 })
const boards = ref<CanvasSummary[]>([])
const activeId = ref<number>()
const name = ref('新画布')
const loading = ref(false)
const ready = ref(false)
const loadError = ref('')
const saveState = ref('')
const assets = ref<Record<number, CanvasAsset>>({})
const imageModels = ref<ApiModel[]>([])
const videoModels = ref<ApiModel[]>([])
const pickerVisible = ref(false)
const pickerNode = ref<string>()
const fileInput = ref<HTMLInputElement>()
const uploadBusy = ref(false)
const creating = ref(false)
const menu = ref<{ x: number; y: number; position: { x: number; y: number } }>()
const connectionMenu = ref<{ x: number; y: number; position: { x: number; y: number }; nodeId: string; handleId: string; handleType: 'source' | 'target' }>()
const pendingConnection = ref<OnConnectStartParams>()
let ignorePaneClick = false
const showEdges = ref(true)
const snapEnabled = ref(false)
const showMap = ref(false)
const handMode = ref(false)
const submitting = reactive(new Set<string>())
const polling = new Set<string>()
let saveTimer: ReturnType<typeof setTimeout> | undefined
let pollTimer: ReturnType<typeof setInterval> | undefined
let saveQueue: Promise<void> = Promise.resolve()
const savedSnapshot = ref('')
let disposed = false

const nodeTypes = Object.fromEntries(nodeKinds.map(kind => [kind.type, markRaw(CanvasNodeComponent)]))
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
  const current = node.data.parameters ?? {}
  const next: Record<string, CanvasParameterValue> = {}
  for (const field of fields) {
    if (current[field.key] !== undefined) next[field.key] = current[field.key]
    else if (field.default !== undefined) next[field.key] = field.default
  }
  node.data.parameters = next
}

function normalizeNode(node: CanvasNode) {
  node.data.parameters ??= {}
  if (!node.data.parameters.aspect_ratio && node.data.ratio) node.data.parameters.aspect_ratio = node.data.ratio
  if (!node.data.parameters.quality && node.data.quality) node.data.parameters.quality = node.data.quality
  if (!node.data.parameters.ratio && node.data.ratio) node.data.parameters.ratio = node.data.ratio
  if (!node.data.parameters.resolution && node.data.resolution) node.data.parameters.resolution = node.data.resolution
  if (!node.data.parameters.duration && node.data.duration) node.data.parameters.duration = node.data.duration
  syncModelParameters(node, modelForNode(node))
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
      await saveCanvas(id, JSON.parse(current))
      savedSnapshot.value = current
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

async function openBoard(id: number) {
  if (loading.value || submitting.size || uploadBusy.value) return
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
    saveState.value = '已保存'
    loadError.value = ''
    await nextTick()
    await flow.setViewport(viewport.value)
    await hydrateAssets().catch(error => ElMessage.warning(message(error)))
    void pollTasks()
  } catch (error) {
    loadError.value = message(error)
    ElMessage.error(message(error))
  } finally { loading.value = false }
}

async function newBoard() {
  if (loading.value || creating.value || submitting.size || uploadBusy.value) return
  creating.value = true
  try {
    await persist()
    const board = await createCanvas()
    boards.value.unshift(board)
    await openBoard(board.id)
  } catch (error) { ElMessage.error(message(error)) }
  finally { creating.value = false }
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
  return node
}

function connect(connection: Connection) {
  if (!canEdit.value || !validConnection(connection, nodes.value, edges.value)) return
  edges.value.push({ ...connection, id: crypto.randomUUID(), type: 'simplebezier' })
  pendingConnection.value = undefined
  connectionMenu.value = undefined
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
  // 拖线松手后的合成点击不能立即关掉刚打开的菜单。
  if (ignorePaneClick) { ignorePaneClick = false; return }
  menu.value = undefined
  connectionMenu.value = undefined
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
}

function remove(id: string) {
  if (!canEdit.value) return
  if (nodes.value.find(node => node.id === id)?.data?.task?.state === 'pending' || submitting.has(id)) {
    ElMessage.warning('请等待节点生成完成后再移除')
    return
  }
  nodes.value = nodes.value.filter(node => node.id !== id)
  edges.value = edges.value.filter(edge => edge.source !== id && edge.target !== id)
}

function deleteSelection() {
  nodes.value.filter(node => node.selected).forEach(node => remove(node.id))
  edges.value = edges.value.filter(edge => !edge.selected)
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
    const result = node.type === 'remote-videoGenerationNode'
      ? await apiVideoGenerate({ model: Number(data.model), prompt, parameters: data.parameters, input_asset_ids: input.assetIds })
      : await apiGenerate({ model: Number(data.model), prompt, parameters: data.parameters, input_asset_ids: input.assetIds })
    const taskId = 'task_id' in result ? result.task_id : 'taskId' in result ? result.taskId : undefined
    const historyId = 'history_id' in result ? result.history_id : 'historyId' in result ? result.historyId : undefined
    if (!taskId || !historyId) throw new Error('生成接口没有返回任务和历史记录 ID')
    data.task = { taskId, historyId, state: 'pending' }
    // 先保存任务归属，离开页面后也能通过历史记录恢复结果。
    await persist()
    void pollTasks()
  } catch (error) { ElMessage.error(message(error)) }
  finally { submitting.delete(id) }
}

async function pollTasks() {
  for (const node of nodes.value) {
    const task = node.data?.task
    if (!task || task.state !== 'pending' || polling.has(task.taskId)) continue
    const boardId = activeId.value
    polling.add(task.taskId)
    try {
      const response = await authFetch(`/api/api-proxy/canvases/tasks/${task.historyId}`)
      if (!response.ok) throw new Error('生成记录查询失败')
      const result = await response.json()
      if (disposed || activeId.value !== boardId || !nodes.value.includes(node)) continue
      if (['done', 'completed', 'success'].includes(result.status)) {
        if (!result.asset_ids.length) throw new Error('生成已完成，但资产尚未入库')
        const video = node.type === 'remote-videoGenerationNode'
        node.data!.outputs[video ? 'video' : 'image'] = { dataType: video ? 'VIDEO' : 'IMAGE', value: { assetIds: result.asset_ids } }
        task.state = 'completed'
        delete task.error
        await hydrateAssets()
        await persist()
      } else if (['error', 'failed', 'cancelled'].includes(result.status)) {
        task.state = 'failed'
        task.error = result.message || '生成失败，请调整后重新生成'
        await persist()
      } else {
        // 沿用原有任务接口，视频供应商的查询和结果入库也由它完成。
        const statusResponse = await authFetch(`/api/api-proxy/task/${task.taskId}`)
        if (disposed || activeId.value !== boardId) continue
        if (statusResponse.status === 404) {
          task.state = 'failed'
          task.error = '任务状态已过期，且历史记录尚未完成，请检查原任务后重试'
        } else if (statusResponse.ok) {
          const status = await statusResponse.json()
          if (disposed || activeId.value !== boardId) continue
          if (status.status === 'failed') { task.state = 'failed'; task.error = status.error?.error_message || '生成失败' }
        }
      }
    } catch (error) {
      // 网络暂时失败时保留任务，下次轮询继续，不重复提交生成。
      if (!disposed && activeId.value === boardId) task.error = message(error)
    } finally { polling.delete(task.taskId) }
  }
}

async function deleteBoard() {
  if (!activeId.value || submitting.size || uploadBusy.value) return
  try {
    await ElMessageBox.confirm('删除画布不会删除资产和生成记录。确定删除？', '删除画布', { confirmButtonText: '删除', cancelButtonText: '取消' })
    await persist()
    const response = await authFetch(`/api/api-proxy/canvases/${activeId.value}`, { method: 'DELETE' })
    if (!response.ok) throw new Error('画布删除失败')
    boards.value = boards.value.filter(board => board.id !== activeId.value)
    ready.value = false; activeId.value = undefined; nodes.value = []; edges.value = []
    if (boards.value[0]) await openBoard(boards.value[0].id)
  } catch (error) { if (error !== 'cancel' && error !== 'close') ElMessage.error(message(error)) }
}

function contextMenu(event: MouseEvent) {
  if (!canEdit.value) return
  menu.value = { x: Math.min(event.clientX, window.innerWidth - 180), y: Math.min(event.clientY, window.innerHeight - 220), position: flow.screenToFlowCoordinate({ x: event.clientX, y: event.clientY }) }
}

function keydown(event: KeyboardEvent) {
  if ((event.target as HTMLElement).closest('input,textarea,select,[contenteditable="true"],.el-dialog')) return
  if (event.key === 'Delete' || event.key === 'Backspace') { event.preventDefault(); deleteSelection() }
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'd') { event.preventDefault(); nodes.value.filter(node => node.selected).forEach(node => duplicate(node.id)) }
}

function beforeUnload(event: BeforeUnloadEvent) { if (dirty.value || submitting.size || uploadBusy.value) { event.preventDefault(); event.returnValue = '' } }
onBeforeRouteLeave(async () => {
  if (submitting.size || uploadBusy.value) { ElMessage.warning('请等待任务提交或素材上传完成后再离开'); return false }
  try { await persist(); return true } catch (error) { ElMessage.error(message(error)); return false }
})
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
  run: id => { void run(id) },
  pick,
  duplicate,
  remove,
})
onMounted(async () => {
  window.addEventListener('keydown', keydown)
  window.addEventListener('beforeunload', beforeUnload)
  pollTimer = setInterval(() => { void pollTasks() }, 3000)
  try {
    boards.value = await listCanvases()
    if (boards.value[0]) await openBoard(boards.value[0].id)
  } catch (error) { loadError.value = `${message(error)}。请确认已执行画布建表 SQL 并更新后端。` }
  const results = await Promise.allSettled([getApiModels('image'), getApiModels('video')])
  if (results[0].status === 'fulfilled') imageModels.value = results[0].value
  if (results[1].status === 'fulfilled') videoModels.value = results[1].value
  if (results.some(result => result.status === 'rejected')) ElMessage.warning('部分模型加载失败，请刷新页面重试')
  nodes.value.forEach(normalizeNode)
})
onBeforeUnmount(() => { disposed = true; clearTimeout(saveTimer); clearInterval(pollTimer); window.removeEventListener('keydown', keydown); window.removeEventListener('beforeunload', beforeUnload) })
</script>

<template>
  <main class="canvas-page">
    <header class="canvas-toolbar">
      <div class="canvas-heading"><span class="canvas-mark">⌘</span><div><h1>创作画布</h1><p>把想法连接起来</p></div></div>
      <ElSelect :model-value="activeId" :disabled="loading || submitting.size > 0 || uploadBusy" placeholder="选择画布" class="board-select" @change="openBoard"><ElOption v-for="board in boards" :key="board.id" :value="board.id" :label="board.name" /></ElSelect>
      <input v-if="ready" v-model="name" class="canvas-name" maxlength="100" aria-label="画布名称" :disabled="loading" />
      <span class="save-state" role="status">{{ saveState }}</span>
      <ElButton :icon="Plus" :disabled="loading || submitting.size > 0 || uploadBusy" @click="newBoard">新建画布</ElButton>
      <ElButton :disabled="!canEdit || !dirty" @click="persist().catch(error => ElMessage.error(message(error)))">保存</ElButton>
      <ElButton :icon="Delete" :disabled="!canEdit || submitting.size > 0 || uploadBusy" aria-label="删除画布" @click="deleteBoard" />
    </header>
    <div class="canvas-workspace" @contextmenu.prevent="contextMenu" @pointerdown.capture="ignorePaneClick = false">
      <VueFlow v-model:nodes="nodes" v-model:edges="edges" id="creative-canvas" :node-types="nodeTypes" :min-zoom="0.2" :max-zoom="8" :pan-on-drag="handMode ? true : [1, 2]" :selection-mode="SelectionMode.Partial" selection-on-drag :snap-to-grid="snapEnabled" :snap-grid="[16, 16]" :delete-key-code="null" :zoom-on-double-click="false" :nodes-draggable="canEdit" :nodes-connectable="canEdit" :connect-on-click="false" :is-valid-connection="(connection) => validConnection(connection, nodes, edges)" :class="{ 'edges-hidden': !showEdges }" @connect="connect" @connect-start="connectStart" @connect-end="connectEnd" @move-end="({ flowTransform }) => viewport = flowTransform" @pane-click="paneClick">
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
        <ElButton text aria-label="素材库" title="素材库" @click="pick()"><Folders :size="18" /></ElButton>
        <ElButton text aria-label="整理画布" title="整理画布" @click="flow.fitView({ padding: .3 })"><Network :size="18" /></ElButton>
        <ElButton text :type="showMap ? 'primary' : undefined" aria-label="显示地图" title="显示地图" @click="showMap = !showMap"><Map :size="18" /></ElButton>
        <ElButton text :type="snapEnabled ? 'primary' : undefined" aria-label="网格吸附" title="网格吸附" @click="snapEnabled = !snapEnabled"><Magnet :size="18" /></ElButton>
        <ElButton text :type="showEdges ? 'primary' : undefined" aria-label="显示连线" title="显示连线" @click="showEdges = !showEdges"><Workflow :size="18" /></ElButton>
        <ElButton text aria-label="适应视图" title="适应视图" @click="flow.fitView({ padding: .3 })"><Focus :size="18" /></ElButton>
        <ElButton text aria-label="缩放" title="缩放" @click="flow.zoomIn()">{{ Math.round(viewport.zoom * 100) }}%</ElButton>
      </div>
      <div class="canvas-controls canvas-controls-center" aria-label="画布工具">
        <ElButton text aria-label="添加节点" title="添加节点" @click="openCenterNodeMenu"><PlusIcon :size="18" /></ElButton>
        <ElButton text :type="handMode ? 'primary' : undefined" aria-label="移动工具" title="移动工具" @click="handMode = !handMode"><MousePointer2 :size="18" /></ElButton>
        <ElButton text aria-label="定位节点" title="定位节点" @click="flow.fitView({ padding: .3 })"><Search :size="18" /></ElButton>
        <ElButton text aria-label="画布提示" title="双击画布添加节点；从端口拖出可自动创建兼容节点"><Info :size="18" /></ElButton>
      </div>
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
  </main>
</template>

<style scoped>
.canvas-page { height: 100vh; display: flex; flex-direction: column; background: transparent; color: var(--color-text); }
.canvas-toolbar { min-height: 56px; padding: 10px 18px; display: flex; align-items: center; gap: 10px; border-bottom: 1px solid var(--color-border); background: color-mix(in srgb, var(--color-surface-base) 68%, transparent); backdrop-filter: blur(18px); }
.canvas-heading { display: flex; align-items: center; gap: 10px; margin-right: 12px; flex-shrink: 0; }
.canvas-mark { display: grid; width: 28px; height: 28px; place-items: center; border: 1px solid var(--color-border-strong); border-radius: 8px; color: var(--color-text); font-size: 16px; }
.canvas-heading h1 { font-size: 14px; font-weight: 600; letter-spacing: .4px; }.canvas-heading p { margin-top: 2px; font-size: 10px; color: var(--color-muted); }
.board-select { width: 160px; flex-shrink: 0; }.canvas-name { width: 140px; min-width: 60px; background: transparent; color: var(--color-text); border: 0; border-bottom: 1px solid var(--color-border); padding: 6px; font-size: 13px; }
.save-state { margin-left: auto; white-space: nowrap; font-size: 11px; color: var(--color-muted); }
.canvas-workspace { position: relative; flex: 1; min-height: 0; container-type: inline-size; }
.canvas-controls :deep(.el-button) { width: 28px; height: 28px; margin-left: 0; padding: 0; color: var(--color-muted); font-size: 12px; font-variant-numeric: tabular-nums; }.canvas-controls :deep(.el-button:hover) { color: var(--color-text); background: var(--color-surface-soft); }
.canvas-empty { pointer-events: none; position: absolute; inset: 0; z-index: 4; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 32px; padding: 24px; user-select: none; }.canvas-empty > :deep(.el-button) { pointer-events: auto; margin-top: 20px; }
.empty-hint { display: flex; align-items: center; gap: 12px; color: var(--color-muted); font-size: 14px; font-weight: 500; }.empty-actions { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; max-width: 100%; pointer-events: auto; }.empty-actions button { display: flex; align-items: center; gap: 16px; width: 200px; max-width: 100%; min-height: 56px; padding: 6px 8px; border: 1px solid var(--color-border); border-radius: 16px; background: var(--color-surface-soft); color: var(--color-text); font: inherit; font-size: 14px; font-weight: 600; text-align: left; cursor: pointer; transition: background-color .15s, border-color .15s; }.empty-actions button:hover { border-color: var(--color-border-strong); background: var(--color-surface); }.action-icon { display: flex; flex: 0 0 40px; width: 40px; height: 40px; align-items: center; justify-content: center; border-radius: 12px; background: color-mix(in srgb, var(--color-surface-soft) 70%, var(--color-border)); }.action-icon :deep(svg) { width: 22px; height: 22px; color: var(--color-muted); }
.canvas-status { position: absolute; bottom: 16px; left: 18px; display: flex; gap: 18px; color: var(--color-muted); font-size: 11px; pointer-events: none; }
.canvas-controls { position: absolute; z-index: 5; bottom: 16px; display: flex; align-items: center; gap: 2px; padding: 2px 4px; border: 1px solid var(--color-border); border-radius: 6px; background: color-mix(in srgb, var(--color-surface-base) 88%, transparent); backdrop-filter: blur(18px); box-shadow: var(--shadow-soft); }.canvas-controls-left { left: 16px; }.canvas-controls-center { left: 50%; transform: translateX(-50%); }.canvas-controls span { min-width: 42px; color: var(--color-muted); font-size: 11px; text-align: center; }
.canvas-menu { position: fixed; z-index: 200; width: 180px; padding: 4px; border: 1px solid var(--color-border); border-radius: 4px; background: var(--color-surface-base); box-shadow: var(--shadow-soft); }.canvas-menu button { display: block; width: 100%; text-align: left; border: 0; border-radius: 3px; background: transparent; color: var(--color-text); padding: 8px 10px; cursor: pointer; font-size: 13px; }.canvas-menu button:hover { background: var(--color-surface-soft); }.canvas-menu-divider { display: block; height: 1px; margin: 4px 6px; background: var(--color-border); }.connection-menu-title { margin: 4px 8px 6px; color: var(--color-muted); font-size: 11px; }
:deep(.vue-flow__node) { background: transparent; border: 0; padding: 0; }:deep(.vue-flow__edge-path) { stroke: var(--color-primary); stroke-width: 2; }:deep(.vue-flow.edges-hidden .vue-flow__edge) { opacity: 0; pointer-events: none; }:deep(.vue-flow__edge.selected .vue-flow__edge-path) { stroke: var(--color-info); stroke-width: 3; }:deep(.vue-flow__minimap) { border: 1px solid var(--color-border); border-radius: 10px; background: color-mix(in srgb, var(--color-surface-base) 90%, transparent); margin: 16px; overflow: hidden; }:deep(.vue-flow__minimap-mask) { fill: var(--color-surface); }:deep(.vue-flow__minimap-node) { fill: var(--color-muted); }
.canvas-page { --el-bg-color: var(--color-surface-base); --el-bg-color-overlay: var(--color-surface-base); --el-fill-color-blank: var(--color-surface-base); --el-text-color-regular: var(--color-text); --el-text-color-primary: var(--color-text); --el-text-color-placeholder: var(--color-muted); --el-border-color: var(--color-border); --el-border-color-light: var(--color-border); --el-fill-color-light: var(--color-surface-soft); }
:deep(.el-textarea__inner) { background: var(--color-surface-soft); color: var(--color-text); }:deep(.el-button) { background: var(--color-surface-soft); color: var(--color-text); border-color: var(--color-border); }:deep(.el-button:hover) { border-color: var(--color-border-strong); background: var(--color-surface-soft); }:deep(.el-button.is-disabled) { color: var(--color-faint); }
@media (max-width: 1050px) { .canvas-toolbar { flex-wrap: wrap; padding: 10px 12px; }.canvas-heading { margin-right: 0; }.canvas-name { width: 100px; }.canvas-status span:last-child { display: none; } }
@media (max-width: 600px) { .canvas-heading p, .save-state { display: none; }.canvas-heading h1 { font-size: 13px; }.board-select { width: 120px; }.canvas-toolbar { gap: 6px; }.empty-actions { flex-wrap: wrap; }.canvas-controls-left { left: 12px; max-width: calc(100% - 24px); overflow-x: auto; }.canvas-controls-center { right: 12px; left: auto; transform: none; } }
</style>
