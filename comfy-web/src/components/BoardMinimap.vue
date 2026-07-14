<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

interface Viewport { x: number; y: number; zoom: number }

const props = defineProps<{
  layers: any[]
  activeLayerId: string
  viewport: Viewport
  canvasWidth: number
  canvasHeight: number
  zoomPercent: number
}>()
const emit = defineEmits<{
  navigate: [point: { x: number; y: number }]
  selectLayer: [layerId: string]
  zoomOut: []
  zoomIn: []
  fit: []
}>()

const WIDTH = 188
const HEIGHT = 104
const PADDING = 7
const COLORS = ['#d9fff4', '#7eb7ff', '#b99cff', '#ffaf7a', '#ff86ad']
const switching = ref(false)
const enteringLayerId = ref<string | null>(null)
const leavingLayerId = ref<string | null>(null)
let switchTimer = 0
let drawFrame = 0
const layerCanvases = new Map<string, HTMLCanvasElement>()

watch(() => props.activeLayerId, (next, previous) => {
  enteringLayerId.value = next
  leavingLayerId.value = previous
  switching.value = true
  window.clearTimeout(switchTimer)
  switchTimer = window.setTimeout(() => {
    switching.value = false
    enteringLayerId.value = null
    leavingLayerId.value = null
  }, 520)
})
onBeforeUnmount(() => {
  window.clearTimeout(switchTimer)
  window.cancelAnimationFrame(drawFrame)
  layerCanvases.clear()
})

function layerItems(layer: any) {
  return [...layer.rootSteps, ...layer.groups, ...layer.annotations].map((item: any) => ({
    id: item.id,
    x: item.x,
    y: item.y,
    width: item.kind === 'text' ? 210 : item.kind === 'brush' ? item.width : 286,
    height: item.kind === 'text' ? 76 : item.kind === 'brush' ? item.height : 164,
    color: item.minimapColor ?? item.color,
  }))
}

const mapModel = computed(() => {
  const activeIndex = props.layers.findIndex(layer => layer.id === props.activeLayerId)
  const mapLayers = props.layers.map((layer, index) => ({ layer, index, depth: activeIndex - index, items: layerItems(layer) }))
  const items = mapLayers.flatMap(item => item.items)
  const minX = Math.min(0, ...items.map(item => item.x)) - 80
  const minY = Math.min(0, ...items.map(item => item.y)) - 80
  const maxX = Math.max(props.canvasWidth, ...items.map(item => item.x + item.width)) + 80
  const maxY = Math.max(props.canvasHeight, ...items.map(item => item.y + item.height)) + 80
  const scale = Math.min((WIDTH - PADDING * 2) / Math.max(1, maxX - minX), (HEIGHT - PADDING * 2) / Math.max(1, maxY - minY))
  const offsetX = (WIDTH - (maxX - minX) * scale) / 2
  const offsetY = (HEIGHT - (maxY - minY) * scale) / 2
  const x = (value: number) => offsetX + (value - minX) * scale
  const y = (value: number) => offsetY + (value - minY) * scale
  return {
    bounds: { minX, minY, scale, offsetX, offsetY },
    layers: mapLayers.map(entry => ({
      ...entry,
      color: COLORS[entry.index % COLORS.length],
      active: entry.layer.id === props.activeLayerId,
      blur: entry.depth < 0 ? 4.5 : [0, 1.2, 2.2, 3.2, 4][Math.min(4, Math.max(0, entry.depth))],
      opacity: entry.layer.visible || entry.layer.id === props.activeLayerId
        ? (entry.depth < 0 ? .06 : [.72, .3, .18, .1, .055][Math.min(4, Math.max(0, entry.depth))])
        : .045,
      scale: entry.depth < 0 ? .78 : [1, .92, .86, .8, .75][Math.min(4, Math.max(0, entry.depth))],
      shapes: entry.items.map(item => {
        const width = entry.layer.id === props.activeLayerId ? 8 : 7
        const height = entry.layer.id === props.activeLayerId ? 5 : 4.5
        const centerX = x(item.x + item.width / 2)
        const centerY = y(item.y + item.height / 2)
        return { id: item.id, x: centerX - width / 2, y: centerY - height / 2, width, height, color: item.color ?? COLORS[entry.index % COLORS.length] }
      }),
    })),
  }
})

