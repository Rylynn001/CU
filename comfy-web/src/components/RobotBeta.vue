<template>
  <div
    class="relative flex flex-col items-center justify-center select-none px-2.5 pt-2"
    :style="containerStyle"
  >
    <!-- 顶部耳朵 -->
    <div class="relative w-20 flex justify-between px-2 -mb-2 z-0">
      <div class="w-3.5 h-4 bg-zinc-300 dark:bg-zinc-700 border-2 border-black/10 dark:border-white/10 rounded-tl-xl" />
      <div class="w-3.5 h-4 bg-zinc-300 dark:bg-zinc-700 border-2 border-black/10 dark:border-white/10 rounded-tr-xl" />
    </div>

    <!-- 主体 -->
    <div class="relative flex items-center justify-center">
      <!-- 左侧指示灯 -->
      <div
        :class="[
          'absolute -left-1.5 w-1 h-5 rounded-l-xs transition-all duration-300',
          sideEarClass,
        ]"
      />
      <!-- 右侧指示灯 -->
      <div
        :class="[
          'absolute -right-1.5 w-1 h-5 rounded-r-xs transition-all duration-300',
          sideEarClass,
        ]"
      />

      <!-- 屏幕外壳 -->
      <div class="z-10 w-22 h-15 rounded-xl bg-zinc-100 dark:bg-zinc-800 border-2 border-black/10 dark:border-white/20 flex items-center justify-center p-1.5 shadow-[0_3px_10px_rgba(0,0,0,0.05)] dark:shadow-[0_4px_16px_rgba(0,0,0,0.4)]">
        <!-- 屏幕内容 -->
        <div class="relative w-full h-full bg-[#050505] rounded-lg flex items-center justify-center gap-3.5 overflow-hidden shadow-[inset_0_2px_5px_rgba(0,0,0,0.95)]">
          <!-- 眼睛 -->
          <div class="relative z-10 flex items-center justify-center gap-3.5">
            <EyeLED :emotion="emotion" :is-blinking="isBlinking" :offset-x="eyeOffset" />
            <EyeLED :emotion="emotion" :is-blinking="isBlinking" :offset-x="eyeOffset" />
          </div>

          <!-- 扫描线效果 -->
          <div
            class="absolute inset-0 pointer-events-none z-20"
            style="
              background-image: linear-gradient(
                rgba(0, 0, 0, 0) 50%,
                rgba(0, 0, 0, 0.72) 50%
              );
              background-size: 100% 4px;
            "
          />

          <!-- 内阴影 -->
          <div class="absolute inset-0 pointer-events-none z-20 shadow-[inset_0_0_8px_rgba(0,0,0,0.9)]" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import EyeLED, { type RobotEmotion } from './EyeLED.vue'

const props = defineProps<{
  emotion: RobotEmotion
  textLength?: number
  isListening?: boolean
}>()

const isBlinking = ref(false)
const floatY = ref(0)

let blinkInterval: NodeJS.Timeout | null = null
let floatIntervalRef: NodeJS.Timeout | null = null

// 眼睛偏移量
const eyeOffset = computed(() => {
  return Math.sin((props.textLength || 0) * 0.45) * 6
})

// 侧耳指示灯样式
const sideEarClass = computed(() => {
  if (props.isListening) {
    return 'bg-red-500 shadow-[0_0_10px_#ef4444,0_0_18px_rgba(239,68,68,0.7)] animate-pulse'
  }
  if (props.emotion === 'thinking') {
    return 'bg-amber-400 shadow-[0_0_8px_#facc15]'
  }
  return 'bg-emerald-400 shadow-[0_0_8px_#10b981]'
})

// 浮动动画样式
const containerStyle = computed(() => ({
  transform: `translateY(${floatY.value}px)`,
  transition: 'transform 0.3s ease-out',
}))

// 眨眼逻辑
onMounted(() => {
  // 眨眼定时器
  const scheduleNextBlink = () => {
    const delay = 2800 + Math.random() * 2200
    blinkInterval = setTimeout(() => {
      if (props.emotion !== 'thinking') {
        isBlinking.value = true
        setTimeout(() => {
          isBlinking.value = false
        }, 140)
      }
      scheduleNextBlink()
    }, delay)
  }
  scheduleNextBlink()

  // 浮动动画
  let floatDirection = 1
  const floatSpeed = props.emotion === 'thinking' ? 5 : 2
  floatIntervalRef = setInterval(() => {
    floatY.value += floatDirection * 0.2
    const maxFloat = props.emotion === 'thinking' ? floatSpeed : floatSpeed
    if (floatY.value >= maxFloat || floatY.value <= -maxFloat) {
      floatDirection *= -1
    }
  }, 50)
})

onUnmounted(() => {
  if (blinkInterval) {
    clearTimeout(blinkInterval)
  }
  if (floatIntervalRef) {
    clearInterval(floatIntervalRef)
  }
})
</script>
