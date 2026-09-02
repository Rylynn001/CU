<script setup lang="ts">
import { useRouter } from 'vue-router'
const router = useRouter()

const features = [
  {
    path: '/image',
    title: '图片生成',
    desc: '基于 ComfyUI 的文生图、图生图工作台，支持多模型、多参数精细调控。',
  },
  {
    path: '/video',
    title: '视频生成',
    desc: '输入文字或图片，生成连贯的 AI 视频内容，支持多种风格与时长。',
  },
  {
    path: '/node-panel',
    title: '节点面板',
    desc: '全新的节点式创作模式，多面板逐级溯源提示词与参考素材，理清创作链路。',
  },
  {
    path: '/assets',
    title: '我的资产',
    desc: '集中管理图片、视频等生成内容，方便查看、复用与下载创作成果。',
  },
]
</script>

<template>
  <div class="home">
    <main class="home-stage">
      <section class="hero" aria-labelledby="home-title">
        <h1 id="home-title" class="hero-title">若晴AI Studio</h1>
        <p class="hero-sub">从提示词、参考素材到历史记录，用清晰的工作台承载连续创作流程。</p>
      </section>

      <section class="cards" aria-label="主要入口">
        <button
          v-for="feature in features"
          :key="feature.path"
          type="button"
          class="feature-card"
          @click="router.push(feature.path)"
        >
          <h2 class="card-title">{{ feature.title }}</h2>
          <p class="card-desc">{{ feature.desc }}</p>
        </button>
      </section>
    </main>
  </div>
</template>

<style scoped>
.home {
  min-height: 100vh;
  position: relative;
  overflow: hidden;
  padding: 48px clamp(28px, 5vw, 96px);
  animation: page-enter 0.5s ease both;
}

.home-stage {
  position: relative;
  z-index: 1;
  min-height: calc(100vh - 96px);
  display: grid;
  grid-template-columns: minmax(500px, 1.1fr) minmax(520px, 0.9fr);
  align-items: center;
  gap: clamp(42px, 5vw, 80px);
}

.hero {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 18px;
}

.hero-title {
  max-width: 680px;
  font-size: 50px;
  font-weight: 900;
  color: #fff;
  letter-spacing: 0;
  line-height: 1.02;
  white-space: nowrap;
  margin: 0;
  text-shadow: 0 14px 44px rgba(255, 255, 255, 0.12);
}

.hero-sub {
  max-width: 520px;
  margin: 0;
  color: var(--color-muted);
  font-size: 15px;
  line-height: 1.7;
  letter-spacing: 0;
}

.cards {
  display: flex;
  flex-direction: column;
  gap: 22px;
  width: 100%;
  max-width: 520px;
}

.feature-card {
  position: relative;
  border: 1px solid rgba(255, 255, 255, 0.13);
  border-radius: 24px;
  background: rgba(255,255,255,0.03);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  box-shadow: 0 8px 32px rgba(0,0,0,0.3);
  overflow: hidden;
}

.feature-card::before {
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(135deg, rgba(255,255,255,0.16), transparent 42%),
    radial-gradient(circle at 82% 12%, rgba(255,255,255,0.14), transparent 30%);
  opacity: 0.5;
}

.feature-card {
  min-height: 168px;
  padding: 36px 40px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 16px;
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.3s, background 0.3s, transform 0.2s, box-shadow 0.2s;
}

.feature-card:hover,
.feature-card:focus-visible {
  border-color: rgba(255, 255, 255, 0.24);
  background: rgba(255,255,255,0.045);
  transform: translateY(-3px);
  box-shadow: var(--shadow-soft);
}

.card-title {
  position: relative;
  z-index: 1;
  margin: 0;
  color: var(--color-text);
  font-size: 28px;
  font-weight: 800;
  letter-spacing: 0;
}

.card-desc {
  position: relative;
  z-index: 1;
  margin: 0;
  color: rgba(226, 232, 240, 0.48);
  font-size: 14px;
  line-height: 1.7;
}

@media (max-width: 1200px) {
  .home-stage {
    grid-template-columns: minmax(0, 1fr) minmax(420px, 1fr);
    gap: 36px;
  }

  .hero-title {
    font-size: 38px;
  }
}

@media (max-width: 900px) {
  .home-stage {
    grid-template-columns: 1fr;
  }

  .cards {
    max-width: none;
  }
}

@media (max-width: 768px) {
  .home {
    padding: 28px 20px;
  }

  .home-stage {
    min-height: auto;
    grid-template-columns: 1fr;
  }

  .hero-title {
    font-size: 29px;
  }

  .cards {
    max-width: none;
  }
}

@media (max-width: 480px) {
  .home {
    padding-inline: 16px;
  }

  .hero-title {
    font-size: 25px;
  }
}
</style>
