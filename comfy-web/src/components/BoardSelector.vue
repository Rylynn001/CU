<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import type { BoardMeta } from '../services/nodePanelStorage'

const router = useRouter()

const props = defineProps<{
  boards: BoardMeta[]
}>()

const emit = defineEmits<{
  enter: [id: number]
  create: [name: string]
  delete: [id: number]
  rename: [id: number, name: string]
}>()

const showCreate = ref(false)
const newName = ref('')
const editingId = ref<number | null>(null)
const editingName = ref('')

function fmtDate(ts: number) {
  if (!ts) return '暂未保存'
  return new Date(ts).toLocaleDateString('zh-CN', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

function confirmCreate() {
  const name = newName.value.trim() || `工作区 ${props.boards.length + 1}`
  emit('create', name)
  showCreate.value = false
  newName.value = ''
}

function startRename(b: BoardMeta) {
  editingId.value = b.id
  editingName.value = b.name
}
function submitRename() {
  const name = editingName.value.trim()
  if (name && editingId.value !== null) emit('rename', editingId.value, name)
  editingId.value = null
}
</script>

<template>
  <div class="bs-page">
    <!-- 右上角新建按钮（fixed 定位） -->
    <button class="btn-create" @click="showCreate = true">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
        <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
      </svg>
      新建工作区
    </button>

    <!-- 顶部 -->
    <header class="bs-header">
      <div class="bs-head-left">
        <button class="btn-back" @click="router.push('/')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round">
            <polyline points="15 18 9 12 15 6"/>
          </svg>
          首页
        </button>
        <h1 class="bs-title">节点面板</h1>
        <p class="bs-desc">{{ boards.length }} 个工作区</p>
      </div>
    </header>

    <!-- 卡片网格 -->
    <div class="bs-grid">
      <!-- 已有工作区 -->
      <div
        v-for="(b, i) in boards"
        :key="b.id"
        class="bs-card"
        :style="{ animationDelay: `${i * 0.05}s` }"
        @click="emit('enter', b.id)"
      >
        <!-- 装饰网格线 -->
        <div class="card-grid-deco" aria-hidden="true" />

        <div class="card-body">
          <div class="card-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
              <rect x="3" y="3" width="18" height="4" rx="1"/>
              <rect x="3" y="10" width="18" height="4" rx="1"/>
              <rect x="3" y="17" width="18" height="4" rx="1"/>
            </svg>
          </div>

          <!-- 名称（双击重命名） -->
          <template v-if="editingId === b.id">
            <input
              class="rename-input"
              v-model="editingName"
              @blur="submitRename"
              @keyup.enter="submitRename"
              @keyup.esc="editingId = null"
              @click.stop
              autofocus
            />
          </template>
          <h3 v-else class="card-name" @dblclick.stop="startRename(b)">{{ b.name }}</h3>

          <p class="card-date">最后保存：{{ fmtDate(b.updatedAt) }}</p>
        </div>

        <button class="card-del" @click.stop="emit('delete', b.id)" title="删除">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <!-- 空态 / 新建入口 -->
      <div class="bs-card bs-card-new" @click="showCreate = true">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round">
          <rect x="3" y="3" width="18" height="18" rx="3"/>
          <line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/>
        </svg>
        <p class="new-card-hint">新建工作区</p>
      </div>
    </div>

    <!-- 新建弹窗 -->
    <Transition name="overlay">
      <div v-if="showCreate" class="overlay" @click.self="showCreate = false">
        <div class="modal">
          <h2 class="modal-title">新建工作区</h2>
          <input
            v-model="newName"
            class="modal-input"
            placeholder="工作区名称（留空自动命名）"
            @keyup.enter="confirmCreate"
            autofocus
          />
          <div class="modal-actions">
            <button class="btn-cancel" @click="showCreate = false; newName = ''">取消</button>
            <button class="btn-confirm" @click="confirmCreate">创建</button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.bs-page {
  min-height: 100vh;
  padding: 48px 56px;
  animation: page-enter 0.4s ease both;
}

.bs-head-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.btn-back {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 12px 6px 8px;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.1);
  background: transparent;
  color: rgba(255,255,255,0.45);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
  align-self: flex-start;
  margin-bottom: 8px;
}
.btn-back:hover {
  background: rgba(255,255,255,0.06);
  color: rgba(255,255,255,0.8);
  border-color: rgba(255,255,255,0.2);
}
.bs-title {
  font-size: 26px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.9);
  letter-spacing: -0.5px;
}
.bs-desc {
  margin-top: 6px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.35);
}
.btn-create {
  position: fixed;
  top: 20px;
  right: 28px;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 10px 20px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.85);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.btn-create:hover {
  background: rgba(255, 255, 255, 0.14);
  border-color: rgba(255, 255, 255, 0.28);
  color: #fff;
}

