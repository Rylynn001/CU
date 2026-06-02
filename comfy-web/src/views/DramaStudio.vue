<template>
  <div class="studio" v-if="episode">
    <header class="topbar">
      <div class="topbar-left">
        <button class="back-btn" @click="router.push(`/drama/${dramaId}`)">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round">
            <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
          </svg>
          返回项目
        </button>
        <div class="studio-identity">
          <h1 class="studio-title">{{ episode.title }}</h1>
          <span class="episode-chip">第 {{ episodeNum }} 集</span>
        </div>
      </div>
      <button class="btn-sm" @click="load">刷新</button>
    </header>

    <div class="studio-body">
      <aside class="sidebar">
        <nav class="pipeline">
          <div v-for="section in sidebarSections" :key="section.id" class="pipe-section">
            <div class="pipe-section-label">{{ section.label }}</div>
            <button
              v-for="item in section.items"
              :key="item.key"
              :class="['pipe-item', { active: activeKey === item.key, done: item.done }]"
              @click="activeKey = item.key"
            >
              <span class="pipe-icon">
                <svg v-if="item.done" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><polyline points="20 6 9 17 4 12"/></svg>
                <span v-else class="pipe-dot" />
              </span>
              <span class="pipe-copy">
                <span class="pipe-label">{{ item.label }}</span>
                <span v-if="item.desc" class="pipe-sub">{{ item.desc }}</span>
              </span>
            </button>
          </div>
        </nav>
      </aside>

      <main class="main">
        <!-- 原始内容 -->
        <div v-if="activeKey === 'raw'" class="content-panel">
          <div class="panel-toolbar">
            <div class="step-indicator">
              <span class="step-num">01</span>
              <span class="step-name">原始内容</span>
            </div>
            <div class="toolbar-right">
              <span v-if="localRaw" class="char-count">{{ localRaw.length }} 字</span>
              <button class="btn-sm btn-accent" @click="saveRaw">保存</button>
            </div>
          </div>
          <textarea class="fill-textarea" v-model="localRaw" placeholder="粘贴小说原文、故事大纲或分镜描述..." />
        </div>

        <!-- AI 改写 -->
        <div v-else-if="activeKey === 'rewrite'" class="content-panel">
          <div class="panel-toolbar">
            <div class="step-indicator">
              <span class="step-num">02</span>
              <span class="step-name">AI 改写</span>
            </div>
            <div class="toolbar-right">
              <button class="btn-sm" @click="doRewrite" :disabled="running">
                {{ episode.script_content ? '重新改写' : '开始改写' }}
              </button>
              <button v-if="!episode.script_content" class="btn-sm" @click="skipRewrite">跳过改写</button>
            </div>
          </div>
          <div v-if="running && runningType === 'rewrite'" class="step-loading">
            <svg class="spin" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
            <div class="loading-text">正在改写剧本...</div>
          </div>
          <div v-else-if="!episode.script_content" class="step-empty">
            <div class="empty-title">AI 改写为格式化剧本</div>
            <div class="empty-desc">可以先用 AI 把原始内容整理成格式化剧本，也可以跳过直接提取角色与场景</div>
            <div class="empty-actions">
              <button class="btn-primary" @click="doRewrite">开始改写</button>
              <button class="btn-ghost" @click="skipRewrite">跳过改写</button>
            </div>
          </div>
          <textarea v-else class="fill-textarea" v-model="localScript" />
        </div>

        <!-- 提取 -->
        <div v-else-if="activeKey === 'extract'" class="content-panel">
          <div class="panel-toolbar">
            <div class="step-indicator">
              <span class="step-num">03</span>
              <span class="step-name">提取角色与场景</span>
            </div>
            <div class="toolbar-right">
              <span v-if="chars.length" class="char-count">{{ chars.length }} 角色 · {{ scenes.length }} 场景</span>
              <button class="btn-sm" @click="doExtract" :disabled="running">
                {{ chars.length ? '重新提取' : '开始提取' }}
              </button>
            </div>
          </div>
          <div v-if="running && runningType === 'extract'" class="step-loading">
            <svg class="spin" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
            <div class="loading-text">正在提取角色和场景...</div>
            <div class="loading-events">
              <div v-for="(ev, i) in agentEvents" :key="i" class="event-line">{{ ev }}</div>
            </div>
          </div>
          <div v-else-if="!chars.length" class="step-empty">
            <div class="empty-title">从剧本提取角色与场景</div>
            <div class="empty-desc">AI 自动分析剧本，提取角色信息和场景列表，与项目已有数据智能去重合并</div>
            <button class="btn-primary" @click="doExtract">开始提取</button>
          </div>
          <div v-else class="extract-stage">
            <div class="card extract-summary">
              <div class="summary-kicker">Extraction Board</div>
              <div class="summary-title">角色与场景结果</div>
              <div class="summary-stats">
                <div class="summary-stat"><span>角色</span><strong>{{ chars.length }}</strong></div>
                <div class="summary-stat"><span>场景</span><strong>{{ scenes.length }}</strong></div>
              </div>
            </div>
            <div class="card extract-card">
              <div class="extract-head">
                角色 <span class="tag">{{ chars.length }}</span>
              </div>
              <div class="extract-list">
                <div v-for="c in chars" :key="c.id" class="extract-row">
                  <div class="char-avatar">{{ c.name?.[0] || '?' }}</div>
                  <div class="extract-info">
                    <div class="extract-name-row">
                      <span class="extract-name">{{ c.name }}</span>
                      <span class="tag">{{ c.role || '角色' }}</span>
                    </div>
                    <div class="extract-meta">{{ c.description || c.appearance || '暂无描述' }}</div>
                  </div>
                </div>
              </div>
            </div>
            <div class="card extract-card" v-if="scenes.length">
              <div class="extract-head">
                场景 <span class="tag">{{ scenes.length }}</span>
              </div>
              <div class="extract-list">
                <div v-for="s in scenes" :key="s.id" class="extract-row">
                  <div class="scene-dot" />
                  <div class="extract-info">
                    <div class="extract-name-row">
                      <span class="extract-name">{{ s.location }}</span>
                      <span v-if="s.time" class="tag">{{ s.time }}</span>
                    </div>
                    <div class="extract-meta">{{ s.prompt || '等待补充场景描述' }}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  </div>

  <div v-else-if="loading" class="loading-full">
    <svg class="spin" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'

