<template>
  <div class="drama-page">
    <div class="page-head">
      <div class="head-left">
        <h1 class="page-title">短剧项目</h1>
        <p class="page-desc">{{ dramas.length }} 个项目</p>
      </div>
      <button class="btn-primary" @click="showCreate = true">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
          <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        新建项目
      </button>
    </div>

    <div v-if="loading" class="grid">
      <div v-for="i in 3" :key="i" class="skeleton-card" />
    </div>

    <div v-else class="grid">
      <div
        v-for="(d, i) in dramas"
        :key="d.id"
        class="project-card"
        :style="{ animationDelay: `${i * 0.06}s` }"
        @click="router.push(`/drama/${d.id}`)"
      >
        <div class="card-film-strip">
          <span v-for="j in 5" :key="j" class="film-hole" />
        </div>
        <div class="card-body">
          <div class="card-header">
            <div class="episode-badge">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="10"/></svg>
              {{ d.episode_count || 0 }} 集
            </div>
            <button class="btn-ghost-icon" @click.stop="delDrama(d)" title="删除">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">
                <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14H6L5 6"/>
                <path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/>
              </svg>
            </button>
          </div>
          <h3 class="project-title">{{ d.title }}</h3>
          <div class="project-meta">
            <span v-if="d.style" class="style-tag">{{ d.style }}</span>
            <span class="meta-item">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
              {{ d.character_count || 0 }}
            </span>
            <span class="meta-item">
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/></svg>
              {{ d.scene_count || 0 }}
            </span>
          </div>
        </div>
        <div class="card-footer">
          <span class="card-date">{{ fmtDate(d.updated_at) }}</span>
        </div>
      </div>

      <div v-if="!dramas.length" class="empty-card" @click="showCreate = true">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round">
          <rect x="3" y="3" width="18" height="18" rx="3"/>
          <line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/>
        </svg>
        <p class="empty-title">新建第一个短剧项目</p>
        <p class="empty-desc">从剧本到成片，AI 助力的短剧制作工作台</p>
      </div>
    </div>

    <!-- 新建弹窗 -->
    <div v-if="showCreate" class="overlay" @click.self="showCreate = false">
      <div class="modal">
        <h2 class="modal-title">新建短剧项目</h2>
        <p class="modal-desc">输入项目基本信息，即可开始制作</p>
        <form @submit.prevent="createDrama" class="modal-form">
          <label class="field">
            <span class="field-label">项目名称 <span class="required">*</span></span>
            <input v-model="form.title" class="field-input" placeholder="例如：都市情感短剧《时光邮局》" required autofocus />
          </label>
          <div class="field-row">
            <label class="field">
              <span class="field-label">计划集数</span>
              <input v-model.number="form.total_episodes" class="field-input" type="number" min="1" max="100" />
            </label>
            <label class="field">
              <span class="field-label">视觉风格</span>
              <select v-model="form.style" class="field-input">
                <option value="">不指定</option>
                <option v-for="s in styles" :key="s" :value="s">{{ s }}</option>
              </select>
            </label>
          </div>
          <div class="modal-actions">
            <button type="button" class="btn-ghost" @click="showCreate = false">取消</button>
            <button type="submit" class="btn-primary">创建项目</button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

const router = useRouter()
const BASE = '/api/api-proxy'

const dramas = ref<any[]>([])
const loading = ref(false)
const showCreate = ref(false)
const form = ref({ title: '', total_episodes: 1, style: '' })
const styles = ['realistic', 'anime', 'ghibli', 'cinematic', 'comic', 'watercolor']

