<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

const canvasRef = ref<HTMLCanvasElement>()
let resizeHandler: (() => void) | null = null

onMounted(() => {
  const canvas = canvasRef.value!
  const ctx = canvas.getContext('2d')!

  const gap = 18
  const dotRadius = 1.0
  const dotColor = { r: 160, g: 170, b: 210 }

  function resize() {
    canvas.width = window.innerWidth
    canvas.height = window.innerHeight
    draw()
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    const cols = Math.ceil(canvas.width / gap) + 2
    const rows = Math.ceil(canvas.height / gap) + 2
    for (let row = 0; row < rows; row++) {
      for (let col = 0; col < cols; col++) {
        ctx.beginPath()
        ctx.arc(col * gap, row * gap, dotRadius, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(${dotColor.r}, ${dotColor.g}, ${dotColor.b}, 0.2)`
        ctx.fill()
      }
    }
  }

  resize()
  resizeHandler = resize
  window.addEventListener('resize', resize)

  onUnmounted(() => {
    window.removeEventListener('resize', resize)
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
