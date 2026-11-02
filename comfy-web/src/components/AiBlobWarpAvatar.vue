<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { usePreferredReducedMotion } from '@vueuse/core'
import { ShaderMount, warpFragmentShader, getShaderColorFromString, type WarpUniforms } from '@paper-design/shaders'

const surface = ref<HTMLElement>()
const reducedMotion = usePreferredReducedMotion()
let shader: ShaderMount | undefined

onMounted(() => {
  if (!surface.value) return
  const uniforms: WarpUniforms = {
    u_colors: ['#fda4af', '#0070f3', '#fb923c', '#f472b6', '#00d4ff'].map(getShaderColorFromString),
    u_colorsCount: 5,
    u_proportion: 0.54,
    u_softness: 1,
    u_shape: 0,
    u_shapeScale: 1,
    u_distortion: 0.25,
    u_swirl: 0.8,
    u_swirlIterations: 10,
    u_fit: 0,
    u_scale: 0.2,
    u_rotation: 0,
    u_originX: 0.5,
    u_originY: 0.5,
    u_offsetX: 0,
    u_offsetY: 0,
    u_worldWidth: 0,
    u_worldHeight: 0,
  }
  // 不支持 WebGL 的设备保留圆形渐变底色。
  try {
    shader = new ShaderMount(surface.value, warpFragmentShader, { ...uniforms }, undefined, reducedMotion.value === 'reduce' ? 0 : 1.15)
  } catch {
    shader = undefined
  }
})

watch(reducedMotion, value => shader?.setSpeed(value === 'reduce' ? 0 : 1.15))
onUnmounted(() => shader?.dispose())
</script>

<template>
  <span class="warp-avatar" aria-hidden="true"><span ref="surface" class="warp-surface" /></span>
</template>

<style scoped>
.warp-avatar { display: block; position: relative; isolation: isolate; width: 32px; height: 32px; border-radius: 50%; overflow: hidden; background: linear-gradient(135deg, #fda4af, #0070f3, #00d4ff); box-shadow: 0 0 0 1px var(--color-border), 0 2px 8px var(--color-surface-soft); }
.warp-surface { position: absolute; inset: 0; border-radius: inherit; animation: warp-pulse 5.2s ease-in-out infinite; }
.warp-surface :deep(canvas) { display: block; width: 100%; height: 100%; }
@keyframes warp-pulse { 0%, 100% { transform: scale(1) rotate(0); } 35% { transform: scale(1.055) rotate(2deg); } 70% { transform: scale(.99) rotate(-1.5deg); } }
@media (prefers-reduced-motion: reduce) { .warp-surface { animation: none; } }
</style>