const router = useRouter()
const route = useRoute()
const BASE = '/api/api-proxy'

const dramaId = Number(route.params.id)
const episodeNum = Number(route.params.num)

const episode = ref<any>(null)
const loading = ref(false)
const chars = ref<any[]>([])
const scenes = ref<any[]>([])
const localRaw = ref('')
const localScript = ref('')
const running = ref(false)
const runningType = ref<string | null>(null)
const agentEvents = ref<string[]>([])
const activeKey = ref('raw')

const sidebarSections = computed(() => [
  {
    id: 'script',
    label: '剧本',
    items: [
      { key: 'raw',     label: '原始内容', desc: localRaw.value ? `${localRaw.value.length} 字` : '', done: !!localRaw.value },
      { key: 'rewrite', label: 'AI 改写',  desc: '', done: !!episode.value?.script_content },
      { key: 'extract', label: '提取角色与场景', desc: chars.value.length ? `${chars.value.length} 角色` : '', done: chars.value.length > 0 },
    ],
  },
])

async function load() {
  loading.value = true
  try {
    const res = await fetch(`${BASE}/dramas/${dramaId}/episodes/${episodeNum}`)
    if (!res.ok) throw new Error('加载失败')
    episode.value = await res.json()
    localRaw.value = episode.value.content || ''
    localScript.value = episode.value.script_content || ''

    // 加载角色和场景
    const [cRes, sRes] = await Promise.all([
      fetch(`${BASE}/episodes/${episode.value.id}/characters`),
      fetch(`${BASE}/episodes/${episode.value.id}/scenes`),
    ])
    chars.value = (await cRes.json()).items || []
    scenes.value = (await sRes.json()).items || []

    // 自动跳转到最近的步骤
    if (chars.value.length) activeKey.value = 'extract'
    else if (episode.value.script_content) activeKey.value = 'rewrite'
    else activeKey.value = 'raw'
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function saveRaw() {
  if (!episode.value) return
  await fetch(`${BASE}/episodes/${episode.value.id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content: localRaw.value }),
  })
  episode.value.content = localRaw.value
  ElMessage.success('已保存')
}

async function skipRewrite() {
  if (!episode.value) return
  await fetch(`${BASE}/episodes/${episode.value.id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ script_content: localRaw.value }),
  })
  episode.value.script_content = localRaw.value
  localScript.value = localRaw.value
  activeKey.value = 'extract'
  ElMessage.success('已跳过改写，内容已同步')
}

async function doRewrite() {
  if (!episode.value) return
  running.value = true
  runningType.value = 'rewrite'
  try {
    // script_rewriter agent — 暂未实现后端，占位
    ElMessage.warning('script_rewriter agent 尚未接入，请手动编辑或跳过改写')
  } finally {
    running.value = false
    runningType.value = null
  }
}

