<script setup lang="ts">
import { computed, inject, nextTick, onBeforeUnmount, watch } from 'vue'
import { Handle, Position, useVueFlow, type NodeProps } from '@vue-flow/core'
import { CircleDashed, CircleDot } from '@lucide/vue'
import { ElButton, ElInput, ElSelect, ElOption, ElInputNumber, ElSwitch } from 'element-plus'
import { canvasActionsKey, type CanvasNodeData } from '../services/canvasGraph'

const props = defineProps<NodeProps<CanvasNodeData>>()
const actions = inject(canvasActionsKey)!
const { updateNodeInternals, viewport } = useVueFlow()
const generating = computed(() => props.type.includes('Generation'))
const isVideo = computed(() => props.type.includes('video'))
const isText = computed(() => props.type === 'remote-textNode')
const busy = computed(() => props.data.task?.state === 'pending' || actions.isSubmitting(props.id))
const models = computed(() => isVideo.value ? actions.videoModels.value : actions.imageModels.value)
const selectedModel = computed(() => models.value.find(model => String(model.id) === String(props.data.model)))
const parameterFields = computed(() => selectedModel.value?.parameters?.fields ?? [])
const media = computed(() => Object.values(props.data.outputs).flatMap(output => typeof output.value === 'string' ? [] : output.value.assetIds.map(id => actions.assets.value[id] ?? { id, url: '', type: isVideo.value ? 'video' : 'image' })))
async function refreshBounds() { await nextTick(); updateNodeInternals([props.id]) }
watch(media, refreshBounds)
let stopResize: (() => void) | undefined
function startResize(event: PointerEvent) {
  if (event.button !== 0) return
  const element = (event.currentTarget as HTMLElement).closest('article')!
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
onBeforeUnmount(() => stopResize?.())
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
  // 沿用 Toonflow：按端口尺寸还原缩放，朝光标偏移，最大半径为 6 像素。
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
</script>

<template>
  <article class="canvas-node" :class="{ selected, generating: busy }" :style="{ width: data.width ? `${data.width}px` : undefined, height: data.height ? `${data.height}px` : undefined }">
    <header class="node-header">
      <span class="node-kind">{{ isText ? '文' : isVideo ? '影' : '图' }}</span>
      <input v-model="data.label" class="node-name nodrag" aria-label="节点名称" />
      <div class="node-actions nodrag">
        <button title="创建副本" aria-label="创建副本" @click="actions.duplicate(id)">⧉</button>
        <button title="移除节点" aria-label="移除节点" :disabled="busy" @click="actions.remove(id)">×</button>
      </div>
    </header>
    <div class="node-body">
      <ElInput v-if="isText" class="nodrag nowheel" type="textarea" :rows="5" :model-value="data.prompt" placeholder="输入文本，连到生成节点作为提示词" @update:model-value="setText" />
      <div v-else-if="media.length" class="node-media nowheel">
        <template v-for="asset in media" :key="asset.id">
          <video v-if="asset.url && asset.type === 'video'" :src="asset.url" controls preload="metadata" @loadedmetadata="refreshBounds" />
          <img v-else-if="asset.url" :src="asset.url" alt="节点图片" draggable="false" @load="refreshBounds" />
          <div v-else class="media-missing">资产 {{ asset.id }} 暂不可用</div>
        </template>
      </div>
      <div v-else class="node-empty">
        <span>{{ busy ? '生成中…' : generating ? '创作从这里开始' : '从资产库选择素材' }}</span>
        <small>{{ generating ? '连接参考素材，或直接输入描述' : '素材沿用现有资产库' }}</small>
      </div>
      <p v-if="data.task?.error" class="node-error" role="alert">{{ data.task.error }}</p>
      <div v-if="!generating && !isText" class="nodrag node-footer">
        <ElButton size="small" @click="actions.pick(id)">选择素材</ElButton>
      </div>
    </div>
    <button v-if="selected" class="resize-corner nodrag nopan" title="拖动调整节点大小" aria-label="调整节点大小" @pointerdown.stop.prevent="startResize" />
    <template v-for="handle in data.handles" :key="handle.id">
      <Handle :id="handle.id" :type="handle.type" :position="handle.type === 'target' ? Position.Left : Position.Right" class="node-handle" role="button" :title="handle.label" :aria-label="handle.label" :style="{ top: handleTop(handle) }" @pointermove="moveHandle" @pointerleave="resetHandle" @pointercancel="resetHandle">
        <CircleDot class="handle-icon connected-icon" :size="18" aria-hidden="true" />
        <CircleDashed class="handle-icon dashed-icon" :size="18" aria-hidden="true" />
      </Handle>
    </template>
    <section v-if="generating && selected" class="node-settings nodrag nopan nowheel" @keydown.stop @dblclick.stop>
      <ElInput v-model="data.prompt" type="textarea" :rows="3" :disabled="busy" placeholder="描述你想生成的内容" aria-label="生成提示词" />
      <div class="settings-grid">
        <label>模型<ElSelect :model-value="data.model" :disabled="busy" placeholder="选择模型" @update:model-value="setModel"><ElOption v-for="model in models" :key="model.id" :label="model.name" :value="String(model.id)" /></ElSelect></label>
        <template v-for="field in parameterFields" :key="field.key">
          <label v-if="field.type === 'select' && field.options?.length">{{ field.label }}<ElSelect :model-value="parameterValue(field.key, field.default)" :disabled="busy" @update:model-value="setParameter(field.key, $event)"><ElOption v-for="option in field.options" :key="String(option)" :label="String(option)" :value="option" /></ElSelect></label>
          <label v-else-if="field.type === 'number'">{{ field.label }}<ElInputNumber :model-value="Number(parameterValue(field.key, field.default))" :min="field.min" :max="field.max" :step="field.step" :disabled="busy" @update:model-value="setParameter(field.key, $event ?? field.default)" /></label>
          <label v-else-if="field.type === 'boolean'" class="switch-field">{{ field.label }}<ElSwitch :model-value="Boolean(parameterValue(field.key, field.default))" :disabled="busy" @update:model-value="setParameter(field.key, $event)" /></label>
          <label v-else>{{ field.label }}<ElInput :model-value="String(parameterValue(field.key, field.default))" :disabled="busy" @update:model-value="setParameter(field.key, $event)" /></label>
        </template>
      </div>
      <ElButton class="generate-button" :loading="busy" :disabled="!data.model" @click="actions.run(id)">{{ busy ? '正在生成' : isVideo ? '生成视频' : '生成图片' }}</ElButton>
    </section>
  </article>
</template>

<style scoped>
.canvas-node { position: relative; width: 220px; color: var(--color-text); text-align: left; }
.canvas-node.selected { z-index: 2; }
.node-header { display: flex; align-items: center; gap: 6px; padding: 0 4px 8px; font-size: 14px; line-height: 20px; }
.node-kind { display: grid; width: 16px; height: 16px; place-items: center; color: var(--color-muted); font-size: 10px; }
.node-name { min-width: 0; flex: 1; padding: 4px; color: var(--color-text); background: transparent; border: 0; font-size: 13px; }
.node-actions { display: flex; gap: 2px; }
.node-actions button { visibility: hidden; border: 0; background: transparent; color: var(--color-muted); width: 24px; height: 26px; cursor: pointer; border-radius: 5px; }.canvas-node:hover .node-actions button, .canvas-node.selected .node-actions button { visibility: visible; }
.node-actions button:hover { color: var(--color-text); background: var(--color-surface-soft); }
.node-actions button:disabled { opacity: .4; cursor: not-allowed; }
.node-body { position: relative; padding: 8px; min-height: 100px; overflow: auto; border: 1px solid var(--color-border); border-radius: 4px; background: var(--color-surface-base); }.canvas-node.selected .node-body { border-color: color-mix(in srgb, var(--color-primary) 50%, var(--color-border)); }
.resize-corner { position: absolute; right: 2px; bottom: 2px; width: 4px; height: 4px; padding: 0; border: 1px solid var(--color-border-strong); border-radius: 1px; background: var(--color-surface-base); opacity: .55; cursor: nwse-resize; }.resize-corner::before { content: ''; position: absolute; inset: -4px; }
.node-empty { min-height: 160px; display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 10px; color: var(--color-muted); font-size: 13px; }
.node-empty small { color: var(--color-faint); font-size: 11px; }
.node-media { max-height: 360px; overflow: auto; display: grid; gap: 6px; }
.node-media img, .node-media video { display: block; width: 100%; max-height: 300px; object-fit: contain; border-radius: 6px; }.node-media img { pointer-events: none; }
.media-missing { padding: 30px 10px; color: var(--color-muted); font-size: 12px; }
.node-footer { padding-top: 6px; display: flex; justify-content: flex-end; }
.node-error { color: var(--color-danger); font-size: 12px; padding: 8px; overflow-wrap: anywhere; }
.node-settings { position: absolute; top: calc(100% + 12px); left: 50%; transform: translateX(-50%); width: 420px; max-width: 80vw; padding: 12px; display: grid; gap: 12px; border: 1px solid var(--color-border); border-radius: 12px; background: color-mix(in srgb, var(--color-surface-base) 94%, transparent); backdrop-filter: blur(18px); box-shadow: var(--shadow-soft); }
.settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.settings-grid label { min-width: 0; display: grid; gap: 6px; font-size: 11px; color: var(--color-muted); }
.settings-grid .switch-field { display: flex; align-items: center; justify-content: space-between; gap: 10px; min-height: 32px; }
.settings-grid :deep(.el-select), .settings-grid :deep(.el-input-number) { width: 100%; }
.generate-button { width: 100%; }
:deep(.node-handle) { display: flex; align-items: center; justify-content: center; width: 18px; height: 18px; border: 0; border-radius: 0; background: transparent; color: var(--color-muted); }
:deep(.node-handle.vue-flow__handle-left) { left: -12px; }
:deep(.node-handle.vue-flow__handle-right) { right: -12px; }
:deep(.node-handle)::before { content: ''; position: absolute; inset: -13px; border-radius: 50%; }
:deep(.handle-icon) { pointer-events: none; opacity: .68; transform: translate(var(--handleX, 0px), var(--handleY, 0px)); transition: opacity .12s ease-out, transform .12s ease-out; }
:deep(.handle-icon.connected-icon) { display: none; }
:deep(.canvas-node:hover .handle-icon), :deep(.node-handle.connecting .handle-icon), :deep(.node-handle.connected .handle-icon) { opacity: 1; }
:deep(.node-handle.connected .dashed-icon) { display: none; }
:deep(.node-handle.connected .connected-icon) { display: block; }
:deep(.node-handle:hover) { color: var(--color-primary); }
@media (prefers-reduced-motion: reduce) { :deep(.handle-icon) { transform: none; transition: none; } }
</style>
