<script setup lang="ts">
import { useSlots } from 'vue'
import { ElMessage } from 'element-plus'
import { prioritizeTask } from '../api/apiService'

interface Record {
  id: string
  status: 'generating' | 'done' | 'error'
  taskId?: string
  createdAt: number
  modelName: string
  errorMsg?: string
}

const props = withDefaults(defineProps<{
  record: Record
  showEditButton?: boolean
}>(), {
  showEditButton: true,
})
const emit = defineEmits<{
  (e: 'delete', id: string): void
  (e: 'retry', record: Record): void
  (e: 'edit', id: string): void
}>()

const slots = useSlots()

async function handlePrioritize() {
  if (!props.record.taskId) return
  try {
    const userStr = localStorage.getItem('user')
    const userId = userStr ? JSON.parse(userStr).id : undefined
    await prioritizeTask(props.record.taskId, userId)
    ElMessage.success('已插队，任务将优先处理')
  } catch (e: any) {
    ElMessage.error(e.message || '插队失败')
  }
}

function formatTime(ts: number): string {
  const d = new Date(ts)
  const pad = (n: number) => String(n).padStart(2, '0')
  return (d.getMonth() + 1) + '/' + d.getDate() + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes())
}
</script>

<template>
  <div class="record-card" :class="record.status">
    <div class="card-body">
      <!-- 左侧：输入图列（随卡片滚动） -->
      <div v-if="slots.input" class="card-input-col">
        <slot name="input" />
      </div>

      <!-- 右侧：主内容 -->
      <div class="card-main-col">
        <!-- 卡片头部 -->
        <div class="card-header">
          <div class="card-header-left">
            <span class="card-time">{{ formatTime(record.createdAt) }}</span>
            <span class="card-model">{{ record.modelName }}</span>
          </div>
          <div class="card-header-actions">
            <button
              v-if="record.status === 'done' && showEditButton"
              class="card-edit-btn"
              @click="emit('edit', record.id)"
              title="编辑并继续生图"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M12 19l7-7-3-3-7 7v3h3z"/>
                <path d="M18 13l1.5-1.5a2.12 2.12 0 0 0-3-3L15 10"/>
              </svg>
              编辑
            </button>
            <button class="card-delete-btn" @click="emit('delete', record.id)" title="删除">×</button>
          </div>
        </div>

        <!-- meta slot（参数标签等） -->
        <slot name="meta" />

        <!-- prompt slot -->
        <slot name="prompt" />

        <!-- 生成中 -->
        <div v-if="record.status === 'generating'" class="card-generating">
          <div class="breath-ring" />
          <div class="generating-content">
            <slot name="progress">
              <span class="loading-text">生成中...</span>
            </slot>
          </div>
          <button v-if="record.taskId" class="prioritize-btn" @click="handlePrioritize">插队</button>
        </div>

        <!-- 错误 -->
        <div v-else-if="record.status === 'error'" class="card-error">
          <span class="error-text">{{ record.errorMsg || '生成失败' }}</span>
          <button class="retry-btn" @click="emit('retry', record)">重试</button>
        </div>

        <!-- 结果 -->
        <div v-else-if="record.status === 'done'">
          <slot name="result" />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.record-card {
  background: linear-gradient(180deg, rgba(32, 36, 48, 0.42), rgba(7, 9, 15, 0.28));
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  transition: border-color 0.2s, transform 0.2s, box-shadow 0.2s;
  backdrop-filter: blur(18px);
  box-shadow: 0 12px 38px rgba(0, 0, 0, 0.2);
}
.record-card:hover {
  border-color: rgba(255, 255, 255, 0.24);
  transform: translateY(-2px);
  box-shadow: var(--shadow-soft);
}
.record-card.generating {
  border-color: rgba(166, 231, 226, 0.3);
}
.record-card.error {
  border-color: rgba(248, 113, 113, 0.28);
}

.card-body {
  display: flex;
  min-height: 0;
}

/* 左侧输入图列 */
.card-input-col {
  flex: 0 0 40%;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  padding: 12px;
  border-right: 1px solid var(--color-border);
  background: rgba(0, 0, 0, 0.14);
}

/* 右侧主内容 */
.card-main-col {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px 20px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.card-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.card-header-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
.card-time {
  font-size: 11px;
  color: var(--color-faint);
  letter-spacing: 0;
}
.card-model {
  font-size: 11px;
  color: var(--color-muted);
  background: rgba(255, 255, 255, 0.06);
  padding: 2px 8px;
  border-radius: 6px;
  border: 1px solid var(--color-border);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-edit-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid var(--color-border);
  color: var(--color-muted);
  font-size: 11px;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s, color 0.2s, transform 0.2s;
  flex-shrink: 0;
}
.card-edit-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.24);
  color: var(--color-text);
  transform: translateY(-1px);
}
.card-delete-btn {
  width: 24px;
  height: 24px;
  padding: 0 0 2px;
  border-radius: 50%;
  background: none;
  border: 1px solid var(--color-border);
  color: var(--color-faint);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.2s, border-color 0.2s, color 0.2s;
  flex-shrink: 0;
}
.card-delete-btn:hover {
  background: rgba(248, 113, 113, 0.15);
  border-color: rgba(248, 113, 113, 0.3);
  color: var(--color-danger);
}

/* 生成中 */
.card-generating {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}
.breath-ring {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 2px solid rgba(166, 231, 226, 0.5);
  flex-shrink: 0;
  animation: breathe-ring 2s ease-in-out infinite;
}
@keyframes breathe-ring {
  0%, 100% { border-color: rgba(166, 231, 226, 0.42); transform: scale(1); }
  50% { border-color: rgba(255, 255, 255, 0.72); transform: scale(1.08); }
}
.generating-content {
  flex: 1;
  min-width: 0;
}
.loading-text {
  font-size: 12px;
  color: var(--color-muted);
  letter-spacing: 0;
}
.prioritize-btn {
  padding: 4px 12px;
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.07);
  border: 1px solid rgba(255, 255, 255, 0.16);
  color: var(--color-primary);
  font-size: 11px;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s, color 0.2s;
  flex-shrink: 0;
}
.prioritize-btn:hover {
  background: rgba(255, 255, 255, 0.14);
  border-color: rgba(255, 255, 255, 0.28);
}

/* 错误 */
.card-error {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: rgba(248, 113, 113, 0.06);
  border-radius: var(--radius-sm);
  border: 1px solid rgba(248, 113, 113, 0.12);
}
.error-text {
  flex: 1;
  font-size: 12px;
  color: var(--color-danger);
  word-break: break-all;
}
.retry-btn {
  padding: 4px 12px;
  border-radius: var(--radius-sm);
  background: rgba(248, 113, 113, 0.1);
  border: 1px solid rgba(248, 113, 113, 0.25);
  color: var(--color-danger);
  font-size: 11px;
  cursor: pointer;
  transition: background 0.2s;
  flex-shrink: 0;
}
.retry-btn:hover {
  background: rgba(248, 113, 113, 0.2);
}
</style>