const viewModel = computed(() => {
  const zoom = Math.max(.001, props.viewport.zoom)
  const view = {
    x: -props.viewport.x / zoom,
    y: -props.viewport.y / zoom,
    width: props.canvasWidth / zoom,
    height: props.canvasHeight / zoom,
  }
  const { minX, minY, scale, offsetX, offsetY } = mapModel.value.bounds
  return {
    x: offsetX + (view.x - minX) * scale,
    y: offsetY + (view.y - minY) * scale,
    width: Math.max(4, view.width * scale),
    height: Math.max(4, view.height * scale),
  }
})

function drawLayer(layer: (typeof mapModel.value.layers)[number]) {
  const target = layerCanvases.get(layer.layer.id)
  if (!target) return
  const dpr = Math.min(1.5, window.devicePixelRatio || 1)
  const width = Math.round(WIDTH * dpr)
  const height = Math.round(HEIGHT * dpr)
  if (target.width !== width || target.height !== height) {
    target.width = width
    target.height = height
  }
  const context = target.getContext('2d')
  if (!context) return
  context.setTransform(dpr, 0, 0, dpr, 0, 0)
  context.clearRect(0, 0, WIDTH, HEIGHT)
  context.globalAlpha = .72
  layer.shapes.forEach(shape => {
    context.fillStyle = shape.color
    context.beginPath()
    context.roundRect(shape.x, shape.y, shape.width, shape.height, 1.5)
    context.fill()
  })
}

function scheduleDraw() {
  window.cancelAnimationFrame(drawFrame)
  drawFrame = window.requestAnimationFrame(() => mapModel.value.layers.forEach(drawLayer))
}

function setLayerCanvas(layerId: string, element: any) {
  if (element instanceof HTMLCanvasElement) layerCanvases.set(layerId, element)
  else layerCanvases.delete(layerId)
  scheduleDraw()
}

watch(mapModel, scheduleDraw, { flush: 'post' })

function navigate(event: MouseEvent) {
  const rect = (event.currentTarget as HTMLElement).getBoundingClientRect()
  const svgX = (event.clientX - rect.left) * WIDTH / rect.width
  const svgY = (event.clientY - rect.top) * HEIGHT / rect.height
  const { minX, minY, scale, offsetX, offsetY } = mapModel.value.bounds
  emit('navigate', { x: minX + (svgX - offsetX) / scale, y: minY + (svgY - offsetY) / scale })
}
</script>

<template>
  <aside class="board-minimap" @pointerdown.stop>
    <header><span>导航图</span><div><button v-for="(layer, index) in layers" :key="layer.id" :class="{ active: layer.id === activeLayerId, hidden: !layer.visible }" :style="{ '--layer-color': COLORS[index % COLORS.length] }" :title="`${layer.name}${layer.visible ? '' : ' · 已隐藏'}`" @click="emit('selectLayer', layer.id)">{{ index + 1 }}</button></div></header>
    <div class="map-stage" :class="{ switching }" role="img" aria-label="画布节点导航图" @click="navigate">
      <canvas v-for="layer in mapModel.layers" :key="layer.layer.id" :ref="element => setLayerCanvas(layer.layer.id, element)" class="map-layer" :class="{ active: layer.active, entering: layer.layer.id === enteringLayerId, leaving: layer.layer.id === leavingLayerId }" :style="{ '--layer-opacity': layer.opacity, '--layer-blur': `${layer.blur}px`, '--layer-scale': layer.scale }" />
      <svg :viewBox="`0 0 ${WIDTH} ${HEIGHT}`" aria-hidden="true">
        <rect width="188" height="104" class="map-background" />
        <text x="94" y="64" text-anchor="middle" class="layer-count">{{ layers.length }}</text>
        <text x="94" y="78" text-anchor="middle" class="layer-count-label">LAYERS</text>
        <rect :x="viewModel.x" :y="viewModel.y" :width="viewModel.width" :height="viewModel.height" class="viewport-box" />
      </svg>
    </div>
    <footer><button title="缩小" @click="emit('zoomOut')">−</button><span>{{ zoomPercent }}%</span><button title="放大" @click="emit('zoomIn')">＋</button><button title="适应画布" @click="emit('fit')">◎</button></footer>
  </aside>
