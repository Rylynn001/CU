<script setup lang="ts">
import { computed, inject, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Handle, Position, useVueFlow, type NodeProps } from '@vue-flow/core'
import { CircleDashed, CircleDot, FileText, Image, Video, Loader2 } from '@lucide/vue'
import { ElButton, ElInput, ElSelect, ElOption, ElInputNumber, ElSwitch, ElCard, ElDropdown, ElDropdownMenu, ElDropdownItem, ElSlider } from 'element-plus'
import { canvasActionsKey, canvasReferences, type CanvasNodeData } from '../services/canvasGraph'
import mediaReferenceInput from './mediaReferenceInput.vue'

const props = defineProps<NodeProps<CanvasNodeData>>()
const actions = inject(canvasActionsKey)!
const { updateNodeInternals, viewport, connectionLookup, findNode, getNodes, getEdges } = useVueFlow()
const references = computed(() => canvasReferences(getNodes.value, actions.assets.value, getEdges.value, props.id))

const generating = computed(() => props.type.includes('Generation'))
const isVideo = computed(() => props.type.includes('video'))
const isText = computed(() => props.type === 'remote-textNode')
const busy = computed(() => props.data.task?.state === 'pending' || actions.isSubmitting(props.id))
const models = computed(() => isVideo.value ? actions.videoModels.value : actions.imageModels.value)
const selectedModel = computed(() => models.value.find(model => String(model.id) === String(props.data.model)))
const parameterFields = computed(() => selectedModel.value?.parameters?.fields ?? [])
const media = computed(() => Object.values(props.data.outputs).flatMap(output =>
  typeof output.value === 'string' ? [] : output.value.assetIds.map(id => actions.assets.value[id] ?? { id, url: '', type: isVideo.value ? 'video' : 'image' })
))

function isHandleConnected(handle: CanvasNodeData['handles'][number]) {
  return !!connectionLookup.value.get(`${props.id}-${handle.type}-${handle.id}`)?.size
}
function isHandleNodeActive(handle: CanvasNodeData['handles'][number]) {
  const connections = connectionLookup.value.get(`${props.id}-${handle.type}-${handle.id}`)
  if (!connections?.size) return false
  if (props.selected || props.dragging) return true
  for (const conn of connections.values()) {
    const other = findNode(handle.type === 'source' ? conn.target : conn.source)
    if (other?.selected || other?.dragging) return true
  }
  return false
}

async function refreshBounds() { await nextTick(); updateNodeInternals([props.id]) }
watch(media, refreshBounds)

const nodeArticle = ref<HTMLElement>()
let stopResize: (() => void) | undefined
function startResize(event: PointerEvent) {
  if (event.button !== 0) return
  const element = nodeArticle.value
  if (!element) return
  const bounds = element.getBoundingClientRect()
  const zoom = viewport.value.zoom
  const x = event.clientX
  const y = event.clientY
  const move = (pointer: PointerEvent) => {
    props.data.width = Math.round(Math.max(260, Math.min(1200, (bounds.width + pointer.clientX - x) / zoom)))
    props.data.height = Math.round(Math.max(180, Math.min(1200, (bounds.height + pointer.clientY - y) / zoom)))
    void refreshBounds()
  }
  stopResize = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', finish)
    window.removeEventListener('pointercancel', finish)
  }
  const finish = () => { stopResize?.(); stopResize = undefined }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', finish, { once: true })
  window.addEventListener('pointercancel', finish, { once: true })
}
function resizeWithKeyboard(event: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return
  event.preventDefault()
  const dx = event.key === 'ArrowLeft' ? -10 : event.key === 'ArrowRight' ? 10 : 0
  const dy = event.key === 'ArrowUp' ? -10 : event.key === 'ArrowDown' ? 10 : 0
  const el = nodeArticle.value
  if (!el) return
  props.data.width = Math.round(Math.max(260, Math.min(1200, (props.data.width ?? el.offsetWidth) + dx)))
  props.data.height = Math.round(Math.max(180, Math.min(1200, (props.data.height ?? el.offsetHeight) + dy)))
  void refreshBounds()
}
onBeforeUnmount(() => stopResize?.())

const editingLabel = ref(false)
const labelDraft = ref('')
const labelInput = ref<HTMLInputElement>()
async function editLabel() {
  labelDraft.value = props.data.label
  editingLabel.value = true
  await nextTick()
  labelInput.value?.select()
}
function saveLabel() {
  const label = labelDraft.value.trim()
  if (label) props.data.label = label
  editingLabel.value = false
}
function confirmLabel(event: KeyboardEvent) {
  if (event.isComposing) return
  event.preventDefault()
  saveLabel()
}

