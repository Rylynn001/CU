<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { cancelLayerRender, enqueueLayerRender } from '../utils/layerRenderQueue'

interface Viewport { x: number; y: number; zoom: number }
interface CachedViewport extends Viewport { padding: number }

const props = defineProps<{
  layer: any
  links: any[]
  depth: number
  visible: boolean
  priority: boolean
  transitioning: boolean
  fadeOut: boolean
  outgoingScale: number
  renderLevel: 'full' | 'no-text' | 'silhouette'
  blurEnabled: boolean
  viewport: Viewport
  width: number
  height: number
  renderRevision: string
  moving: boolean
  dpr: number
}>()

const BLUR_BY_DEPTH = [0, 10, 20, 30, 40]
const OPACITY_BY_DEPTH = [1, .26, .12, .06, .03]
const SATURATION_BY_DEPTH = [1, .72, .5, .32, .18]
const OVERSCAN = .2
const canvas = ref<HTMLCanvasElement>()
const snapshot = ref<CachedViewport>({ x: 0, y: 0, zoom: 1, padding: 0 })
const ready = ref(false)
let renderToken = 0
let renderTimer = 0
let downscaleToken = 0
let renderedDpr = 0
let acquiredUrls = new Set<string>()

interface BitmapEntry {
  refs: number
  bitmap?: ImageBitmap
  promise: Promise<ImageBitmap | undefined>
}
const bitmapCache = ((globalThis as any).__productionLayerBitmaps ??= new Map<string, BitmapEntry>()) as Map<string, BitmapEntry>

function acquireBitmap(url: string) {
  let entry = bitmapCache.get(url)
  if (!entry) {
    entry = {
      refs: 0,
      promise: fetch(url).then(response => response.ok ? response.blob() : undefined).then(blob => blob ? createImageBitmap(blob) : undefined).then(bitmap => {
        const current = bitmapCache.get(url)
        if (!current) { bitmap?.close(); return undefined }
        current.bitmap = bitmap
        if (current.refs <= 0) { bitmap?.close(); bitmapCache.delete(url); return undefined }
        if (!bitmap) bitmapCache.delete(url)
        return bitmap
      }).catch(() => undefined),
    }
    bitmapCache.set(url, entry)
  }
  entry.refs++
  return entry.bitmap ? Promise.resolve(entry.bitmap) : entry.promise
}

function releaseBitmaps(urls: Set<string>) {
  urls.forEach(url => {
    const entry = bitmapCache.get(url)
    if (!entry) return
    entry.refs--
    if (entry.refs <= 0 && entry.bitmap) { entry.bitmap.close(); bitmapCache.delete(url) }
  })
}

function activeVersion(card: any) {
  return card?.batches?.flatMap((batch: any) => batch.versions).find((version: any) => version.id === card.activeVersionId)
}

function groupVersion(group: any) {
  const output = group.outputs.find((item: any) => item.id === group.defaultOutputId) ?? group.outputs[0]
  const cardId = output?.cardIds?.[0] ?? output?.cardId
  const card = cardId ? group.children.find((item: any) => item.id === cardId) : undefined
  return activeVersion(card)
}

function createSurface(width: number, height: number) {
  if (typeof OffscreenCanvas !== 'undefined') return new OffscreenCanvas(width, height)
  const fallback = document.createElement('canvas')
  fallback.width = width
  fallback.height = height
  return fallback
}

function roundedRect(context: any, x: number, y: number, width: number, height: number, radius: number) {
  context.beginPath()
  context.roundRect(x, y, width, height, radius)
}

function drawCover(context: any, bitmap: ImageBitmap, x: number, y: number, width: number, height: number) {
  const scale = Math.max(width / bitmap.width, height / bitmap.height)
  const sourceWidth = width / scale
  const sourceHeight = height / scale
  const sourceX = (bitmap.width - sourceWidth) / 2
  const sourceY = (bitmap.height - sourceHeight) / 2
  context.save()
  roundedRect(context, x, y, width, height, 10)
  context.clip()
  context.drawImage(bitmap, sourceX, sourceY, sourceWidth, sourceHeight, x, y, width, height)
  context.restore()
}

