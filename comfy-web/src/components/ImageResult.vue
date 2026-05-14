<script setup lang="ts">
import { computed } from 'vue'
import { ElImage, ElEmpty } from 'element-plus'

const props = defineProps<{
  imageUrl: string
  progress: number
  generating: boolean
}>()

const progressPct = computed(() => Math.round(props.progress))
</script>

<template>
  <div class="image-result">
    <!-- generating state -->
    <div v-if="generating" class="generating-wrap">
      <div class="breath-ring">
        <div class="ring r1" />
        <div class="ring r2" />
        <div class="ring r3" />
        <div class="center-dot" />
      </div>
      <div class="progress-track">
        <div class="progress-fill" :style="{ width: progressPct + '%' }" />
      </div>
      <p class="progress-label">{{ progressPct }}%</p>
    </div>

    <!-- result image -->
    <div v-if="imageUrl" class="image-wrap">
      <ElImage
        :src="imageUrl"
        fit="contain"
        :preview-src-list="[imageUrl]"
        class="result-image"
      />
    </div>

    <!-- empty -->
    <div v-else-if="!generating" class="empty-wrap">
      <div class="empty-orb" />
      <p class="empty-text">等待生成</p>
    </div>
  </div>
</template>

<style scoped>
.image-result {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 420px;
  gap: 20px;
}

/* ── Breathing ring ── */
.generating-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
  width: 100%;
}

.breath-ring {
  position: relative;
  width: 100px;
  height: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.ring {
  position: absolute;
  border-radius: 50%;
  border: 1.5px solid rgba(108, 99, 255, 0.5);
  animation: breathe 3s ease-in-out infinite;
}
.r1 { width: 100%; height: 100%; animation-delay: 0s; }
.r2 { width: 72%; height: 72%; animation-delay: 0.5s; border-color: rgba(167,139,250,0.5); }
.r3 { width: 44%; height: 44%; animation-delay: 1s; border-color: rgba(196,181,253,0.6); }

.center-dot {
  width: 10px; height: 10px;
  border-radius: 50%;
  background: #a78bfa;
  animation: pulse-dot 2s ease-in-out infinite;
}

/* progress bar */
.progress-track {
  width: 200px;
  height: 3px;
  background: rgba(255,255,255,0.08);
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #6c63ff, #a78bfa);
  border-radius: 2px;
  transition: width 0.4s ease;
}

.progress-label {
  font-size: 12px;
  color: rgba(255,255,255,0.4);
  letter-spacing: 1px;
}

/* image */
.image-wrap {
  width: 100%;
  display: flex;
  justify-content: center;
}

.result-image {
  max-width: 100%;
  max-height: 560px;
  border-radius: 14px;
  box-shadow: 0 8px 40px rgba(0,0,0,0.5);
}

/* empty */
.empty-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}

.empty-orb {
  width: 60px; height: 60px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(108,99,255,0.15) 0%, transparent 70%);
  border: 1px solid rgba(108,99,255,0.15);
  animation: breathe 4s ease-in-out infinite;
}

.empty-text {
  font-size: 12px;
  color: rgba(255,255,255,0.2);
  letter-spacing: 2px;
}
</style>