async function load() {
  loading.value = true
  try {
    const res = await fetch(`${BASE}/dramas`)
    const data = await res.json()
    dramas.value = data.items || []
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function createDrama() {
  if (!form.value.title.trim()) return
  try {
    const res = await fetch(`${BASE}/dramas`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(form.value),
    })
    const d = await res.json()
    showCreate.value = false
    form.value = { title: '', total_episodes: 1, style: '' }
    router.push(`/drama/${d.id}`)
  } catch (e: any) {
    ElMessage.error(e.message)
  }
}

async function delDrama(d: any) {
  try {
    await ElMessageBox.confirm(`确定删除「${d.title}」？此操作不可恢复。`, '提示', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
    await fetch(`${BASE}/dramas/${d.id}`, { method: 'DELETE' })
    ElMessage.success('已删除')
    load()
  } catch {
    // 取消
  }
}

function fmtDate(s: string) {
  if (!s) return ''
  const d = new Date(s)
  const diff = Date.now() - d.getTime()
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  if (diff < 604800000) return `${Math.floor(diff / 86400000)} 天前`
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

onMounted(load)
</script>

<style scoped>
.drama-page {
  padding: 28px 48px 40px;
  overflow-y: auto;
  height: 100%;
}

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 28px;
}
.head-left { display: flex; flex-direction: column; gap: 4px; }
.page-title { font-size: 26px; font-weight: 700; letter-spacing: -0.02em; color: #fff; margin: 0; }
.page-desc { font-size: 13px; color: rgba(255,255,255,0.4); margin: 0; }

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 20px;
}

.project-card {
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: transform 0.22s ease, box-shadow 0.22s ease, border-color 0.2s;
}
.project-card:hover {
  border-color: rgba(255,255,255,0.82);
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  transform: translateY(-3px);
}

.card-film-strip {
  display: flex;
  justify-content: space-around;
  align-items: center;
  padding: 6px 16px;
  background: rgba(255,255,255,0.03);
  border-bottom: 1px solid rgba(255,255,255,0.06);
}
.film-hole {
  width: 10px; height: 8px;
  background: rgba(255,255,255,0.08);
  border-radius: 2px;
  transition: background 0.2s;
}
.project-card:hover .film-hole:nth-child(2) { background: rgba(255,255,255,0.14); }
.project-card:hover .film-hole:nth-child(4) { background: rgba(255,255,255,0.5); }

.card-body { padding: 18px 18px 14px; flex: 1; display: flex; flex-direction: column; gap: 10px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.episode-badge {
  display: flex; align-items: center; gap: 5px;
  font-size: 11px; font-weight: 600; color: rgba(255,255,255,0.4); letter-spacing: 0.04em;
}
.episode-badge svg { color: rgba(255,255,255,0.82); }

.btn-ghost-icon {
  background: none; border: none; cursor: pointer; padding: 4px;
  color: rgba(255,255,255,0.3); border-radius: 4px; opacity: 0;
  transition: opacity 0.15s, color 0.15s, background 0.15s;
}
.project-card:hover .btn-ghost-icon { opacity: 1; }
.btn-ghost-icon:hover { color: #f87171; background: rgba(248,113,113,0.1); }

.project-title { font-size: 16px; font-weight: 600; color: #fff; margin: 0; line-height: 1.35; }

.project-meta { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.style-tag {
  font-size: 11px; font-weight: 500; padding: 2px 8px;
  background: rgba(255,255,255,0.12); color: rgba(255,255,255,0.82); border-radius: 99px;
  border: 1px solid rgba(255,255,255,0.2);
}
.meta-item { display: flex; align-items: center; gap: 4px; font-size: 12px; color: rgba(255,255,255,0.4); }

.card-footer {
  padding: 10px 18px 14px;
  border-top: 1px solid rgba(255,255,255,0.06);
}
.card-date { font-size: 11px; color: rgba(255,255,255,0.3); }

.skeleton-card {
  height: 180px; border-radius: 12px;
  background: linear-gradient(90deg, rgba(255,255,255,0.04) 25%, rgba(255,255,255,0.08) 50%, rgba(255,255,255,0.04) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }

.empty-card {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 10px; padding: 56px 32px;
  cursor: pointer;
  background: rgba(255,255,255,0.02);
  border: 1.5px dashed rgba(255,255,255,0.12);
  border-radius: 12px;
  text-align: center;
  color: rgba(255,255,255,0.3);
  transition: all 0.2s ease;
}
.empty-card:hover { border-color: rgba(255,255,255,0.82); background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.82); transform: translateY(-2px); }
.empty-title { font-size: 14px; font-weight: 600; color: rgba(255,255,255,0.7); margin: 0; }
.empty-desc { font-size: 12px; color: rgba(255,255,255,0.35); max-width: 220px; line-height: 1.6; margin: 0; }

/* modal */
.overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 200;
  display: flex; align-items: center; justify-content: center;
}
.modal {
  background: #1a1a1d; border: 1px solid rgba(255,255,255,0.1);
  border-radius: 16px; padding: 32px; width: 460px;
  box-shadow: 0 24px 64px rgba(0,0,0,0.6);
}
.modal-title { font-size: 19px; font-weight: 700; color: #fff; margin: 0 0 6px; }
.modal-desc { font-size: 13px; color: rgba(255,255,255,0.4); margin: 0 0 24px; }
.modal-form { display: flex; flex-direction: column; gap: 16px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field-label { font-size: 12px; font-weight: 600; color: rgba(255,255,255,0.7); }
.required { color: #f87171; }
.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.field-input {
  background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);
  border-radius: 8px; padding: 8px 12px; color: #fff; font-size: 13px;
  outline: none; transition: border-color 0.2s;
}
.field-input:focus { border-color: rgba(255,255,255,0.82); }
.field-input option { background: #1a1a1d; }
.modal-actions { display: flex; justify-content: flex-end; gap: 10px; padding-top: 6px; }

/* buttons */
.btn-primary {
  display: flex; align-items: center; gap: 6px;
  background: rgba(255,255,255,0.14); color: #fff; border: none;
  border-radius: 8px; padding: 8px 16px; font-size: 13px; font-weight: 500;
  cursor: pointer; transition: background 0.2s;
}
.btn-primary:hover { background: rgba(255,255,255,0.14); }
.btn-ghost {
  background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.7);
  border: 1px solid rgba(255,255,255,0.1); border-radius: 8px;
  padding: 8px 16px; font-size: 13px; cursor: pointer; transition: background 0.2s;
}
.btn-ghost:hover { background: rgba(255,255,255,0.1); }

/* 统一为参数面板的玻璃风格 */
.project-card {
  background: linear-gradient(180deg, rgba(25, 29, 39, 0.5), rgba(6, 8, 13, 0.34));
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-soft);
  backdrop-filter: var(--glass-blur);
}
.project-card:hover {
  border-color: rgba(255,255,255,0.24);
  background: linear-gradient(180deg, rgba(32, 37, 49, 0.54), rgba(8, 10, 16, 0.4));
  box-shadow: var(--shadow-lift);
}
.card-film-strip {
  display: none;
}
.episode-badge,
.style-tag,
.meta-item {
  color: var(--color-muted);
}
.episode-badge svg {
  color: var(--color-muted);
}
.style-tag {
  background: rgba(255,255,255,0.08);
  border: 1px solid var(--color-border);
}
.card-footer {
  border-top: 1px solid var(--color-border);
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
.empty-card {
  background: linear-gradient(180deg, rgba(25, 29, 39, 0.42), rgba(6, 8, 13, 0.3));
  border-color: var(--color-border);
  backdrop-filter: var(--glass-blur);
}
.empty-card:hover {
  border-color: rgba(255,255,255,0.24);
  background: rgba(255,255,255,0.08);
  color: var(--color-text);
}
.modal {
  background: rgba(9, 12, 18, 0.78);
  border: 1px solid var(--color-border);
  backdrop-filter: var(--glass-blur);
  box-shadow: var(--shadow-lift);
}
.field-input:focus {
  border-color: var(--color-border);
}
</style>