async function renderBackdrop() {
  if (props.moving || !canvas.value || props.width <= 0 || props.height <= 0) return
  downscaleToken++
  const token = ++renderToken
  const dpr = Math.max(.25, props.dpr)
  const padding = Math.round(Math.max(props.width, props.height) * OVERSCAN)
  const cssWidth = props.width + padding * 2
  const cssHeight = props.height + padding * 2
  const pixelWidth = Math.max(1, Math.round(cssWidth * dpr))
  const pixelHeight = Math.max(1, Math.round(cssHeight * dpr))
  const source = createSurface(pixelWidth, pixelHeight)
  const sourceContext = source.getContext('2d') as any
  if (!sourceContext) return
  sourceContext.scale(dpr, dpr)
  sourceContext.lineCap = 'round'
  sourceContext.lineJoin = 'round'

  const toX = (x: number) => x * props.viewport.zoom + props.viewport.x + padding
  const toY = (y: number) => y * props.viewport.zoom + props.viewport.y + padding
  const zoom = props.viewport.zoom
  const intersectsCache = (x: number, y: number, width: number, height: number) => {
    const left = toX(x)
    const top = toY(y)
    return left + width * zoom >= 0 && top + height * zoom >= 0 && left <= cssWidth && top <= cssHeight
  }

  props.links.forEach(link => {
    const gradient = sourceContext.createLinearGradient(toX(link.p0.x), toY(link.p0.y), toX(link.p2.x), toY(link.p2.y))
    gradient.addColorStop(0, link.sourceColor)
    gradient.addColorStop(1, link.targetColor)
    sourceContext.beginPath()
    sourceContext.moveTo(toX(link.p0.x), toY(link.p0.y))
    sourceContext.quadraticCurveTo(toX(link.p1.x), toY(link.p1.y), toX(link.p2.x), toY(link.p2.y))
    sourceContext.strokeStyle = 'rgba(0,0,0,.82)'
    sourceContext.lineWidth = 8
    sourceContext.stroke()
    sourceContext.strokeStyle = gradient
    sourceContext.lineWidth = 4.5
    sourceContext.stroke()
  })

  const cards = [...props.layer.rootSteps, ...props.layer.groups].filter((item: any) => intersectsCache(item.x, item.y, 286, 164))
  const urls = new Set<string>()
  const cardData = cards.map((item: any) => {
    const version = props.renderLevel === 'silhouette' ? undefined : item.kind === 'group' ? groupVersion(item) : activeVersion(item)
    if (version?.type === 'image' && version.src) urls.add(version.src)
    return { item, version }
  })
  const bitmaps = new Map<string, ImageBitmap>()
  await Promise.all([...urls].map(async url => {
    const bitmap = await acquireBitmap(url)
    if (bitmap) bitmaps.set(url, bitmap)
  }))
  if (token !== renderToken) { releaseBitmaps(urls); return }
  releaseBitmaps(acquiredUrls)
  acquiredUrls = urls

  cardData.forEach(({ item, version }) => {
    const x = toX(item.x)
    const y = toY(item.y)
    const width = 286 * zoom
    const height = 164 * zoom
    sourceContext.fillStyle = props.renderLevel === 'silhouette' ? (item.minimapColor ?? item.color ?? '#303030') : item.kind === 'group' ? '#121212' : '#0b0b0b'
    roundedRect(sourceContext, x, y, width, height, 11 * zoom)
    sourceContext.fill()
    const bitmap = version?.src ? bitmaps.get(version.src) : undefined
    if (bitmap) drawCover(sourceContext, bitmap, x, y, width, height)
    sourceContext.strokeStyle = 'rgba(255,255,255,.2)'
    sourceContext.lineWidth = Math.max(1, zoom)
    roundedRect(sourceContext, x, y, width, height, 11 * zoom)
    sourceContext.stroke()
    if (props.renderLevel === 'full') {
      sourceContext.fillStyle = 'rgba(255,255,255,.72)'
      sourceContext.font = `${Math.max(8, 10 * zoom)}px sans-serif`
      sourceContext.fillText(item.title ?? '', x + 9 * zoom, y + 19 * zoom, width - 18 * zoom)
    }
  })

  props.layer.annotations.filter((annotation: any) => intersectsCache(annotation.x, annotation.y, annotation.kind === 'text' ? 210 : annotation.width, annotation.kind === 'text' ? 76 : annotation.height)).forEach((annotation: any) => {
    const x = toX(annotation.x)
    const y = toY(annotation.y)
    if (annotation.kind === 'text') {
      sourceContext.fillStyle = 'rgba(255,255,255,.72)'
      sourceContext.font = `${Math.max(10, 14 * zoom)}px sans-serif`
      sourceContext.fillText(annotation.text, x, y + 18 * zoom, 210 * zoom)
      return
    }
    sourceContext.save()
    sourceContext.translate(x, y)
    sourceContext.scale(zoom, zoom)
    sourceContext.strokeStyle = 'rgba(255,255,255,.7)'
    sourceContext.lineWidth = 2
    sourceContext.stroke(new Path2D(annotation.path))
    sourceContext.restore()
  })

  let output = source
  if (props.depth > 0) {
    const blurred = createSurface(pixelWidth, pixelHeight)
    const blurContext = blurred.getContext('2d') as any
    if (!blurContext) return
    const blur = props.blurEnabled ? BLUR_BY_DEPTH[props.depth] * dpr : 0
    const saturation = SATURATION_BY_DEPTH[props.depth] ?? SATURATION_BY_DEPTH[4]
    blurContext.filter = `blur(${blur}px) saturate(${saturation})`
    blurContext.drawImage(source as any, 0, 0)
    blurContext.filter = 'none'
    output = blurred
  }
  const nextFrame = typeof createImageBitmap === 'function' ? await createImageBitmap(output as any) : undefined
  if (token !== renderToken) { nextFrame?.close(); return }
  const target = canvas.value
  target.width = pixelWidth
  target.height = pixelHeight
  target.style.width = `${cssWidth}px`
  target.style.height = `${cssHeight}px`
  target.style.left = `${-padding}px`
  target.style.top = `${-padding}px`
  const targetContext = target.getContext('2d')
  targetContext?.clearRect(0, 0, pixelWidth, pixelHeight)
  if (nextFrame) targetContext?.drawImage(nextFrame, 0, 0)
  else targetContext?.drawImage(output as HTMLCanvasElement, 0, 0)
  nextFrame?.close()
  snapshot.value = { ...props.viewport, padding }
  renderedDpr = dpr
  ready.value = true
}

