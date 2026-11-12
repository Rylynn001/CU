<script setup lang="ts">
import { computed, markRaw, nextTick, onBeforeUnmount, onMounted, provide, reactive, ref, watch } from 'vue'
import { onBeforeRouteLeave } from 'vue-router'
import { VueFlow, useVueFlow, SelectionMode, type Connection, type ViewportTransform } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { MiniMap } from '@vue-flow/minimap'
import { ElButton, ElSelect, ElOption, ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Picture, VideoCamera, Document, FolderOpened, ZoomIn, ZoomOut, FullScreen, Delete } from '@element-plus/icons-vue'
import CanvasNodeComponent from '../components/CanvasNode.vue'
import AssetPicker from '../components/AssetPicker.vue'
import { apiGenerate, apiVideoGenerate, authFetch, createCanvas, getApiModels, getCanvas, listCanvases, saveCanvas, uploadInputImage, type ApiModel, type CanvasSummary, type CanvasDocument } from '../api/apiService'
import { canvasActionsKey, collectInputs, makeNode, nodeKinds, validConnection, type CanvasAsset, type CanvasNode, type CanvasEdge } from '../services/canvasGraph'
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
  if (type.includes('Generation')) node.data!.model = String((type.includes('video') ? videoModels : imageModels).value[0]?.id ?? '')
  nodes.value.forEach(item => { item.selected = false })
  node.selected = true
  nodes.value.push(node)
  menu.value = undefined
  return node
}

