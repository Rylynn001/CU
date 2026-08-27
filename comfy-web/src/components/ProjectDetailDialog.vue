<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

interface ProjectDetail {
  id: number
  name: string
  role: string
  owner: { user_id: number; user_name: string; real_name: string } | null
  admins: Array<{ user_id: number; user_name: string; real_name: string }>
  members: Array<{ user_id: number; user_name: string; real_name: string }>
  total_members: number
  category_count: number
  approved_count: number
  pending_count: number
  rejected_count: number
}

const props = defineProps<{
  visible: boolean
  projectId: number | null
}>()

const emit = defineEmits<{
  close: []
}>()

const detail = ref<ProjectDetail | null>(null)
const loading = ref(false)

function getUser() {
  const s = localStorage.getItem('user')
  return s ? JSON.parse(s) : null
}

async function loadDetail() {
  if (!props.projectId) return
  const user = getUser()
  if (!user) return

  loading.value = true
  try {
    const res = await fetch(`/api/api-proxy/projects/${props.projectId}?user_id=${user.id}`)
    if (!res.ok) throw new Error()
    detail.value = await res.json()
  } catch {
    ElMessage.error('加载项目详情失败')
    handleClose()
  } finally {
    loading.value = false
  }
}

function handleClose() {
  emit('close')
  detail.value = null
}

function getRoleName(role: string): string {
  const map: Record<string, string> = {
    owner: '拥有者',
    admin: '管理员',
    member: '成员',
  }
  return map[role] || role
}

watch(() => props.visible, (newVal) => {
  if (newVal) {
    loadDetail()
  }
})
</script>

<template>
  <Teleport to="body">
    <Transition name="detail-dialog">
      <div v-if="visible" class="dialog-overlay" @click="handleClose">
        <div class="dialog-content" @click.stop>
          <div class="dialog-header">
            <span class="dialog-title">项目详情</span>
            <button class="dialog-close" @click="handleClose">✕</button>
          </div>

          <div class="dialog-body">
            <div v-if="loading" class="dialog-loading">
              <div class="mini-spinner" />
            </div>

            <div v-else-if="detail" class="detail-container">
              <!-- 项目名称 -->
              <div class="detail-section">
                <div class="section-title">项目名称</div>
                <div class="project-name">{{ detail.name }}</div>
              </div>

              <!-- 我的角色 -->
              <div class="detail-section">
                <div class="section-title">我的角色</div>
                <div class="role-badge" :class="detail.role">
                  {{ getRoleName(detail.role) }}
                </div>
              </div>

              <!-- 成员统计 -->
              <div class="detail-section">
                <div class="section-title">成员</div>
                <div class="members-grid">
                  <div class="member-group">
                    <div class="group-label">拥有者</div>
                    <div v-if="detail.owner" class="member-list">
                      <div class="member-item">
                        {{ detail.owner.real_name || detail.owner.user_name }}
                      </div>
                    </div>
                    <div v-else class="no-data">无</div>
                  </div>

                  <div class="member-group">
                    <div class="group-label">管理员</div>
                    <div v-if="detail.admins.length > 0" class="member-list">
                      <div v-for="admin in detail.admins" :key="admin.user_id" class="member-item">
                        {{ admin.real_name || admin.user_name }}
                      </div>
                    </div>
                    <div v-else class="no-data">无</div>
                  </div>

                  <div class="member-group">
                    <div class="group-label">普通成员</div>
                    <div v-if="detail.members.length > 0" class="member-list">
                      <div v-for="member in detail.members" :key="member.user_id" class="member-item">
                        {{ member.real_name || member.user_name }}
                      </div>
                    </div>
                    <div v-else class="no-data">无</div>
                  </div>
                </div>
                <div class="total-count">总计 {{ detail.total_members }} 人</div>
              </div>

              <!-- 统计数据 -->
              <div class="detail-section">
                <div class="section-title">统计</div>
                <div class="stats-grid">
                  <div class="stat-item">
                    <div class="stat-label">分类数</div>
                    <div class="stat-value">{{ detail.category_count }}</div>
                  </div>
                  <div class="stat-item approved">
                    <div class="stat-label">已通过</div>
                    <div class="stat-value">{{ detail.approved_count }}</div>
                  </div>
                  <div class="stat-item pending">
                    <div class="stat-label">审批中</div>
                    <div class="stat-value">{{ detail.pending_count }}</div>
                  </div>
                  <div class="stat-item rejected">
                    <div class="stat-label">已驳回</div>
                    <div class="stat-value">{{ detail.rejected_count }}</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="dialog-footer">
            <button class="dialog-btn" @click="handleClose">关闭</button>
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
  max-width: 600px;
  max-height: 80vh;
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
  padding: 20px;
}

