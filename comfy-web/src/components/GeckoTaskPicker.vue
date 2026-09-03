<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

interface GeckoTask {
  task_id: number
  project_name: string
  task_name: string
  task_type: string
  eps_name?: string
  shot?: string
}

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'select', task: GeckoTask): void
}>()

const tasks = ref<GeckoTask[]>([])
const loading = ref(false)
const selectedTask = ref<GeckoTask | null>(null)

watch(() => props.visible, (val) => {
  if (val) {
    loadTasks()
  } else {
    selectedTask.value = null
  }
})

async function loadTasks() {
  loading.value = true
  try {
    const res = await fetch('/api/api-proxy/gecko/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page: 1 }),
    })
    const data = await res.json()
    if (!data.success) {
      ElMessage.error(data.message || '获取任务失败')
      return
    }
    tasks.value = data.data_list || []
  } catch (e: any) {
    ElMessage.error('获取任务失败')
  } finally {
    loading.value = false
  }
}

function selectTask(task: GeckoTask) {
  selectedTask.value = task
}

function confirm() {
  if (!selectedTask.value) {
    ElMessage.warning('请选择任务')
    return
  }
  emit('select', selectedTask.value)
  close()
}

function close() {
  emit('update:visible', false)
}
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog">
      <div v-if="visible" class="dialog-overlay" @click="close">
        <div class="dialog-content" @click.stop>
          <div class="dialog-header">
            <span class="dialog-title">选择 Gecko 任务</span>
            <button class="dialog-close" @click="close">✕</button>
          </div>

          <div class="dialog-body">
            <div v-if="loading" class="center-state">
              <div class="mini-spin" />
            </div>
            <div v-else-if="tasks.length === 0" class="center-state">
              <p class="empty-hint">暂无任务</p>
            </div>
            <div v-else class="task-list">
              <div
                v-for="task in tasks"
                :key="task.task_id"
                class="task-item"
                :class="{ selected: selectedTask?.task_id === task.task_id }"
                @click="selectTask(task)"
              >
                <div class="task-info">
                  <span class="task-name">{{ task.task_name }}</span>
                  <span class="task-meta">{{ task.project_name }}</span>
                  <span v-if="task.eps_name || task.shot" class="task-meta">
                    {{ task.eps_name ? `场次: ${task.eps_name}` : '' }}
                    {{ task.shot ? ` · 镜头: ${task.shot}` : '' }}
                  </span>
                </div>
              </div>
            </div>
          </div>

          <div class="dialog-footer">
            <button class="dialog-btn cancel" @click="close">取消</button>
            <button class="dialog-btn confirm" @click="confirm">确认</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 4000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(8px);
}

.dialog-content {
  width: min(90%, 500px);
  max-height: 70vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 16px;
  background: rgba(25, 25, 30, 0.98);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

.dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}

.dialog-title {
  font-size: 15px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.9);
}

.dialog-close {
  width: 28px;
  height: 28px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 50%;
  background: transparent;
  color: rgba(255, 255, 255, 0.5);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.dialog-close:hover {
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.9);
}

.dialog-body {
  flex: 1;
  min-height: 300px;
  overflow-y: auto;
  padding: 16px 20px;
}

.dialog-body::-webkit-scrollbar { width: 6px; }
.dialog-body::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.16);
  border-radius: 3px;
}

.center-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
}

.mini-spin {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  border: 2px solid rgba(255, 255, 255, 0.14);
  border-top-color: rgba(255, 255, 255, 0.72);
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.empty-hint {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.3);
}

.task-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-item {
  padding: 12px 14px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.03);
  cursor: pointer;
  transition: all 0.2s;
}

.task-item:hover {
  border-color: rgba(255, 255, 255, 0.2);
  background: rgba(255, 255, 255, 0.06);
}

.task-item.selected {
  border-color: rgba(255, 255, 255, 0.32);
  background: rgba(255, 255, 255, 0.12);
}

.task-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.task-name {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.9);
  font-weight: 500;
}

.task-meta {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.4);
}

.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  flex-shrink: 0;
}

.dialog-btn {
  padding: 8px 20px;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.dialog-btn.cancel {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.6);
}

.dialog-btn.cancel:hover {
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.9);
}

.dialog-btn.confirm {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.24);
  color: rgba(255, 255, 255, 0.95);
}

.dialog-btn.confirm:hover {
  background: rgba(255, 255, 255, 0.18);
}

.dialog-enter-active,
.dialog-leave-active {
  transition: opacity 0.2s;
}

.dialog-enter-from,
.dialog-leave-to {
  opacity: 0;
}
</style>