function connect(connection: Connection) {
  if (!canEdit.value || !validConnection(connection, nodes.value, edges.value)) return
  edges.value.push({ ...connection, id: crypto.randomUUID(), type: 'simplebezier' })
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
      ? await apiVideoGenerate({ model: data.model, prompt, ratio: data.ratio, resolution: data.resolution, duration: data.duration, input_asset_ids: input.assetIds })
      : await apiGenerate({ model: Number(data.model), prompt, aspect_ratio: data.ratio, quality: data.quality, n: data.n, input_asset_ids: input.assetIds })
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
provide(canvasActionsKey, { assets, imageModels, videoModels, isSubmitting: id => submitting.has(id), run: id => { void run(id) }, pick, duplicate, remove })
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
    <div class="canvas-workspace" @contextmenu.prevent="contextMenu">
      <VueFlow v-model:nodes="nodes" v-model:edges="edges" id="creative-canvas" :node-types="nodeTypes" :min-zoom="0.2" :max-zoom="4" :pan-on-drag="[1, 2]" :selection-mode="SelectionMode.Partial" selection-on-drag :delete-key-code="null" :zoom-on-double-click="false" :nodes-draggable="canEdit" :nodes-connectable="canEdit" :connect-on-click="true" :is-valid-connection="(connection) => validConnection(connection, nodes, edges)" @connect="connect" @move-end="({ flowTransform }) => viewport = flowTransform" @pane-click="menu = undefined">
        <Background :gap="24" pattern-color="var(--color-border)" />
        <MiniMap v-if="nodes.length" pannable zoomable :width="150" :height="100" />
      </VueFlow>
      <aside class="canvas-tools" aria-label="添加节点">
        <ElButton :icon="Picture" :disabled="!canEdit" title="添加图片生成节点" @click="addNode('remote-imageGenerationNode')">图片生成</ElButton>
        <ElButton :icon="VideoCamera" :disabled="!canEdit" title="添加视频生成节点" @click="addNode('remote-videoGenerationNode')">视频生成</ElButton>
        <ElButton :icon="Document" :disabled="!canEdit" @click="addNode('remote-textNode')">文本</ElButton>
        <ElButton :icon="FolderOpened" :disabled="!canEdit" @click="pick()">资产库</ElButton>
        <ElButton :loading="uploadBusy" :disabled="!canEdit" @click="fileInput?.click()">上传素材</ElButton>
        <input ref="fileInput" hidden type="file" accept="image/*,video/*" multiple @change="upload" />
      </aside>
      <div v-if="!ready || !nodes.length" class="canvas-empty">
        <span class="empty-symbol">＋</span><h2>{{ ready ? '从一个节点开始' : '你的创作工作台' }}</h2>
        <p v-if="loadError" role="alert">{{ loadError }}</p>
        <p v-else>{{ ready ? '添加生成节点或素材，拖动两侧圆点连接输入与输出。' : '新建画布，连接文本、图片与视频。' }}</p>
        <ElButton v-if="!ready" :disabled="loading" @click="newBoard">新建画布</ElButton>
      </div>
      <footer class="canvas-status"><span>{{ nodes.length }} 个节点 · {{ edges.length }} 条连线</span><span v-if="selectedCount">已选 {{ selectedCount }} 个节点</span><span>拖拽框选 · 滚轮缩放 · 中键平移 · Delete 删除</span></footer>
      <div class="canvas-zoom"><ElButton :icon="ZoomOut" aria-label="缩小" @click="flow.zoomOut()" /><span>{{ Math.round(viewport.zoom * 100) }}%</span><ElButton :icon="ZoomIn" aria-label="放大" @click="flow.zoomIn()" /><ElButton :icon="FullScreen" aria-label="显示全部节点" @click="flow.fitView({ padding: .3 })" /></div>
    </div>
    <div v-if="menu" class="canvas-menu" :style="{ left: `${menu.x}px`, top: `${menu.y}px` }" @mouseleave="menu = undefined">
      <button v-for="kind in nodeKinds" :key="kind.type" @click="addNode(kind.type, menu?.position)">{{ kind.label }}</button>
    </div>
    <AssetPicker v-model:visible="pickerVisible" :max-select="pickerNode ? 1 : 20" allow-video @select="applyAssets" />
  </main>
</template>

<style scoped>
.canvas-page { height: 100vh; display: flex; flex-direction: column; background: transparent; color: var(--color-text); }
.canvas-toolbar { min-height: 76px; padding: 14px 24px; display: flex; align-items: center; gap: 12px; border-bottom: 1px solid var(--color-border); background: var(--color-surface); }
.canvas-heading { display: flex; align-items: center; gap: 12px; margin-right: 20px; flex-shrink: 0; }
.canvas-mark { font-size: 32px; color: var(--color-muted); }
.canvas-heading h1 { font-size: 17px; font-weight: 500; letter-spacing: 2px; }.canvas-heading p { margin-top: 4px; font-size: 11px; color: var(--color-muted); }
.board-select { width: 160px; flex-shrink: 0; }.canvas-name { width: 140px; min-width: 60px; background: transparent; color: var(--color-text); border: 0; border-bottom: 1px solid var(--color-border); padding: 6px; font-size: 13px; }
.save-state { margin-left: auto; white-space: nowrap; font-size: 11px; color: var(--color-muted); }
.canvas-workspace { position: relative; flex: 1; min-height: 0; }.canvas-tools { position: absolute; z-index: 5; top: 22px; left: 22px; padding: 6px; display: flex; gap: 4px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface-base); box-shadow: var(--shadow-soft); }
.canvas-tools :deep(.el-button), .canvas-zoom :deep(.el-button) { margin-left: 0; }
.canvas-empty { pointer-events: none; position: absolute; left: 50%; top: 45%; transform: translate(-50%, -50%); text-align: center; width: min(500px, 80%); }.canvas-empty :deep(button) { pointer-events: auto; margin-top: 20px; }
.empty-symbol { display: block; font-size: 44px; font-weight: 200; color: var(--color-faint); margin-bottom: 16px; }.canvas-empty h2 { font-size: 22px; font-weight: 400; letter-spacing: 3px; }.canvas-empty p { color: var(--color-muted); line-height: 1.8; font-size: 13px; margin-top: 12px; }
.canvas-status { position: absolute; bottom: 20px; left: 24px; display: flex; gap: 18px; color: var(--color-muted); font-size: 11px; pointer-events: none; }.canvas-status span:last-child { color: var(--color-faint); }
.canvas-zoom { position: absolute; bottom: 48px; left: 22px; display: flex; align-items: center; gap: 4px; border: 1px solid var(--color-border); background: var(--color-surface-base); border-radius: var(--radius-sm); padding: 4px; }.canvas-zoom span { padding: 0 6px; color: var(--color-muted); font-size: 11px; min-width: 40px; text-align: center; }
.canvas-menu { position: fixed; z-index: 200; width: 180px; padding: 6px; border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-surface-base); box-shadow: var(--shadow-soft); }.canvas-menu button { display: block; width: 100%; text-align: left; border: 0; background: transparent; color: var(--color-text); padding: 10px 12px; cursor: pointer; font-size: 13px; }.canvas-menu button:hover { background: var(--color-surface-soft); }
:deep(.vue-flow__node) { background: transparent; border: 0; padding: 0; }:deep(.vue-flow__edge-path) { stroke: var(--color-primary); stroke-width: 2; }:deep(.vue-flow__edge.selected .vue-flow__edge-path) { stroke: var(--color-info); stroke-width: 3; }:deep(.vue-flow__minimap) { border: 1px solid var(--color-border); border-radius: var(--radius-sm); background: var(--color-surface-base); margin: 18px; }:deep(.vue-flow__minimap-mask) { fill: var(--color-surface); }:deep(.vue-flow__minimap-node) { fill: var(--color-muted); }
.canvas-page { --el-bg-color: var(--color-surface-base); --el-bg-color-overlay: var(--color-surface-base); --el-fill-color-blank: var(--color-surface-base); --el-text-color-regular: var(--color-text); --el-text-color-primary: var(--color-text); --el-text-color-placeholder: var(--color-muted); --el-border-color: var(--color-border); --el-border-color-light: var(--color-border); --el-fill-color-light: var(--color-surface-soft); }
:deep(.el-textarea__inner) { background: var(--color-surface-soft); color: var(--color-text); }:deep(.el-button) { background: var(--color-surface-soft); color: var(--color-text); border-color: var(--color-border); }:deep(.el-button:hover) { border-color: var(--color-border-strong); background: var(--color-surface-soft); }:deep(.el-button.is-disabled) { color: var(--color-faint); }
@media (max-width: 1050px) { .canvas-toolbar { flex-wrap: wrap; padding: 12px; }.canvas-heading { margin-right: 0; }.canvas-name { width: 100px; }.canvas-tools { flex-wrap: wrap; max-width: calc(100% - 40px); }.canvas-status span:last-child { display: none; } }
@media (max-width: 600px) { .canvas-heading p, .save-state { display: none; }.canvas-heading h1 { font-size: 14px; }.board-select { width: 120px; }.canvas-tools { top: 12px; left: 12px; gap: 0; }.canvas-toolbar { gap: 6px; } }
</style>