async function downscaleHiddenCache(nextDpr: number) {
  const target = canvas.value
  if (!target || !ready.value || !renderedDpr || shouldMaintainCache() || nextDpr >= renderedDpr) return
  const token = renderToken
  const scaleToken = ++downscaleToken
  const ratio = Math.max(.25, nextDpr) / renderedDpr
  const bitmap = typeof createImageBitmap === 'function' ? await createImageBitmap(target) : undefined
  if (!bitmap || token !== renderToken || scaleToken !== downscaleToken || shouldMaintainCache()) { bitmap?.close(); return }
  target.width = Math.max(1, Math.round(target.width * ratio))
  target.height = Math.max(1, Math.round(target.height * ratio))
  target.getContext('2d')?.drawImage(bitmap, 0, 0, target.width, target.height)
  bitmap.close()
  renderedDpr = Math.max(.25, nextDpr)
}

function scheduleRender(immediate = false) {
  window.clearTimeout(renderTimer)
  const delay = immediate ? Math.max(0, (props.depth - 1) * 28) : 55 + props.depth * 35
  renderTimer = window.setTimeout(queueRender, delay)
}

function scheduleMotionRefresh() {
  window.clearTimeout(renderTimer)
  renderTimer = window.setTimeout(queueRender, 420 + props.depth * 30)
}