/* ── 卡片网格 ── */
.bs-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 18px;
}

.bs-card {
  position: relative;
  border: 1px solid var(--color-border);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.035);
  overflow: hidden;
  cursor: pointer;
  animation: card-in 0.35s ease both;
  transition: border-color 0.2s, background 0.2s, transform 0.15s;
  min-height: 150px;
}
.bs-card:hover {
  border-color: rgba(255, 255, 255, 0.22);
  background: rgba(255, 255, 255, 0.065);
  transform: translateY(-2px);
}

/* 装饰网格线 */
.card-grid-deco {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255,255,255,0.04) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.04) 1px, transparent 1px);
  background-size: 28px 28px;
  pointer-events: none;
}

.card-body {
  padding: 22px 20px 18px;
}
.card-icon {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.5);
  margin-bottom: 14px;
}
.card-name {
  font-size: 15px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.85);
  margin-bottom: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-date {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.28);
}

.rename-input {
  width: 100%;
  background: rgba(255,255,255,0.08);
  border: 1px solid rgba(255,255,255,0.24);
  border-radius: 6px;
  color: rgba(255,255,255,0.9);
  font-size: 14px;
  padding: 4px 8px;
  outline: none;
  margin-bottom: 8px;
}

.card-del {
  position: absolute;
  top: 10px;
  right: 10px;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: rgba(255,255,255,0.2);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: all 0.18s;
}
.bs-card:hover .card-del { opacity: 1; }
.card-del:hover { background: rgba(244,63,94,0.2); color: #f43f5e; }

/* 新建卡片 */
.bs-card-new {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  border-style: dashed;
  border-color: rgba(255,255,255,0.12);
  color: rgba(255,255,255,0.28);
  background: transparent;
}
.bs-card-new:hover {
  border-color: rgba(255,255,255,0.24);
  color: rgba(255,255,255,0.5);
  background: rgba(255,255,255,0.02);
}
.new-card-hint {
  font-size: 13px;
}

/* ── 新建弹窗 ── */
.overlay {
  position: fixed;
  inset: 0;
  z-index: 500;
  background: rgba(0,0,0,0.6);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
}
.modal {
  width: 360px;
  padding: 28px 28px 24px;
  border-radius: 18px;
  border: 1px solid rgba(255,255,255,0.12);
  background: rgba(20,22,28,0.98);
  box-shadow: 0 24px 64px rgba(0,0,0,0.5);
}
.modal-title {
  font-size: 16px;
  font-weight: 500;
  color: rgba(255,255,255,0.9);
  margin-bottom: 18px;
}
.modal-input {
  width: 100%;
  box-sizing: border-box;
  padding: 11px 14px;
  border-radius: 10px;
  border: 1px solid rgba(255,255,255,0.14);
  background: rgba(255,255,255,0.05);
  color: rgba(255,255,255,0.85);
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
  margin-bottom: 20px;
}
.modal-input:focus { border-color: rgba(255,255,255,0.3); }
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
.btn-cancel {
  padding: 8px 18px;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.1);
  background: transparent;
  color: rgba(255,255,255,0.45);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-cancel:hover { background: rgba(255,255,255,0.05); color: rgba(255,255,255,0.75); }
.btn-confirm {
  padding: 8px 22px;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.22);
  background: rgba(255,255,255,0.1);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-confirm:hover { background: rgba(255,255,255,0.18); }

/* ── 动画 ── */
@keyframes page-enter {
  from { opacity: 0; transform: translateY(16px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes card-in {
  from { opacity: 0; transform: translateY(10px); }
  to   { opacity: 1; transform: translateY(0); }
}
.overlay-enter-active { transition: opacity 0.2s ease; }
.overlay-leave-active { transition: opacity 0.15s ease; }
.overlay-enter-from, .overlay-leave-to { opacity: 0; }
</style>
