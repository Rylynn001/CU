<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

interface Category {
  id: number
  name: string
  asset_count: number
}

interface Project {
  id: number
  name: string
  category_count: number
  categories?: Category[]   // 展开项目后按需加载
}

const props = defineProps<{
  visible: boolean
  mode: 'add' | 'move' | 'copy'  // 操作模式：添加、移动、复制
  assetId?: number
  title?: string
}>()

const emit = defineEmits<{
  close: []
  confirm: [projectId: number, categoryId: number]
}>()

const projects = ref<Project[]>([])
const selectedProjectId = ref<number | null>(null)
const selectedCategoryId = ref<number | null>(null)
const loadingProjects = ref(false)
const processing = ref(false)

const dialogTitle = props.title || (props.mode === 'add' ? '添加到项目' : props.mode === 'move' ? '移动到项目' : '复制到项目')

function getUser() {
  const s = localStorage.getItem('user')
  return s ? JSON.parse(s) : null
}

async function loadProjects() {
  const user = getUser()
  if (!user) return
  loadingProjects.value = true
  try {
    const res = await fetch(`/api/api-proxy/projects?user_id=${user.id}`)
    if (!res.ok) throw new Error()
    const data = await res.json()
    projects.value = data.projects || []
  } catch {
    ElMessage.error('加载项目失败')
  } finally {
    loadingProjects.value = false
  }
}

async function toggleProject(projectId: number) {
  if (selectedProjectId.value === projectId) {
    // 如果点击的是已展开的项目，则收起
    selectedProjectId.value = null
    selectedCategoryId.value = null
  } else {
    // 展开新项目，按需加载分类
    selectedProjectId.value = projectId
    selectedCategoryId.value = null
    const project = projects.value.find(p => p.id === projectId)
    if (project && !project.categories) await loadCategories(project)
  }
}

// 点击项目时按需加载分类
async function loadCategories(project: Project) {
  const user = getUser()
  if (!user) return
  try {
    const res = await fetch(`/api/api-proxy/projects/${project.id}/categories?user_id=${user.id}`)
    if (!res.ok) throw new Error()
    const data = await res.json()
    project.categories = data.categories || []
  } catch {
    project.categories = []
    ElMessage.error('加载分类失败')
  }
}