async function doExtract() {
  if (!episode.value) return
  running.value = true
  runningType.value = 'extract'
  agentEvents.value = []
  try {
    const res = await fetch(`${BASE}/agent/extract`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ episode_id: episode.value.id, drama_id: dramaId }),
    })
    if (!res.ok || !res.body) throw new Error('请求失败')

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buf = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      const lines = buf.split('\n')
      buf = lines.pop() || ''
      for (const line of lines) {
        if (line.startsWith('event: tool_start')) continue
        if (line.startsWith('data: ')) {
          try {
            const d = JSON.parse(line.slice(6))
            if (d.tool) agentEvents.value.push(`调用工具：${d.tool}`)
            if (d.text) agentEvents.value.push(d.text.slice(0, 60))
            if (agentEvents.value.length > 20) agentEvents.value.shift()
          } catch { /**/ }
        }
      }
    }

    // 刷新结果
    const [cRes, sRes] = await Promise.all([
      fetch(`${BASE}/episodes/${episode.value.id}/characters`),
      fetch(`${BASE}/episodes/${episode.value.id}/scenes`),
    ])
    chars.value = (await cRes.json()).items || []
    scenes.value = (await sRes.json()).items || []
    ElMessage.success(`提取完成：${chars.value.length} 角色，${scenes.value.length} 场景`)
  } catch (e: any) {
    ElMessage.error(e.message)
  } finally {
    running.value = false
    runningType.value = null
  }
}

onMounted(load)
</script>