function queueRender() {
  enqueueLayerRender({
    key: props.layer.id,
    priority: props.transitioning ? 0 : props.priority ? 1 : props.depth + 2,
    run: renderBackdrop,
  })
}

function cacheCoversViewport() {
  if (!ready.value) return false
  const previous = snapshot.value
  const ratio = props.viewport.zoom / previous.zoom
  if (ratio < .8 || ratio > 1.25) return false
  const dx = props.viewport.x - previous.x * ratio
  const dy = props.viewport.y - previous.y * ratio
  const left = -previous.padding * ratio + dx
  const top = -previous.padding * ratio + dy
  const cachedWidth = (props.width + previous.padding * 2) * ratio
  const cachedHeight = (props.height + previous.padding * 2) * ratio
  return left <= 0 && top <= 0 && left + cachedWidth >= props.width && top + cachedHeight >= props.height
}

function shouldMaintainCache() {
  return props.visible || props.priority || props.transitioning
}

function cacheNeedsRefresh() {
  return !cacheCoversViewport() || renderedDpr + .04 < Math.max(.25, props.dpr)
}

const transform = computed(() => {
  if (!ready.value) return 'none'
  const previous = snapshot.value
  const ratio = props.viewport.zoom / previous.zoom
  const dx = props.viewport.x - previous.x * ratio
  const dy = props.viewport.y - previous.y * ratio
  const tx = previous.padding * (1 - ratio) + dx
  const ty = previous.padding * (1 - ratio) + dy
  return `matrix(${ratio},0,0,${ratio},${tx},${ty})`
})

const opacity = computed(() => {
  if (props.transitioning) return props.fadeOut ? 0 : 1
  if (!props.visible) return 0
  const base = OPACITY_BY_DEPTH[props.depth] ?? OPACITY_BY_DEPTH[4]
  return base
})

watch(() => [props.renderRevision, props.width, props.height, props.depth, props.blurEnabled, props.renderLevel], () => {
  if (!ready.value || shouldMaintainCache()) scheduleRender()
}, { immediate: true })
watch(() => props.dpr, dpr => {
  if (!ready.value || shouldMaintainCache()) scheduleRender()
  else if (dpr < renderedDpr - .04) void downscaleHiddenCache(dpr)
})
watch(() => [props.visible, props.priority, props.transitioning], () => {
  if (shouldMaintainCache() && cacheNeedsRefresh()) scheduleRender(true)
})
watch(() => props.moving, moving => { if (!moving && shouldMaintainCache() && cacheNeedsRefresh()) scheduleMotionRefresh() })
watch(() => props.viewport, () => { if (!props.moving && shouldMaintainCache() && cacheNeedsRefresh()) scheduleMotionRefresh() }, { deep: true })

onBeforeUnmount(() => {
  renderToken++
  downscaleToken++
  window.clearTimeout(renderTimer)
  cancelLayerRender(props.layer.id)
  releaseBitmaps(acquiredUrls)
})
</script>

<template>
  <div class="layer-backdrop" :class="{ transitioning }" :style="{ opacity, transform: transitioning ? `scale(${fadeOut ? outgoingScale : 1})` : 'none' }" aria-hidden="true">
    <canvas ref="canvas" :style="{ transform }" />
  </div>
</template>

<style scoped>
.layer-backdrop{position:absolute;z-index:1;inset:0;overflow:hidden;pointer-events:none;contain:strict;transform-origin:center}.layer-backdrop.transitioning{z-index:3;will-change:opacity,transform;transition:opacity .22s cubic-bezier(.2,.75,.25,1),transform .22s cubic-bezier(.2,.75,.25,1)}.layer-backdrop canvas{position:absolute;transform-origin:0 0;will-change:transform;image-rendering:auto}
@media(prefers-reduced-motion:reduce){.layer-backdrop.transitioning{transition:none}}
</style>
