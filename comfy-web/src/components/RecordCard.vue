<script setup lang="ts">
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

const props = defineProps<{ record: Record }>()
const emit = defineEmits<{
  (e: 'delete', id: string): void
  (e: 'retry', record: Record): void
}>()

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
    <!-- 卡片头部 -->
    <div class="card-header">
      <div class="card-header-left">
        <span class="card-time">{{ formatTime(record.createdAt) }}</span>
        <span class="card-model">{{ record.modelName }}</span>
      </div>
      <button class="card-delete-btn" @click="emit('delete', record.id)" title="删除">×</button>
    </div>

    <!-- meta slot（参考图、视频参数等） -->
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
</template>

<style scoped>
.record-card {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 16px;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  transition: border-color 0.2s;
}
.record-card:hover {
  border-color: rgba(255, 255, 255, 0.12);
}
.record-card.generating {
  border-color: rgba(108, 99, 255, 0.2);
}
.record-card.error {
  border-color: rgba(248, 113, 113, 0.2);
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
.card-time {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.3);
  letter-spacing: 0.5px;
}
.card-model {
  font-size: 11px;
  color: rgba(167, 139, 250, 0.7);
  background: rgba(108, 99, 255, 0.1);
  padding: 2px 8px;
  border-radius: 6px;
  border: 1px solid rgba(108, 99, 255, 0.15);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-delete-btn {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: none;
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.3);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  flex-shrink: 0;
}
.card-delete-btn:hover {
  background: rgba(248, 113, 113, 0.15);
  border-color: rgba(248, 113, 113, 0.3);
  color: #f87171;
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
  border: 2px solid rgba(108, 99, 255, 0.5);
  flex-shrink: 0;
  animation: breathe-ring 2s ease-in-out infinite;
}
@keyframes breathe-ring {
  0%, 100% { border-color: rgba(108, 99, 255, 0.5); transform: scale(1); }
  50% { border-color: rgba(167, 139, 250, 0.8); transform: scale(1.08); }
}
.generating-content {
  flex: 1;
  min-width: 0;
}
.loading-text {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.35);
  letter-spacing: 1px;
}
.prioritize-btn {
  padding: 4px 12px;
  border-radius: 6px;
  background: rgba(108, 99, 255, 0.15);
  border: 1px solid rgba(108, 99, 255, 0.3);
  color: rgba(167, 139, 250, 0.9);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}
.prioritize-btn:hover {
  background: rgba(108, 99, 255, 0.3);
  border-color: rgba(108, 99, 255, 0.5);
}

/* 错误 */
.card-error {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: rgba(248, 113, 113, 0.06);
  border-radius: 8px;
  border: 1px solid rgba(248, 113, 113, 0.12);
}
.error-text {
  flex: 1;
  font-size: 12px;
  color: #f87171;
  word-break: break-all;
}
.retry-btn {
  padding: 4px 12px;
  border-radius: 6px;
  background: rgba(248, 113, 113, 0.1);
  border: 1px solid rgba(248, 113, 113, 0.25);
  color: #f87171;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
  flex-shrink: 0;
}
.retry-btn:hover {
  background: rgba(248, 113, 113, 0.2);
}
</style>