<style scoped>
.studio {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
  background: #0f0f1a;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  height: 52px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  flex-shrink: 0;
}
.topbar-left { display: flex; align-items: center; gap: 16px; }
.back-btn {
  display: flex; align-items: center; gap: 6px;
  background: none; border: none; cursor: pointer;
  color: rgba(255,255,255,0.35); font-size: 13px; padding: 0;
  transition: color 0.2s;
}
.back-btn:hover { color: rgba(255,255,255,0.75); }
.studio-identity { display: flex; align-items: center; gap: 10px; }
.studio-title { font-size: 15px; font-weight: 600; color: #fff; margin: 0; }
.episode-chip {
  font-size: 11px; padding: 2px 8px; border-radius: 99px;
  background: rgba(167,139,250,0.12); color: #c4b5fd;
  border: 1px solid rgba(167,139,250,0.2);
}

.studio-body { display: flex; flex: 1; overflow: hidden; }

/* sidebar */
.sidebar {
  width: 200px;
  flex-shrink: 0;
  border-right: 1px solid rgba(255,255,255,0.06);
  overflow-y: auto;
  padding: 16px 0;
}
.pipe-section { margin-bottom: 20px; }
.pipe-section-label {
  font-size: 10px; font-weight: 600; letter-spacing: 0.08em;
  color: rgba(255,255,255,0.25); text-transform: uppercase;
  padding: 0 16px 8px;
}
.pipe-item {
  width: 100%; display: flex; align-items: center; gap: 10px;
  padding: 8px 16px; background: none; border: none; cursor: pointer;
  text-align: left; transition: background 0.15s;
  border-left: 2px solid transparent;
}
.pipe-item:hover { background: rgba(255,255,255,0.04); }
.pipe-item.active {
  background: rgba(167,139,250,0.08);
  border-left-color: #a78bfa;
}
.pipe-icon {
  width: 16px; height: 16px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  color: rgba(255,255,255,0.3);
}
.pipe-item.done .pipe-icon { color: #4ade80; }
.pipe-item.active .pipe-icon { color: #a78bfa; }
.pipe-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.pipe-copy { display: flex; flex-direction: column; gap: 2px; }
.pipe-label { font-size: 13px; color: rgba(255,255,255,0.5); }
.pipe-item.active .pipe-label { color: #fff; font-weight: 500; }
.pipe-item.done .pipe-label { color: rgba(255,255,255,0.7); }
.pipe-sub { font-size: 11px; color: rgba(255,255,255,0.25); }

/* main */
.main { flex: 1; overflow-y: auto; }
.content-panel { display: flex; flex-direction: column; height: 100%; }

.panel-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 24px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  flex-shrink: 0;
}
.step-indicator { display: flex; align-items: center; gap: 8px; }
.step-num { font-size: 11px; font-weight: 700; color: #a78bfa; }
.step-name { font-size: 14px; font-weight: 600; color: #fff; }
.toolbar-right { display: flex; align-items: center; gap: 8px; }
.char-count { font-size: 12px; color: rgba(255,255,255,0.35); }

.fill-textarea {
  flex: 1; width: 100%; padding: 24px;
  background: transparent; border: none; outline: none;
  color: rgba(255,255,255,0.85); font-size: 14px; line-height: 1.7;
  resize: none; font-family: inherit;
}
.fill-textarea::placeholder { color: rgba(255,255,255,0.2); }

.step-empty {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 12px; color: rgba(255,255,255,0.3); padding: 40px;
}
.empty-title { font-size: 15px; font-weight: 600; color: rgba(255,255,255,0.7); margin: 0; }
.empty-desc { font-size: 13px; color: rgba(255,255,255,0.35); max-width: 360px; text-align: center; line-height: 1.6; margin: 0; }
.empty-actions { display: flex; gap: 10px; margin-top: 4px; }

.step-loading {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  gap: 16px; color: rgba(255,255,255,0.5);
}
.loading-text { font-size: 14px; }
.loading-events {
  max-width: 400px; width: 100%; max-height: 160px; overflow: hidden;
  display: flex; flex-direction: column; gap: 4px;
}
.event-line { font-size: 12px; color: rgba(255,255,255,0.35); font-family: monospace; }

/* extract */
.extract-stage { padding: 24px; display: flex; flex-direction: column; gap: 16px; }
.card {
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 12px; padding: 20px;
}
.extract-summary { display: flex; flex-direction: column; gap: 8px; }
.summary-kicker { font-size: 10px; font-weight: 600; letter-spacing: 0.1em; color: rgba(255,255,255,0.25); text-transform: uppercase; }
.summary-title { font-size: 16px; font-weight: 700; color: #fff; }
.summary-stats { display: flex; gap: 24px; }
.summary-stat { display: flex; flex-direction: column; gap: 2px; }
.summary-stat span { font-size: 12px; color: rgba(255,255,255,0.4); }
.summary-stat strong { font-size: 22px; font-weight: 700; color: #a78bfa; }
.extract-card { padding: 16px; }
.extract-head {
  display: flex; align-items: center; gap: 8px;
  font-size: 13px; font-weight: 600; color: rgba(255,255,255,0.7);
  margin-bottom: 12px;
}
.tag {
  font-size: 11px; padding: 1px 6px; border-radius: 99px;
  background: rgba(167,139,250,0.12); color: #c4b5fd;
}
.extract-list { display: flex; flex-direction: column; gap: 10px; }
.extract-row { display: flex; align-items: flex-start; gap: 10px; }
.char-avatar {
  width: 32px; height: 32px; border-radius: 8px; flex-shrink: 0;
  background: rgba(167,139,250,0.12); color: #a78bfa;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; font-weight: 600;
}
.scene-dot {
  width: 32px; height: 32px; border-radius: 8px; flex-shrink: 0;
  background: rgba(74,222,128,0.1); border: 1px solid rgba(74,222,128,0.2);
}
.extract-info { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.extract-name-row { display: flex; align-items: center; gap: 8px; }
.extract-name { font-size: 14px; font-weight: 600; color: #fff; }
.extract-meta { font-size: 12px; color: rgba(255,255,255,0.4); line-height: 1.5; }

/* buttons */
.btn-sm {
  display: flex; align-items: center; gap: 5px;
  background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.7);
  border: 1px solid rgba(255,255,255,0.1); border-radius: 6px;
  padding: 5px 12px; font-size: 12px; cursor: pointer; transition: background 0.2s;
}
.btn-sm:hover { background: rgba(255,255,255,0.1); }
.btn-sm:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-sm.btn-accent { background: rgba(167,139,250,0.12); border-color: rgba(167,139,250,0.2); color: #c4b5fd; }
.btn-sm.btn-accent:hover { background: rgba(167,139,250,0.2); }
.btn-primary {
  display: flex; align-items: center; gap: 6px;
  background: #7c3aed; color: #fff; border: none;
  border-radius: 8px; padding: 8px 16px; font-size: 13px; font-weight: 500;
  cursor: pointer; transition: background 0.2s;
}
.btn-primary:hover { background: #6d28d9; }
.btn-ghost {
  background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.7);
  border: 1px solid rgba(255,255,255,0.1); border-radius: 8px;
  padding: 8px 16px; font-size: 13px; cursor: pointer;
}
.btn-ghost:hover { background: rgba(255,255,255,0.1); }

.loading-full {
  display: flex; align-items: center; justify-content: center; height: 100%;
  color: rgba(255,255,255,0.4);
}
.spin { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