async function handleConfirm() {
  if (!selectedCategoryId.value || !selectedProjectId.value) {
    ElMessage.warning('请选择分类')
    return
  }

  if (!props.assetId) {
    // 如果没有传入 assetId，只返回选择结果
    emit('confirm', selectedProjectId.value, selectedCategoryId.value)
    handleClose()
    return
  }

  const user = getUser()
  if (!user) { ElMessage.error('请先登录'); return }

  processing.value = true
  try {
    const res = await fetch(`/api/api-proxy/categories/${selectedCategoryId.value}/assets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ asset_id: props.assetId, user_id: user.id }),
    })
    if (!res.ok) {
      if (res.status === 403) throw new Error('非项目成员，无法提交素材')
      throw new Error()
    }
    const data = await res.json()

    // member 提交进入待审核，提示区分
    if (data.review_status === 'pending') {
      ElMessage.success('已提交，等待管理员审核')
    } else {
      const message = props.mode === 'add' ? '已添加到分类' : props.mode === 'move' ? '已移动到分类' : '已复制到分类'
      ElMessage.success(message)
    }

    emit('confirm', selectedProjectId.value, selectedCategoryId.value)
    handleClose()
  } catch (e: any) {
    ElMessage.error(e.message || '操作失败')
  } finally {
    processing.value = false
  }
}

function handleClose() {
  emit('close')
  selectedProjectId.value = null
  selectedCategoryId.value = null
}

watch(() => props.visible, (newVal) => {
  if (newVal) {
    loadProjects()
  }
})
</script>

<template>
  <Teleport to="body">
    <Transition name="project-dialog">
      <div v-if="visible" class="dialog-overlay" @click="handleClose">
        <div class="dialog-content" @click.stop>
          <div class="dialog-header">
            <span class="dialog-title">{{ dialogTitle }}</span>
            <button class="dialog-close" @click="handleClose">✕</button>
          </div>

          <div class="dialog-body">
            <div v-if="loadingProjects" class="dialog-loading">
              <div class="mini-spinner" />
            </div>

            <div v-else-if="projects.length === 0" class="dialog-empty">
              暂无项目，请先创建项目
            </div>

            <div v-else class="projects-list">
              <div
                v-for="project in projects"
                :key="project.id"
                class="project-section"
                :class="{ expanded: selectedProjectId === project.id }"
              >
                <div class="project-header" @click="toggleProject(project.id)">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                  </svg>
                  <span class="project-name">{{ project.name }}</span>
                  <svg class="arrow-icon" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                    <polyline points="9 18 15 12 9 6"/>
                  </svg>
                </div>

                <Transition name="categories-slide">
                  <div v-if="selectedProjectId === project.id" class="categories-list">
                    <div v-if="!project.categories || project.categories.length === 0" class="no-categories">
                      该项目暂无分类
                    </div>
                    <div
                      v-for="category in project.categories"
                      :key="category.id"
                      class="category-item"
                      :class="{ selected: selectedCategoryId === category.id }"
                      @click="selectedCategoryId = category.id"
                    >
                      <span class="category-name">{{ category.name }}</span>
                      <span class="category-count">{{ category.asset_count }}</span>
                    </div>
                  </div>
                </Transition>
              </div>
            </div>
          </div>

          <div class="dialog-footer">
            <button class="dialog-btn cancel" @click="handleClose">取消</button>
            <button class="dialog-btn confirm" :disabled="!selectedCategoryId || processing" @click="handleConfirm">
              {{ processing ? '处理中...' : '确认' }}
            </button>
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
  background: rgba(0, 0, 0, 0.75);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.dialog-content {
  width: 90%;
  max-width: 480px;
  max-height: 70vh;
  background: rgba(25, 25, 30, 0.98);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
  overflow: hidden;
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
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: transparent;
  color: rgba(255, 255, 255, 0.5);
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.dialog-close:hover {
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.9);
  transform: rotate(90deg);
}

.dialog-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  min-height: 200px;
}

.dialog-body::-webkit-scrollbar { width: 4px; }
.dialog-body::-webkit-scrollbar-track { background: rgba(255, 255, 255, 0.03); }
.dialog-body::-webkit-scrollbar-thumb {
  background: rgba(108, 99, 255, 0.3);
  border-radius: 2px;
}

.dialog-loading {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 40px 0;
}

.mini-spinner {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 2px solid rgba(108, 99, 255, 0.3);
  border-top-color: rgba(108, 99, 255, 0.9);
  animation: spin 0.8s linear infinite;
}

.dialog-empty {
  text-align: center;
  padding: 40px 20px;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.3);
}

.projects-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.project-section {
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.02);
  overflow: hidden;
  transition: all 0.2s;
}

.project-section.expanded {
  border-color: rgba(108, 99, 255, 0.3);
  background: rgba(108, 99, 255, 0.05);
}

.project-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  cursor: pointer;
  transition: background 0.2s;
}

.project-header:hover {
  background: rgba(255, 255, 255, 0.04);
}

.project-name {
  flex: 1;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.8);
}

.arrow-icon {
  color: rgba(255, 255, 255, 0.4);
  transition: transform 0.2s;
}

.project-section.expanded .arrow-icon {
  transform: rotate(90deg);
}

.categories-list {
  padding: 4px 8px 8px 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.no-categories {
  padding: 12px 14px;
  text-align: center;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.25);
}

.category-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid transparent;
  cursor: pointer;
  transition: all 0.2s;
}

.category-item:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(108, 99, 255, 0.2);
}

.category-item.selected {
  background: rgba(108, 99, 255, 0.2);
  border-color: rgba(108, 99, 255, 0.6);
}

.category-name {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.7);
}

.category-item.selected .category-name {
  color: rgba(255, 255, 255, 0.95);
}

.category-count {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.3);
  background: rgba(255, 255, 255, 0.08);
  padding: 2px 8px;
  border-radius: 10px;
}

.category-item.selected .category-count {
  background: rgba(167, 139, 250, 0.25);
  color: rgba(167, 139, 250, 0.9);
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
  color: rgba(255, 255, 255, 0.5);
}

.dialog-btn.cancel:hover {
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.8);
}

.dialog-btn.confirm {
  background: rgba(108, 99, 255, 0.3);
  border-color: rgba(108, 99, 255, 0.6);
  color: rgba(255, 255, 255, 0.95);
}

.dialog-btn.confirm:hover:not(:disabled) {
  background: rgba(108, 99, 255, 0.45);
}

.dialog-btn.confirm:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.project-dialog-enter-active,
.project-dialog-leave-active {
  transition: opacity 0.25s ease;
}

.project-dialog-enter-active .dialog-content,
.project-dialog-leave-active .dialog-content {
  transition: transform 0.25s ease, opacity 0.25s ease;
}

.project-dialog-enter-from,
.project-dialog-leave-to {
  opacity: 0;
}

.project-dialog-enter-from .dialog-content,
.project-dialog-leave-to .dialog-content {
  transform: scale(0.9) translateY(20px);
  opacity: 0;
}

.categories-slide-enter-active,
.categories-slide-leave-active {
  transition: all 0.25s ease;
  overflow: hidden;
}

.categories-slide-enter-from,
.categories-slide-leave-to {
  max-height: 0;
  opacity: 0;
}

.categories-slide-enter-to,
.categories-slide-leave-from {
  max-height: 500px;
  opacity: 1;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
