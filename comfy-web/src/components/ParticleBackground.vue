<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

const canvasRef = ref<HTMLCanvasElement>()
let animationId = 0
let resizeHandler: (() => void) | null = null

onMounted(() => {
  const canvas = canvasRef.value!
  const ctx = canvas.getContext('2d')!

  // 透镜参数
  const lens = { x: 0, y: 0, radius: 130, magnify: 2.0 }
  // 透镜自动漂浮的角度
  let lensAngle = 0
  let mouseActive = false

  // 网格参数
  const gap = 18        // 点间距（更密）
  const dotRadius = 1.0 // 基础点大小
  const dotColor = { r: 160, g: 170, b: 210 }

  function resize() {
    canvas.width = window.innerWidth
    canvas.height = window.innerHeight
    // 初始化透镜位置到右上区域
    if (!mouseActive) {
      lens.x = canvas.width * 0.65
      lens.y = canvas.height * 0.3
    }
  }

  function handleMouseMove(e: MouseEvent) {
    mouseActive = true
    lens.x = e.clientX
    lens.y = e.clientY
  }

  function handleMouseLeave() {
    mouseActive = false
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height)

    // 透镜自动漂浮（鼠标不活跃时）
    if (!mouseActive) {
      lensAngle += 0.003
      lens.x = canvas.width * 0.5 + Math.cos(lensAngle) * canvas.width * 0.2
      lens.y = canvas.height * 0.4 + Math.sin(lensAngle * 0.7) * canvas.height * 0.15
    }

    const cols = Math.ceil(canvas.width / gap) + 2
    const rows = Math.ceil(canvas.height / gap) + 2

    for (let row = 0; row < rows; row++) {
      for (let col = 0; col < cols; col++) {
        const baseX = col * gap
        const baseY = row * gap

        // 计算到透镜中心的距离
        const dx = baseX - lens.x
        const dy = baseY - lens.y
        const dist = Math.sqrt(dx * dx + dy * dy)

        let drawX = baseX
        let drawY = baseY
        let r = dotRadius
        let alpha = 0.2

        if (dist < lens.radius) {
          // 在透镜内部：放大效果
          // 越靠近中心放大越强
          const t = 1 - dist / lens.radius  // 0(边缘) → 1(中心)
          const smoothT = t * t * (3 - 2 * t) // smoothstep

          // 从透镜中心向外推移点的位置（模拟放大）
          const scale = 1 + (lens.magnify - 1) * smoothT
          drawX = lens.x + dx * scale
          drawY = lens.y + dy * scale

          // 放大点的大小和亮度
          r = dotRadius * (1 + smoothT * 2.5)
          alpha = 0.2 + smoothT * 0.7
        } else if (dist < lens.radius * 1.3) {
          // 边缘过渡区：轻微扭曲
          const edgeT = 1 - (dist - lens.radius) / (lens.radius * 0.3)
          const push = edgeT * 3
          drawX = baseX + (dx / dist) * push
          drawY = baseY + (dy / dist) * push
          alpha = 0.2 + edgeT * 0.05
        }

        ctx.beginPath()
        ctx.arc(drawX, drawY, r, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(${dotColor.r}, ${dotColor.g}, ${dotColor.b}, ${alpha})`
        ctx.fill()
      }
    }

    // 画透镜玻璃圆盘
    ctx.save()

    // 1. 玻璃底色 —— 半透明深色填充，模拟毛玻璃
    const glassGradient = ctx.createRadialGradient(
      lens.x, lens.y, 0,
      lens.x, lens.y, lens.radius
    )
    glassGradient.addColorStop(0, 'rgba(20, 20, 40, 0.25)')
    glassGradient.addColorStop(0.7, 'rgba(20, 20, 40, 0.18)')
    glassGradient.addColorStop(1, 'rgba(20, 20, 40, 0)')
    ctx.beginPath()
    ctx.arc(lens.x, lens.y, lens.radius, 0, Math.PI * 2)
    ctx.fillStyle = glassGradient
    ctx.fill()

    // 2. 玻璃边缘高光环 —— 模拟光线折射
    ctx.beginPath()
    ctx.arc(lens.x, lens.y, lens.radius, 0, Math.PI * 2)
    ctx.strokeStyle = 'rgba(180, 180, 255, 0.12)'
    ctx.lineWidth = 1.5
    ctx.stroke()

    // 3. 内圈微光
    ctx.beginPath()
    ctx.arc(lens.x, lens.y, lens.radius * 0.97, 0, Math.PI * 2)
    ctx.strokeStyle = 'rgba(200, 200, 255, 0.06)'
    ctx.lineWidth = 1
    ctx.stroke()

    // 4. 顶部弧形高光（模拟玻璃反光）
    ctx.beginPath()
    ctx.arc(lens.x, lens.y - lens.radius * 0.15, lens.radius * 0.75, Math.PI * 1.15, Math.PI * 1.85)
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.07)'
    ctx.lineWidth = 2
    ctx.stroke()

    ctx.restore()

    animationId = requestAnimationFrame(draw)
  }

  resize()
  draw()

  resizeHandler = resize
  window.addEventListener('resize', resize)
  window.addEventListener('mousemove', handleMouseMove)

  onUnmounted(() => {
    cancelAnimationFrame(animationId)
    window.removeEventListener('resize', resize)
    window.removeEventListener('mousemove', handleMouseMove)
  })
})
</script>

<template>
  <canvas ref="canvasRef" class="particle-bg" />
</template>

<style scoped>
.particle-bg {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  z-index: 0;
  pointer-events: none;
}
</style>