function setText(value: string) {
  props.data.prompt = value
  props.data.outputs.text = { dataType: 'STRING', value }
}
function setModel(value: string | number) {
  actions.setModel(props.id, String(value))
}
function parameterValue(key: string, fallback?: string | number | boolean) {
  return props.data.parameters?.[key] ?? fallback ?? ''
}
function setParameter(key: string, value: string | number | boolean | undefined) {
  props.data.parameters ??= {}
  if (value !== undefined) props.data.parameters[key] = value
}
function handleTop(handle: CanvasNodeData['handles'][number]) {
  const sameType = props.data.handles.filter(item => item.type === handle.type)
  const index = sameType.indexOf(handle)
  return `${((index + 1) / (sameType.length + 1)) * 100}%`
}
function moveHandle(event: PointerEvent) {
  if (event.pointerType === 'touch') return
  const element = event.currentTarget as HTMLElement
  const rect = element.getBoundingClientRect()
  if (!rect.width || !rect.height) return
  const x = ((event.clientX - rect.left - rect.width / 2) / rect.width) * 18
  const y = ((event.clientY - rect.top - rect.height / 2) / rect.height) * 18
  const strength = Math.min(0.3, 6 / (Math.hypot(x, y) || 1))
  element.style.setProperty('--handleX', `${x * strength}px`)
  element.style.setProperty('--handleY', `${y * strength}px`)
}
function resetHandle(event: PointerEvent) {
  const element = event.currentTarget as HTMLElement
  element.style.removeProperty('--handleX')
  element.style.removeProperty('--handleY')
}

function handleCommand(command: string) {
  if (command === 'duplicate') actions.duplicate(props.id)
  if (command === 'delete' && !busy.value) actions.remove(props.id)
}
</script>

