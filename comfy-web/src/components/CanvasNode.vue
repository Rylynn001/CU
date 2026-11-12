<script setup lang="ts">
import { computed, inject, nextTick, onBeforeUnmount, watch } from 'vue'
import { Handle, Position, useVueFlow, type NodeProps } from '@vue-flow/core'
import { ElButton, ElInput, ElSelect, ElOption, ElInputNumber } from 'element-plus'
import SegmentedControl from './SegmentedControl.vue'
import { canvasActionsKey, type CanvasNodeData } from '../services/canvasGraph'

const props = defineProps<NodeProps<CanvasNodeData>>()
const actions = inject(canvasActionsKey)!
const { updateNodeInternals, viewport } = useVueFlow()
const generating = computed(() => props.type.includes('Generation'))
const isVideo = computed(() => props.type.includes('video'))
const isText = computed(() => props.type === 'remote-textNode')
const busy = computed(() => props.data.task?.state === 'pending' || actions.isSubmitting(props.id))
const models = computed(() => isVideo.value ? actions.videoModels.value : actions.imageModels.value)
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
      <div v-else-if="media.length" class="node-media nodrag nowheel">
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
    <template v-for="(handle, index) in data.handles" :key="handle.id">
      <Handle :id="handle.id" :type="handle.type" :position="handle.type === 'target' ? Position.Left : Position.Right" role="button" :title="handle.label" :aria-label="handle.label" :style="{ top: `${76 + index * 24}px` }" />
    </template>
    <section v-if="generating && selected" class="node-settings nodrag nopan nowheel" @keydown.stop @dblclick.stop>
      <ElInput v-model="data.prompt" type="textarea" :rows="3" :disabled="busy" placeholder="描述你想生成的内容" aria-label="生成提示词" />
      <div class="settings-grid">
        <label>模型<ElSelect v-model="data.model" :disabled="busy" placeholder="选择模型"><ElOption v-for="model in models" :key="model.id" :label="model.name" :value="String(model.id)" /></ElSelect></label>
        <label>画面比例<ElSelect v-model="data.ratio" :disabled="busy"><ElOption v-for="ratio in ['1:1', '16:9', '9:16', '4:3', '3:4']" :key="ratio" :label="ratio" :value="ratio" /></ElSelect></label>
        <template v-if="isVideo">
          <label>分辨率<ElSelect v-model="data.resolution" :disabled="busy"><ElOption v-for="resolution in ['480p', '720p', '1080p']" :key="resolution" :label="resolution" :value="resolution" /></ElSelect></label>
          <label>时长（秒）<ElInputNumber v-model="data.duration" :min="2" :max="15" :disabled="busy" /></label>
        </template>
        <template v-else>
          <label>清晰度<SegmentedControl v-model="data.quality" label="清晰度" :disabled="busy" :options="[{ value: 'low', label: '低' }, { value: 'medium', label: '中' }, { value: 'high', label: '高' }]" /></label>
          <label>生成数量<ElInputNumber v-model="data.n" :min="1" :max="4" :disabled="busy" /></label>
        </template>
      </div>
      <ElButton class="generate-button" :loading="busy" :disabled="!data.model" @click="actions.run(id)">{{ busy ? '正在生成' : isVideo ? '生成视频' : '生成图片' }}</ElButton>
    </section>
  </article>
</template>

<style scoped>
.canvas-node { position: relative; display: flex; flex-direction: column; width: 300px; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface-base); color: var(--color-text); box-shadow: var(--shadow-soft); }
.canvas-node.selected { border-color: var(--color-primary); }
.node-header { height: 43px; flex-shrink: 0; display: flex; align-items: center; gap: 8px; padding: 0 12px; border-bottom: 1px solid var(--color-border); }
.node-kind { color: var(--color-muted); font-size: 12px; }
.node-name { min-width: 0; flex: 1; padding: 4px; color: var(--color-text); background: transparent; border: 0; font-size: 13px; }
.node-actions { display: flex; gap: 2px; }
.node-actions button { border: 0; background: transparent; color: var(--color-muted); width: 24px; height: 26px; cursor: pointer; }
.node-actions button:hover { color: var(--color-text); background: var(--color-surface-soft); }
.node-actions button:disabled { opacity: .4; cursor: not-allowed; }
.node-body { padding: 8px; flex: 1; min-height: 0; overflow: auto; }
.resize-corner { position: absolute; right: 2px; bottom: 2px; width: 16px; height: 16px; border: 0; border-right: 2px solid var(--color-muted); border-bottom: 2px solid var(--color-muted); border-radius: 0 0 6px 0; background: transparent; cursor: nwse-resize; }
.node-empty { min-height: 160px; display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 10px; color: var(--color-muted); font-size: 13px; }
.node-empty small { color: var(--color-faint); font-size: 11px; }
.node-media { max-height: 360px; overflow: auto; display: grid; gap: 6px; }
.node-media img, .node-media video { display: block; width: 100%; max-height: 300px; object-fit: contain; border-radius: 6px; }
.media-missing { padding: 30px 10px; color: var(--color-muted); font-size: 12px; }
.node-footer { padding-top: 6px; display: flex; justify-content: flex-end; }
.node-error { color: var(--color-danger); font-size: 12px; padding: 8px; overflow-wrap: anywhere; }
.node-settings { position: absolute; top: calc(100% + 12px); left: 50%; transform: translateX(-50%); width: 410px; padding: 12px; display: grid; gap: 12px; border: 1px solid var(--color-border-strong); border-radius: var(--radius-md); background: var(--color-surface-base); box-shadow: var(--shadow-soft); }
.settings-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.settings-grid label { min-width: 0; display: grid; gap: 6px; font-size: 11px; color: var(--color-muted); }
.settings-grid :deep(.el-select), .settings-grid :deep(.el-input-number) { width: 100%; }
.generate-button { width: 100%; }
:deep(.vue-flow__handle) { width: 12px; height: 12px; background: var(--color-primary); border: 3px solid var(--color-surface-base); }
:deep(.vue-flow__handle:hover) { outline: 2px solid var(--color-muted); }
</style>
