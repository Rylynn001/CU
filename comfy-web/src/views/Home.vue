<script setup lang="ts">
import { useRouter } from 'vue-router'
import { Picture, VideoCamera, Files } from '@element-plus/icons-vue'

const router = useRouter()

const features = [
  {
    path: '/image',
    icon: Picture,
    title: '图片生成',
    desc: '基于 ComfyUI 的文生图、图生图工作台，支持多模型、多参数精细调控',
    tag: '已上线',
    tagActive: true,
  },
  {
    path: '/video',
    icon: VideoCamera,
    title: '视频生成',
    desc: '输入文字或图片，生成流畅的 AI 视频内容，支持多种风格与时长',
    tag: '已上线',
    tagActive: true,
  },
  {
    path: '/models',
    icon: Files,
    title: '模型管理',
    desc: '浏览、下载、切换本地模型，统一管理 checkpoint、LoRA 等资源',
    tag: '已上线',
    tagActive: true,
  },
]
</script>

<template>
  <div class="home">
    <!-- background orbs -->
    <div class="orb orb-1" />
    <div class="orb orb-2" />

    <!-- hero -->
    <section class="hero">
      <div class="hero-badge">AI Creative Studio</div>
      <h1 class="hero-title">
        泰然若晴
        <span class="hero-title-accent">创作平台</span>
      </h1>
      <p class="hero-sub">用 AI 释放创意，从图片到视频，一站式生成工作台</p>
    </section>

    <!-- feature cards -->
    <section class="cards">
      <div
        v-for="f in features"
        :key="f.path"
        class="feature-card"
        :class="{ clickable: f.tagActive }"
        @click="f.tagActive && router.push(f.path)"
      >
        <div class="card-glow" />
        <div class="card-top">
          <div class="card-icon">
            <el-icon><component :is="f.icon" /></el-icon>
          </div>
          <span class="card-tag" :class="{ active: f.tagActive }">{{ f.tag }}</span>
        </div>
        <h3 class="card-title">{{ f.title }}</h3>
        <p class="card-desc">{{ f.desc }}</p>
        <div v-if="f.tagActive" class="card-arrow">
          <span>进入</span>
          <span class="arrow">→</span>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.home {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 48px;
  position: relative;
  overflow: hidden;
  gap: 56px;
}

/* orbs */
.orb {
  position: fixed;
  border-radius: 50%;
  filter: blur(90px);
  pointer-events: none;
  z-index: 0;
  animation: breathe 7s ease-in-out infinite;
}
.orb-1 {
  width: 600px; height: 600px;
  background: radial-gradient(circle, rgba(108,99,255,0.14) 0%, transparent 70%);
  top: -160px; left: -160px;
}
.orb-2 {
  width: 500px; height: 500px;
  background: radial-gradient(circle, rgba(167,139,250,0.1) 0%, transparent 70%);
  bottom: -120px; right: -100px;
  animation-delay: 3.5s;
}

/* hero */
.hero {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 18px;
  z-index: 1;
  text-align: center;
}

.hero-badge {
  font-size: 11px;
  letter-spacing: 3px;
  text-transform: uppercase;
  color: rgba(167,139,250,0.7);
  border: 1px solid rgba(108,99,255,0.25);
  padding: 5px 18px;
  border-radius: 20px;
  animation: breathe-border 4s ease-in-out infinite;
}

.hero-title {
  font-size: clamp(36px, 5vw, 60px);
  font-weight: 700;
  color: rgba(255,255,255,0.92);
  letter-spacing: 4px;
  line-height: 1.15;
  margin: 0;
}

.hero-title-accent {
  background: linear-gradient(135deg, #6c63ff, #a78bfa, #c4b5fd);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.hero-sub {
  font-size: 15px;
  color: rgba(255,255,255,0.35);
  letter-spacing: 1px;
  max-width: 480px;
  line-height: 1.7;
  margin: 0;
}

/* cards */
.cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  width: 100%;
  max-width: 960px;
  z-index: 1;
}

.feature-card {
  position: relative;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 20px;
  padding: 28px 26px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow: hidden;
  transition: border-color 0.3s, background 0.3s, transform 0.2s;
  animation: breathe-border 5s ease-in-out infinite;
}

.feature-card.clickable {
  cursor: pointer;
}

.feature-card.clickable:hover {
  border-color: rgba(108,99,255,0.5);
  background: rgba(108,99,255,0.06);
  transform: translateY(-3px);
}

.feature-card.clickable:hover .card-glow {
  opacity: 1;
}

.feature-card.clickable:hover .card-arrow {
  color: #a78bfa;
}

.feature-card.clickable:hover .arrow {
  transform: translateX(4px);
}

/* inner glow on hover */
.card-glow {
  position: absolute;
  inset: 0;
  background: radial-gradient(ellipse at top left, rgba(108,99,255,0.1) 0%, transparent 60%);
  opacity: 0;
  transition: opacity 0.3s;
  pointer-events: none;
}

.card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-icon {
  width: 44px; height: 44px;
  border-radius: 14px;
  background: rgba(108,99,255,0.12);
  border: 1px solid rgba(108,99,255,0.2);
  display: flex; align-items: center; justify-content: center;
  font-size: 20px;
  color: #a78bfa;
}

.card-tag {
  font-size: 10px;
  letter-spacing: 1px;
  padding: 3px 10px;
  border-radius: 20px;
  border: 1px solid rgba(255,255,255,0.1);
  color: rgba(255,255,255,0.3);
}

.card-tag.active {
  border-color: rgba(108,99,255,0.35);
  color: rgba(167,139,250,0.8);
  background: rgba(108,99,255,0.08);
}

.card-title {
  font-size: 18px;
  font-weight: 600;
  color: rgba(255,255,255,0.88);
  letter-spacing: 1px;
  margin: 0;
}

.card-desc {
  font-size: 13px;
  color: rgba(255,255,255,0.35);
  line-height: 1.7;
  margin: 0;
  flex: 1;
}

.card-arrow {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: rgba(255,255,255,0.4);
  transition: color 0.2s;
  margin-top: 4px;
}

.arrow {
  display: inline-block;
  transition: transform 0.2s ease;
}

@media (max-width: 768px) {
  .cards { grid-template-columns: 1fr; }
  .home { padding: 40px 20px; }
}
</style>
