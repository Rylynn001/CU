<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'

const TWO_PI = Math.PI * 2

interface Dot {
  ax: number
  ay: number
  sx: number
  sy: number
  vx: number
  vy: number
  x: number
  y: number
}

const props = withDefaults(defineProps<{
  dotRadius?: number
  dotSpacing?: number
  cursorRadius?: number
  cursorForce?: number
  bulgeOnly?: boolean
  bulgeStrength?: number
  glowRadius?: number
  sparkle?: boolean
  waveAmplitude?: number
  gradientFrom?: string
  gradientTo?: string
  glowColor?: string
}>(), {
  dotRadius: 1.5,
  dotSpacing: 14,
  cursorRadius: 500,
  cursorForce: 0.1,
  bulgeOnly: true,
  bulgeStrength: 67,
  glowRadius: 160,
  sparkle: false,
  waveAmplitude: 0,
  gradientFrom: 'rgba(255,255,255, 0.35)',
  gradientTo: 'rgba(255,255,255, 0.25)',
  glowColor: '#121214',
})

const canvasRef = ref<HTMLCanvasElement>()
const glowRef = ref<SVGCircleElement>()
const glowId = `dot-field-glow-${Math.random().toString(36).slice(2, 9)}`

const dots: Dot[] = []
const mouse = { x: -9999, y: -9999, prevX: -9999, prevY: -9999, speed: 0 }
const size = { w: 0, h: 0, offsetX: 0, offsetY: 0 }

let animationFrame = 0
let speedTimer = 0
let resizeTimer = 0
let glowOpacity = 0
let engagement = 0
let frameCount = 0
let cleanupEvents: (() => void) | null = null

function buildDots(width: number, height: number) {
  const step = props.dotRadius + props.dotSpacing
  const cols = Math.floor(width / step)
  const rows = Math.floor(height / step)
  const padX = (width % step) / 2
  const padY = (height % step) / 2

  dots.length = 0

  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      const ax = padX + col * step + step / 2
      const ay = padY + row * step + step / 2
      dots.push({ ax, ay, sx: ax, sy: ay, vx: 0, vy: 0, x: ax, y: ay })
    }
  }
}

function updateMouseSpeed() {
  const dx = mouse.prevX - mouse.x
  const dy = mouse.prevY - mouse.y
  const dist = Math.sqrt(dx * dx + dy * dy)
  mouse.speed += (dist - mouse.speed) * 0.5
  if (mouse.speed < 0.001) mouse.speed = 0
  mouse.prevX = mouse.x
  mouse.prevY = mouse.y
}