.dialog-body::-webkit-scrollbar { width: 4px; }
.dialog-body::-webkit-scrollbar-track { background: rgba(255, 255, 255, 0.03); }
.dialog-body::-webkit-scrollbar-thumb {
  background: rgba(255,255,255, 0.3);
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
  border: 2px solid rgba(255,255,255, 0.3);
  border-top-color: rgba(255,255,255, 0.9);
  animation: spin 0.8s linear infinite;
}

.detail-container {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.section-title {
  font-size: 12px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.5);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.project-name {
  font-size: 18px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.95);
}

.role-badge {
  display: inline-flex;
  padding: 6px 14px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  width: fit-content;
}

.role-badge.owner {
  background: rgba(255, 193, 7, 0.2);
  border: 1px solid rgba(255, 193, 7, 0.5);
  color: rgba(255, 193, 7, 1);
}

.role-badge.admin {
  background: rgba(56, 189, 248, 0.2);
  border: 1px solid rgba(56, 189, 248, 0.5);
  color: rgba(56, 189, 248, 1);
}

.role-badge.member {
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.3);
  color: rgba(255, 255, 255, 0.8);
}

.members-grid {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
}

.member-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.group-label {
  font-size: 11px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.4);
  text-transform: uppercase;
}

.member-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.member-item {
  padding: 6px 12px;
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 6px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.8);
}

.no-data {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.3);
  font-style: italic;
}

.total-count {
  margin-top: 4px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.5);
  text-align: right;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 12px;
}

.stat-item {
  padding: 16px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: all 0.2s;
}

.stat-item:hover {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.15);
}

.stat-item.approved {
  border-color: rgba(34, 211, 238, 0.3);
}

.stat-item.pending {
  border-color: rgba(251, 191, 36, 0.3);
}

.stat-item.rejected {
  border-color: rgba(239, 68, 68, 0.3);
}

.stat-label {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.5);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.stat-value {
  font-size: 24px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.95);
}

.stat-item.approved .stat-value {
  color: rgba(34, 211, 238, 1);
}

.stat-item.pending .stat-value {
  color: rgba(251, 191, 36, 1);
}

.stat-item.rejected .stat-value {
  color: rgba(239, 68, 68, 1);
}

.dialog-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
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
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: rgba(255, 255, 255, 0.8);
}

.dialog-btn:hover {
  background: rgba(255, 255, 255, 0.15);
  color: rgba(255, 255, 255, 0.95);
}

.detail-dialog-enter-active,
.detail-dialog-leave-active {
  transition: opacity 0.25s ease;
}

.detail-dialog-enter-active .dialog-content,
.detail-dialog-leave-active .dialog-content {
  transition: transform 0.25s ease, opacity 0.25s ease;
}

.detail-dialog-enter-from,
.detail-dialog-leave-to {
  opacity: 0;
}

.detail-dialog-enter-from .dialog-content,
.detail-dialog-leave-to .dialog-content {
  transform: scale(0.9) translateY(20px);
  opacity: 0;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
