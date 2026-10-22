<template>
  <div
    v-if="isBlinking && !isThinking"
    class="w-2.5 h-1 rounded-xs bg-emerald-400 shadow-[0_0_6px_#10b981]"
  />

  <div
    v-else-if="isThinking"
    class="w-2.5 h-3.5 rounded-xs bg-amber-300 shadow-[0_0_10px_#facc15,0_0_18px_rgba(250,204,21,0.4)]"
    :style="thinkingStyle"
  />

  <div
    v-else
    class="w-2.5 h-4.5 rounded-xs bg-emerald-400 shadow-[0_0_12px_#34d399,0_0_20px_rgba(52,211,153,0.45)]"
    :style="eyeStyle"
  />
</template>

<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'

export type RobotEmotion = 'reading' | 'thinking'

const props = defineProps<{
  emotion: RobotEmotion
  isBlinking: boolean
  offsetX: number
}>()

const thinkingY = ref(0)
let thinkingInterval: NodeJS.Timeout | null = null

const isThinking = computed(() => props.emotion === 'thinking')

const eyeStyle = computed(() => ({
  transform: `translateX(${props.offsetX}px)`,
  transition: 'transform 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
}))

const thinkingStyle = computed(() => ({
  transform: `translateY(${thinkingY.value}px)`,
}))

// 模拟思考动画
watch(
  isThinking,
  (thinking) => {
    if (thinking) {
      let direction = 1
      thinkingInterval = setInterval(() => {
        thinkingY.value += direction * 0.5
        if (thinkingY.value >= -1 || thinkingY.value <= -3) {
          direction *= -1
        }
      }, 50)
    } else {
      if (thinkingInterval) {
        clearInterval(thinkingInterval)
        thinkingInterval = null
      }
      thinkingY.value = 0
    }
  },
  { immediate: true }
)

onUnmounted(() => {
  if (thinkingInterval) {
    clearInterval(thinkingInterval)
  }
})
</script>