onMounted(() => {
  const canvas = canvasRef.value
  const container = canvas?.parentElement
  if (!canvas || !container) return

  const context = canvas.getContext('2d', { alpha: true })
  if (!context) return

  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

  const resize = () => {
    window.clearTimeout(resizeTimer)
    resizeTimer = window.setTimeout(doResize, 100)
  }

  const doResize = () => {
    const rect = container.getBoundingClientRect()

    size.w = rect.width
    size.h = rect.height
    size.offsetX = rect.left + window.scrollX
    size.offsetY = rect.top + window.scrollY

    canvas.width = size.w * dpr
    canvas.height = size.h * dpr
    canvas.style.width = `${size.w}px`
    canvas.style.height = `${size.h}px`
    context.setTransform(dpr, 0, 0, dpr, 0, 0)

    buildDots(size.w, size.h)
  }

  const onMouseMove = (event: MouseEvent) => {
    mouse.x = event.pageX - size.offsetX
    mouse.y = event.pageY - size.offsetY
  }

  const tick = () => {
    frameCount++
    const targetEngagement = Math.min(mouse.speed / 5, 1)
    engagement += (targetEngagement - engagement) * 0.06
    if (engagement < 0.001) engagement = 0

    glowOpacity += (engagement - glowOpacity) * 0.08

    if (glowRef.value) {
      glowRef.value.setAttribute('cx', String(mouse.x))
      glowRef.value.setAttribute('cy', String(mouse.y))
      glowRef.value.style.opacity = String(glowOpacity)
    }

    context.clearRect(0, 0, size.w, size.h)

    const grad = context.createLinearGradient(0, 0, size.w, size.h)
    grad.addColorStop(0, props.gradientFrom)
    grad.addColorStop(1, props.gradientTo)
    context.fillStyle = grad

    const cursorRadiusSq = props.cursorRadius * props.cursorRadius
    const radius = props.dotRadius / 2
    const t = frameCount * 0.02

    context.beginPath()

    for (let i = 0; i < dots.length; i++) {
      const dot = dots[i]
      const dx = mouse.x - dot.ax
      const dy = mouse.y - dot.ay
      const distSq = dx * dx + dy * dy

      if (distSq < cursorRadiusSq && engagement > 0.01) {
        const dist = Math.sqrt(distSq)

        if (props.bulgeOnly) {
          const ratio = 1 - dist / props.cursorRadius
          const push = ratio * ratio * props.bulgeStrength * engagement
          const angle = Math.atan2(dy, dx)
          dot.sx += (dot.ax - Math.cos(angle) * push - dot.sx) * 0.15
          dot.sy += (dot.ay - Math.sin(angle) * push - dot.sy) * 0.15
        } else {
          const angle = Math.atan2(dy, dx)
          const move = (500 / Math.max(dist, 1)) * (mouse.speed * props.cursorForce)
          dot.vx += Math.cos(angle) * -move
          dot.vy += Math.sin(angle) * -move
        }
      } else if (props.bulgeOnly) {
        dot.sx += (dot.ax - dot.sx) * 0.1
        dot.sy += (dot.ay - dot.sy) * 0.1
      }

      if (!props.bulgeOnly) {
        dot.vx *= 0.9
        dot.vy *= 0.9
        dot.x = dot.ax + dot.vx
        dot.y = dot.ay + dot.vy
        dot.sx += (dot.x - dot.sx) * 0.1
        dot.sy += (dot.y - dot.sy) * 0.1
      }

      let drawX = dot.sx
      let drawY = dot.sy

      if (props.waveAmplitude > 0) {
        drawY += Math.sin(dot.ax * 0.03 + t) * props.waveAmplitude
        drawX += Math.cos(dot.ay * 0.03 + t * 0.7) * props.waveAmplitude * 0.5
      }

      if (props.sparkle) {
        const hash = ((i * 2654435761) ^ (frameCount >> 3)) >>> 0
        const sparkleRadius = hash % 100 < 3 ? radius * 1.8 : radius
        context.moveTo(drawX + sparkleRadius, drawY)
        context.arc(drawX, drawY, sparkleRadius, 0, TWO_PI)
      } else {
        context.moveTo(drawX + radius, drawY)
        context.arc(drawX, drawY, radius, 0, TWO_PI)
      }
    }

    context.fill()

    if (!reducedMotion) {
      animationFrame = requestAnimationFrame(tick)
    }
  }

  doResize()
  window.addEventListener('resize', resize)
  window.addEventListener('mousemove', onMouseMove, { passive: true })
  speedTimer = window.setInterval(updateMouseSpeed, 20)
  animationFrame = requestAnimationFrame(tick)
  cleanupEvents = () => {
    window.removeEventListener('resize', resize)
    window.removeEventListener('mousemove', onMouseMove)
  }
})

onUnmounted(() => {
  if (animationFrame) cancelAnimationFrame(animationFrame)
  window.clearInterval(speedTimer)
  window.clearTimeout(resizeTimer)
  if (cleanupEvents) cleanupEvents()
})

watch(() => [props.dotRadius, props.dotSpacing], () => {
  if (size.w > 0 && size.h > 0) buildDots(size.w, size.h)
})
</script>

<template>
  <div class="dot-field-container">
    <canvas ref="canvasRef" class="dot-field-canvas" />
    <svg class="dot-field-glow" aria-hidden="true">
      <defs>
        <radialGradient :id="glowId">
          <stop offset="0%" :stop-color="glowColor" />
          <stop offset="100%" stop-color="transparent" />
        </radialGradient>
      </defs>
      <circle
        ref="glowRef"
        cx="-9999"
        cy="-9999"
        :r="glowRadius"
        :fill="`url(#${glowId})`"
      />
    </svg>
  </div>
</template>

<style scoped>
.dot-field-container {
  position: fixed;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
}

.dot-field-canvas,
.dot-field-glow {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.dot-field-canvas {
  display: block;
}

.dot-field-glow {
  pointer-events: none;
}

.dot-field-glow circle {
  opacity: 0;
  will-change: opacity;
}
</style>
