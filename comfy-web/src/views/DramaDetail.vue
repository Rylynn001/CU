<template>
  <div class="detail-page" v-if="drama">
    <div class="page-head">
      <div class="head-left">
        <button class="back-btn" @click="router.push('/drama')">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round">
            <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
          </svg>
          短剧项目
        </button>
        <h1 class="page-title">{{ drama.title }}</h1>
        <div class="drama-meta">
          <span v-if="drama.style" class="style-tag">{{ drama.style }}</span>
          <span class="meta-item">{{ drama.characters?.length || 0 }} 角色</span>
          <span class="meta-item">{{ drama.scenes?.length || 0 }} 场景</span>
        </div>
      </div>
      <button class="btn-primary" @click="addEpisode">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
          <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        新增集
      </button>
    </div>

    <div v-if="!drama.episodes?.length" class="empty-state">
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round">
        <rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/>
      </svg>
      <p class="empty-title">还没有集</p>
      <p class="empty-desc">点击「新增集」开始创作第一集</p>
    </div>

    <div v-else class="episode-list">
      <div
        v-for="ep in drama.episodes"
        :key="ep.id"
        class="ep-card"
        @click="router.push(`/drama/${drama.id}/episode/${ep.episode_number}`)"
      >
        <div class="ep-number">{{ ep.episode_number }}</div>
        <div class="ep-info">
          <div class="ep-title">{{ ep.title }}</div>
          <div class="ep-meta">
            <span :class="['ep-status', `status-${ep.status}`]">{{ statusLabel(ep.status) }}</span>
            <span v-if="ep.has_script" class="ep-badge">有剧本</span>
          </div>
        </div>
        <div class="ep-arrow">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
            <path d="M9 18l6-6-6-6"/>
          </svg>
        </div>
      </div>
    </div>
  </div>

  <div v-else-if="loading" class="loading-center">
    <svg class="spin" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
      <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
    </svg>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'

const router = useRouter()
const route = useRoute()
const BASE = '/api/api-proxy'

const drama = ref<any>(null)
const loading = ref(false)
const dramaId = Number(route.params.id)

async function load() {
  loading.value = true
  try {
    const res = await fetch(`${BASE}/dramas/${dramaId}`)
    if (!res.ok) throw new Error('加载失败')
    drama.value = await res.json()
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function addEpisode() {
  const eps = drama.value?.episodes || []
  const nextNum = eps.length + 1
  try {
    const res = await fetch(`${BASE}/episodes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ drama_id: dramaId, episode_number: nextNum }),
    })
    if (!res.ok) throw new Error('创建失败')
    const ep = await res.json()
    router.push(`/drama/${dramaId}/episode/${ep.episode_number}`)
  } catch (e: any) {
    ElMessage.error(e.message)
  }
}

function statusLabel(s: string) {
  const map: Record<string, string> = { draft: '草稿', processing: '制作中', done: '已完成' }
  return map[s] || s
}

onMounted(load)
</script>

<style scoped>
.detail-page {
  padding: 28px 48px 40px;
  overflow-y: auto;
  height: 100%;
}

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 32px;
}
.head-left { display: flex; flex-direction: column; gap: 8px; }

.back-btn {
  display: flex; align-items: center; gap: 6px;
  background: none; border: none; cursor: pointer;
  color: rgba(255,255,255,0.4); font-size: 13px;
  padding: 0; transition: color 0.2s;
}
.back-btn:hover { color: rgba(255,255,255,0.8); }

.page-title { font-size: 26px; font-weight: 700; color: #fff; margin: 0; }
.drama-meta { display: flex; align-items: center; gap: 10px; }
.style-tag {
  font-size: 11px; font-weight: 500; padding: 2px 8px;
  background: rgba(167,139,250,0.12); color: #c4b5fd; border-radius: 99px;
  border: 1px solid rgba(167,139,250,0.2);
}
.meta-item { font-size: 12px; color: rgba(255,255,255,0.4); }

.empty-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 12px; padding: 80px 32px;
  color: rgba(255,255,255,0.3);
}
.empty-title { font-size: 15px; font-weight: 600; color: rgba(255,255,255,0.6); margin: 0; }
.empty-desc { font-size: 13px; color: rgba(255,255,255,0.3); margin: 0; }

.episode-list { display: flex; flex-direction: column; gap: 10px; }

.ep-card {
  display: flex; align-items: center; gap: 16px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px; padding: 16px 20px;
  cursor: pointer; transition: all 0.2s ease;
}
.ep-card:hover {
  border-color: #a78bfa;
  background: rgba(167,139,250,0.06);
  transform: translateX(4px);
}

.ep-number {
  width: 40px; height: 40px; border-radius: 10px; flex-shrink: 0;
  background: rgba(167,139,250,0.12); color: #a78bfa;
  display: flex; align-items: center; justify-content: center;
  font-size: 15px; font-weight: 700;
}

.ep-info { flex: 1; display: flex; flex-direction: column; gap: 5px; }
.ep-title { font-size: 15px; font-weight: 600; color: #fff; }
.ep-meta { display: flex; align-items: center; gap: 8px; }

.ep-status {
  font-size: 11px; font-weight: 500; padding: 2px 7px; border-radius: 99px;
}
.status-draft { background: rgba(255,255,255,0.08); color: rgba(255,255,255,0.4); }
.status-processing { background: rgba(250,204,21,0.12); color: #fbbf24; }
.status-done { background: rgba(74,222,128,0.12); color: #4ade80; }

.ep-badge {
  font-size: 11px; padding: 2px 7px; border-radius: 99px;
  background: rgba(167,139,250,0.12); color: #c4b5fd;
}

.ep-arrow { color: rgba(255,255,255,0.2); transition: color 0.2s; }
.ep-card:hover .ep-arrow { color: #a78bfa; }

.loading-center {
  display: flex; align-items: center; justify-content: center; height: 100%;
}
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.btn-primary {
  display: flex; align-items: center; gap: 6px;
  background: #7c3aed; color: #fff; border: none;
  border-radius: 8px; padding: 8px 16px; font-size: 13px; font-weight: 500;
  cursor: pointer; transition: background 0.2s;
}
.btn-primary:hover { background: #6d28d9; }

/* 统一为参数面板的玻璃风格 */
.style-tag,
.ep-badge,
.ep-status {
  background: rgba(255,255,255,0.08);
  border: 1px solid var(--color-border);
  color: var(--color-muted);
}
.ep-card {
  background: linear-gradient(180deg, rgba(25, 29, 39, 0.5), rgba(6, 8, 13, 0.34));
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-soft);
  backdrop-filter: var(--glass-blur);
}
.ep-card:hover {
  border-color: rgba(255,255,255,0.24);
  background: linear-gradient(180deg, rgba(32, 37, 49, 0.54), rgba(8, 10, 16, 0.4));
}
.ep-number {
  background: rgba(255,255,255,0.08);
  border: 1px solid var(--color-border);
  color: var(--color-muted);
}
.ep-card:hover .ep-arrow {
  color: var(--color-muted);
}
.btn-primary {
  background: rgba(255,255,255,0.12);
  border: 1px solid rgba(255,255,255,0.24);
  color: var(--color-text);
  box-shadow: 0 12px 32px rgba(0,0,0,0.24);
}
.btn-primary:hover {
  background: rgba(255,255,255,0.18);
  border-color: rgba(255,255,255,0.34);
}
</style>