<template>
  <article ref="nodeArticle" class="canvas-node" :class="{ selected, generating: busy }" :style="{ width: data.width ? `${data.width}px` : undefined, height: data.height ? `${data.height}px` : undefined }">
    <header class="node-header">
      <component :is="isText ? FileText : isVideo ? Video : Image" class="node-kind-icon" :size="14" aria-hidden="true" />
      <input
        v-if="editingLabel"
        ref="labelInput"
        v-model="labelDraft"
        class="node-name-input nodrag"
        aria-label="节点名称"
        @pointerdown.stop
        @mousedown.stop
        @dblclick.stop
        @keydown.stop
        @keydown.enter="confirmLabel"
        @keydown.esc.prevent="editingLabel = false"
        @blur="saveLabel"
      />
      <span
        v-else
        class="node-name nodrag"
        :title="`${data.label}（双击编辑名称）`"
        @dblclick.stop="editLabel"
      >{{ data.label }}</span>
      <ElDropdown class="nodrag" trigger="click" placement="bottom-end" :show-timeout="0" :hide-timeout="0" @command="handleCommand">
        <div class="node-menu-trigger">···</div>
        <template #dropdown>
          <ElDropdownMenu>
            <ElDropdownItem command="duplicate">创建副本</ElDropdownItem>
            <ElDropdownItem command="delete" :disabled="busy">移除节点</ElDropdownItem>
          </ElDropdownMenu>
        </template>
      </ElDropdown>
    </header>
    <ElCard class="node-card" shadow="never" :body-style="{ padding: '8px' }">
      <div v-if="busy && !media.length" class="node-loading" role="status" aria-label="生成中">
        <Loader2 class="loading-icon" :size="22" aria-hidden="true" />
        <span>生成中…</span>
      </div>
      <ElInput v-else-if="isText" class="nodrag nowheel" type="textarea" :rows="5" :model-value="data.prompt" placeholder="输入文本，连到生成节点作为提示词" @update:model-value="setText" />
      <div v-else-if="media.length" class="node-media nowheel">
        <template v-for="asset in media" :key="asset.id">
          <video v-if="asset.url && asset.type === 'video'" :src="asset.url" controls preload="metadata" @loadedmetadata="refreshBounds" />
          <img v-else-if="asset.url" :src="asset.url" alt="节点图片" draggable="false" @load="refreshBounds" />
          <div v-else class="media-missing">资产 {{ asset.id }} 暂不可用</div>
        </template>
      </div>
      <div v-else class="node-empty">
        <span>{{ generating ? '创作从这里开始' : '从资产库选择素材' }}</span>
        <small>{{ generating ? '连接参考素材，或直接输入描述' : '素材沿用现有资产库' }}</small>
      </div>
      <p v-if="data.task?.error" class="node-error" role="alert">{{ data.task.error }}</p>
      <div v-if="!generating && !isText" class="nodrag node-footer">
        <ElButton size="small" @click="actions.pick(id)">选择素材</ElButton>
      </div>
    </ElCard>
    <button
      v-if="selected"
      class="resize-corner nodrag nopan"
      title="拖动调整节点大小（方向键微调）"
      aria-label="调整节点大小"
      @pointerdown.stop.prevent="startResize"
      @keydown.stop="resizeWithKeyboard"
      @mousedown.stop
      @click.stop
      @dblclick.stop
    />
    <template v-for="handle in data.handles" :key="handle.id">
      <Handle
        :id="handle.id"
        :type="handle.type"
        :position="handle.type === 'target' ? Position.Left : Position.Right"
        class="node-handle"
        :class="{
          connected: isHandleConnected(handle),
          'connected-node-active': isHandleNodeActive(handle),
        }"
        role="button"
        :title="handle.label"
        :aria-label="handle.label"
        :style="{ top: handleTop(handle) }"
        @pointermove="moveHandle"
        @pointerleave="resetHandle"
        @pointercancel="resetHandle"
      >
        <CircleDot class="handle-icon connected-icon" :size="18" aria-hidden="true" />
        <CircleDashed class="handle-icon dashed-icon" :size="18" aria-hidden="true" />
      </Handle>
    </template>
    <section v-if="generating && selected" class="node-settings nodrag nopan nowheel" @keydown.stop @dblclick.stop>
      <mediaReferenceInput v-model="data.prompt" :items="references" :disabled="busy" />
      <div class="settings-grid">
        <label>模型<ElSelect :model-value="data.model" :disabled="busy" placeholder="选择模型" @update:model-value="setModel"><ElOption v-for="model in models" :key="model.id" :label="model.description || model.name" :value="String(model.id)" /></ElSelect></label>
        <template v-for="field in parameterFields" :key="field.key">
          <label v-if="field.type === 'select' && field.options?.length">{{ field.label }}<ElSelect :model-value="parameterValue(field.key, field.default)" :disabled="busy" @update:model-value="setParameter(field.key, $event)"><ElOption v-for="option in field.options" :key="String(option)" :label="String(option)" :value="option" /></ElSelect></label>
          <label v-else-if="field.type === 'slider' || field.type === 'number'" class="slider-field">
            <span>{{ field.label }}<em class="param-val">{{ parameterValue(field.key, field.default) }}{{ field.key.includes('duration') ? 's' : '' }}</em></span>
            <ElSlider :model-value="Number(parameterValue(field.key, field.default))" :min="field.min ?? 1" :max="field.max ?? 100" :step="field.step ?? 1" :disabled="busy" :show-tooltip="false" @update:model-value="setParameter(field.key, $event)" />
          </label>
          <label v-else-if="field.type === 'boolean'" class="switch-field">{{ field.label }}<ElSwitch :model-value="Boolean(parameterValue(field.key, field.default))" :disabled="busy" @update:model-value="setParameter(field.key, $event)" /></label>
          <label v-else>{{ field.label }}<ElInput :model-value="String(parameterValue(field.key, field.default))" :disabled="busy" @update:model-value="setParameter(field.key, $event)" /></label>
        </template>
      </div>
      <ElButton class="generate-button" :loading="busy" :disabled="!data.model" @click="actions.run(id)">{{ busy ? '正在生成' : isVideo ? '生成视频' : '生成图片' }}</ElButton>
    </section>
  </article>
</template>

<style scoped>
.canvas-node {
  position: relative;
  width: 220px;
  color: var(--el-text-color-primary, var(--color-text));
  text-align: left;
}
.canvas-node.selected { z-index: 2; }

.node-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 4px 8px;
  font-size: 14px;
  line-height: 20px;
}
.node-kind-icon { flex-shrink: 0; color: var(--color-muted); }
.node-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  cursor: grab;
  user-select: none;
}
.node-name:active { cursor: grabbing; }
.node-name-input {
  flex: 1;
  min-width: 0;
  width: 100%;
  padding: 0 4px;
  border: 1px solid var(--el-color-primary, var(--color-primary));
  border-radius: 3px;
  outline: none;
  background: var(--color-surface-base);
  color: inherit;
  font: inherit;
  font-size: 13px;
  line-height: inherit;
}
.node-menu-trigger {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 4px;
  color: var(--color-muted);
  font-size: 16px;
  letter-spacing: 1px;
  cursor: pointer;
  visibility: hidden;
  flex-shrink: 0;
}
.canvas-node:hover .node-menu-trigger,
.canvas-node.selected .node-menu-trigger { visibility: visible; }
.node-menu-trigger:hover { color: var(--color-text); background: var(--color-surface-soft); }