</template>

<style scoped>
.board-minimap{position:absolute;z-index:7;left:16px;bottom:var(--board-bottom-gap,18px);width:188px;padding:7px;border:1px solid rgba(255,255,255,.09);border-radius:11px;background:rgba(14,14,14,.86);box-shadow:0 12px 28px rgba(0,0,0,.25);backdrop-filter:blur(14px);user-select:none}
.board-minimap header{height:20px;display:flex;align-items:flex-start;justify-content:space-between;color:rgba(255,255,255,.42);font-size:9px}.board-minimap header div{display:flex;gap:2px}.board-minimap header button{width:14px;height:14px;padding:0;border:1px solid transparent;border-radius:50%;background:color-mix(in srgb,var(--layer-color) 24%,#151515);color:var(--layer-color);font-size:7px;line-height:12px;cursor:pointer}.board-minimap header button.active{border-color:var(--layer-color);box-shadow:0 0 0 2px rgba(255,255,255,.06)}.board-minimap header button.hidden{opacity:.28}
.map-stage{position:relative;height:104px;overflow:hidden;border-radius:7px;background:#0a0a0a;cursor:crosshair}.board-minimap svg,.map-layer{position:absolute;inset:0;width:100%;height:104px;display:block;pointer-events:none}.map-background{fill:transparent}.layer-count{fill:rgba(255,255,255,.045);font-size:54px;font-weight:700;letter-spacing:-4px}.layer-count-label{fill:rgba(255,255,255,.055);font-size:7px;letter-spacing:3px}.map-layer{opacity:var(--layer-opacity);filter:blur(var(--layer-blur));transform:scale(var(--layer-scale));transform-origin:center;transition:opacity .48s ease,filter .48s ease,transform .48s cubic-bezier(.18,.8,.24,1)}.map-layer.entering{animation:layer-arrive .5s cubic-bezier(.18,.8,.24,1) both}.map-layer.leaving{animation:layer-retire .5s cubic-bezier(.18,.8,.24,1) both}.viewport-box{fill:rgba(255,255,255,.025);stroke:rgba(255,255,255,.56);stroke-width:.8;vector-effect:non-scaling-stroke;transition:opacity .35s ease}
.board-minimap footer{height:29px;margin-top:5px;padding-top:5px;display:flex;align-items:center;border-top:1px solid rgba(255,255,255,.07)}.board-minimap footer button{width:27px;height:24px;padding:0;border:0;border-radius:5px;background:transparent;color:rgba(255,255,255,.48);cursor:pointer}.board-minimap footer button:hover{background:rgba(255,255,255,.07);color:#fff}.board-minimap footer span{width:48px;color:rgba(255,255,255,.42);font-size:9px;text-align:center}.board-minimap footer button:last-child{margin-left:auto}
@keyframes layer-arrive{0%{opacity:.2;filter:blur(5px);transform:scale(1.28)}100%{opacity:var(--layer-opacity);filter:blur(var(--layer-blur));transform:scale(var(--layer-scale))}}
@keyframes layer-retire{0%{opacity:.78;filter:blur(0);transform:scale(1)}100%{opacity:var(--layer-opacity);filter:blur(var(--layer-blur));transform:scale(var(--layer-scale))}}
@media(max-width:820px){.board-minimap{left:10px;width:154px}.board-minimap svg{height:88px}}
@media(max-width:520px){.board-minimap{bottom:calc(176px + var(--board-bottom-gap,18px));width:138px}.map-stage,.board-minimap svg{height:72px}.board-minimap footer span{width:38px}}
@media(prefers-reduced-motion:reduce){.map-layer{animation:none!important;transition:none!important}}
</style>
