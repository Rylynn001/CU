<script setup lang="ts">
import { ref } from 'vue'
import { ElInput } from 'element-plus'
import { apiVideoGenerate } from '../api/apiService'

const prompt = ref('')
const generating = ref(false)
const videoUrl = ref('')
const errorMsg = ref('')

async function handleGenerate() {
  if (!prompt.value.trim()) { errorMsg.value = '请输入提示词'; return }
  errorMsg.value = ''
  videoUrl.value = ''
  generating.value = true
  try {
    const result = await apiVideoGenerate({ prompt: prompt.value.trim() })
    videoUrl.value = result.video_url
  } catch (e: any) {
    errorMsg.value = '生成失败：' + e.message
  } finally {
    generating.value = false
  }
}
</script>

<template>
  <div class="page">
    <div class="orb orb-1" />
    <div class="orb orb-2" />

    <div class="layout">
      <!-- LEFT PANEL -->
      <aside class="left-panel">
        <div class="panel-header">
          <span class="panel-title">视频生成</span>
          <span class="model-tag">sora-2</span>
        </div>

        <div class="panel-body">
          <p v-if="errorMsg" class="error-msg">{{ errorMsg }}</p>

          <div class="section-label">描述视频内容</div>
          <ElInput
            v-model="prompt"
            type="textarea"
            :rows="6"
            placeholder="输入提示词，描述你想生成的视频内容、场景、动作..."
            class="prompt-input"
          />

          <button
            class="generate-btn"
            :class="{ loading: generating }"
            :disabled="generating"
            @click="handleGenerate"
          >
            <span class="btn-glow" />
            <span class="btn-label">{{ generating ? '生成中...' : '开始生成' }}</span>
          </button>

          <div v-if="generating" class="hint-text">视频生成需要约 1-3 分钟，请耐心等待</div>
        </div>
      </aside>

      <!-- RIGHT: RESULT -->
      <main class="right-panel">
        <!-- Loading -->
        <div v-if="generating" class="api-loading">
          <div class="breath-ring">
            <div class="ring r1" /><div class="ring r2" /><div class="ring r3" />
            <div class="center-dot" />
          </div>
          <p class="loading-text">生成中...</p>
        </div>

        <!-- Video result -->
        <div v-else-if="videoUrl" class="video-wrap">
          <video
            :src="videoUrl"
            controls
            autoplay
            loop
            class="result-video"
          />
          <a :href="videoUrl" target="_blank" class="download-link">下载视频</a>
        </div>

        <!-- Empty -->
        <div v-else class="empty-wrap">
          <div class="empty-orb" />
          <p class="empty-text">等待生成</p>
        </div>
      </main>
    </div>
  </div>
</template>

<style scoped>
.page {
  min-height: 100vh;
  position: relative;
  overflow: hidden;
}

.orb {
  position: fixed;
  border-radius: 50%;
  filter: blur(90px);
  pointer-events: none;
  z-index: 0;
  animation: breathe 6s ease-in-out infinite;
}
.orb-1 {
  width: 500px; height: 500px;
  background: radial-gradient(circle, rgba(108,99,255,0.16) 0%, transparent 70%);
  top: -140px; left: 40px;
}
.orb-2 {
  width: 400px; height: 400px;
  background: radial-gradient(circle, rgba(167,139,250,0.12) 0%, transparent 70%);
  bottom: -100px; right: 60px;
  animation-delay: 3s;
}

.layout {
  position: relative;
  z-index: 1;
  display: flex;
  height: 100vh;
  overflow: hidden;
}

/* Left panel */
.left-panel {
  width: 340px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid rgba(255,255,255,0.06);
  background: rgba(255,255,255,0.02);
  backdrop-filter: blur(16px);
  overflow-y: auto;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 20px 0;
  flex-shrink: 0;
}

.panel-title {
  font-size: 15px;
  font-weight: 600;
  color: rgba(255,255,255,0.85);
  letter-spacing: 1px;
}

.model-tag {
  font-size: 10px;
  color: rgba(167,139,250,0.7);
  border: 1px solid rgba(108,99,255,0.25);
  padding: 2px 10px;
  border-radius: 20px;
  letter-spacing: 1px;
}

.panel-body {
  padding: 20px 20px 32px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.section-label {
  font-size: 11px;
  color: rgba(255,255,255,0.35);
  letter-spacing: 1px;
  margin-bottom: -4px;
}

.prompt-input { width: 100%; }

.generate-btn {
  position: relative;
  width: 100%; height: 46px;
  margin-top: 8px;
  border-radius: 12px; border: none;
  cursor: pointer; overflow: hidden;
  background: linear-gradient(135deg, #6c63ff, #a78bfa, #6c63ff);
  background-size: 200% auto;
  color: #fff; font-size: 14px;
  font-weight: 600; letter-spacing: 2px;
  transition: opacity 0.2s, transform 0.15s;
  animation: shimmer 3s linear infinite;
}
.generate-btn:hover:not(:disabled) { transform: translateY(-1px); opacity: 0.9; }
.generate-btn:active:not(:disabled) { transform: translateY(0); }
.generate-btn:disabled { opacity: 0.45; cursor: not-allowed; animation: none; }
.generate-btn.loading { animation: breathe 2s ease-in-out infinite; }

.btn-glow {
  position: absolute; inset: 0;
  border-radius: inherit; background: inherit;
  filter: blur(12px); opacity: 0;
  transition: opacity 0.3s; z-index: -1;
}
.generate-btn:not(:disabled):hover .btn-glow { opacity: 0.5; }
.btn-label { position: relative; z-index: 1; }

.hint-text {
  font-size: 11px;
  color: rgba(255,255,255,0.25);
  text-align: center;
  letter-spacing: 0.5px;
}

.error-msg {
  color: #f87171; font-size: 12px;
  padding: 8px 12px;
  background: rgba(248,113,113,0.07);
  border-radius: 8px;
  border: 1px solid rgba(248,113,113,0.18);
}

/* Right panel */
.right-panel {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  overflow-y: auto;
}

/* Video result */
.video-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  width: 100%;
  max-width: 860px;
}

.result-video {
  width: 100%;
  max-height: 540px;
  border-radius: 16px;
  box-shadow: 0 8px 48px rgba(0,0,0,0.6);
  background: #000;
}

.download-link {
  font-size: 12px;
  color: rgba(167,139,250,0.7);
  text-decoration: none;
  border: 1px solid rgba(108,99,255,0.2);
  padding: 5px 18px;
  border-radius: 20px;
  letter-spacing: 1px;
  transition: border-color 0.2s, color 0.2s;
}
.download-link:hover { border-color: rgba(108,99,255,0.5); color: #a78bfa; }

/* Loading */
.api-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
}
.loading-text {
  font-size: 13px;
  color: rgba(255,255,255,0.35);
  letter-spacing: 2px;
}

.breath-ring {
  position: relative;
  width: 100px; height: 100px;
  display: flex; align-items: center; justify-content: center;
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

/* Empty */
.empty-wrap {
  display: flex; flex-direction: column;
  align-items: center; gap: 14px;
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

@media (max-width: 900px) {
  .layout { flex-direction: column; height: auto; }
  .left-panel { width: 100%; border-right: none; border-bottom: 1px solid rgba(255,255,255,0.06); }
  .right-panel { padding: 24px 20px; }
}
</style>