.node-card {
  --el-card-border-color: var(--color-border);
  --el-card-bg-color: var(--color-surface-base);
  min-height: 100px;
}
.canvas-node.selected :deep(.el-card) {
  border-color: color-mix(in srgb, var(--color-primary) 50%, var(--color-border));
}

.node-loading {
  min-height: 120px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--color-muted);
  font-size: 13px;
}
.loading-icon {
  color: var(--color-primary);
  animation: nodeLoading 1s linear infinite;
}
@keyframes nodeLoading { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .loading-icon { animation: none; } }

.node-empty { min-height: 120px; display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 10px; color: var(--color-muted); font-size: 13px; }
.node-empty small { color: var(--color-faint); font-size: 11px; }
.node-media { max-height: 360px; overflow: auto; display: grid; gap: 6px; }
.node-media img, .node-media video { display: block; width: 100%; max-height: 300px; object-fit: contain; border-radius: 6px; }
.node-media img { pointer-events: none; }
.media-missing { padding: 30px 10px; color: var(--color-muted); font-size: 12px; }
.node-footer { padding-top: 6px; display: flex; justify-content: flex-end; }
.node-error { color: var(--color-danger); font-size: 12px; padding: 8px; overflow-wrap: anywhere; }

.resize-corner {
  position: absolute;
  right: 2px;
  bottom: 2px;
  width: 10px;
  height: 10px;
  padding: 0;
  border: 1px solid var(--color-border-strong);
  border-radius: 2px;
  background: var(--color-surface-base);
  opacity: 0;
  cursor: nwse-resize;
  transition: opacity .12s;
}
.resize-corner::before { content: ''; position: absolute; inset: -4px; }
.canvas-node:hover .resize-corner,
.canvas-node.selected .resize-corner { opacity: .55; }
.resize-corner:focus-visible { opacity: 1; outline: 1px solid var(--color-primary); }

.node-settings { position: absolute; top: calc(100% + 12px); left: 50%; transform: translateX(-50%); width: 420px; max-width: 80vw; padding: 12px; display: grid; gap: 12px; border: 1px solid var(--color-border); border-radius: 12px; background: color-mix(in srgb, var(--color-surface-base) 94%, transparent); backdrop-filter: blur(18px); box-shadow: var(--shadow-soft); z-index: 10; }
.settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.settings-grid label { min-width: 0; display: grid; gap: 6px; font-size: 11px; color: var(--color-muted); }
.settings-grid .switch-field { display: flex; align-items: center; justify-content: space-between; gap: 10px; min-height: 32px; }
.settings-grid :deep(.el-select), .settings-grid :deep(.el-input-number) { width: 100%; }
.settings-grid .slider-field { grid-column: span 2; gap: 4px; }
.settings-grid .slider-field > span { display: flex; justify-content: space-between; align-items: center; }
.settings-grid .slider-field .param-val { font-style: normal; font-variant-numeric: tabular-nums; color: var(--color-text); font-size: 12px; }
.settings-grid :deep(.el-slider) { width: 100%; }
.generate-button { width: 100%; }

:deep(.node-handle) {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--color-muted);
}
:deep(.node-handle.vue-flow__handle-left) { left: -12px; }
:deep(.node-handle.vue-flow__handle-right) { right: -12px; }
:deep(.node-handle)::before { content: ''; position: absolute; inset: -13px; border-radius: 50%; }
:deep(.handle-icon) {
  pointer-events: none;
  opacity: 0;
  transform: translate(var(--handleX, 0px), var(--handleY, 0px));
  transition: opacity .12s ease-out, transform .12s ease-out;
}
:deep(.handle-icon.connected-icon) { display: none; }
:deep(.node-handle.connecting .handle-icon),
:deep(.node-handle.connected .handle-icon),
:deep(.node-handle.connected-node-active .handle-icon) { opacity: 1; }
:deep(.node-handle.connected .dashed-icon) { display: none; }
:deep(.node-handle.connected .connected-icon) { display: block; }
:deep(.node-handle:hover),
:deep(.node-handle.connecting),
:deep(.node-handle[data-connection-status="valid"]) { color: var(--color-primary); }
:deep(.node-handle[data-connection-status="invalid"]) { color: var(--color-danger); cursor: not-allowed; }
@media (prefers-reduced-motion: reduce) { :deep(.handle-icon) { transform: none; transition: none; } }
</style>
