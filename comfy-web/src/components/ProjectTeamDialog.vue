<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  listMembers, addMember, setMemberRole, removeMember,
  listCandidateUsers,
  listPendingAssets, reviewAsset,
  fetchReviewTimeline, listMySubmissions,
  type ProjectMember, type PendingAsset, type MemberRole, type CandidateUser,
  type ReviewEvent, type MySubmission,
} from '../api/apiService'

const props = defineProps<{
  visible: boolean
  projectId: number
  projectName: string
  currentRole: MemberRole      // 当前用户在该项目的角色
  currentUserId: number
}>()

const emit = defineEmits<{
  close: []
  reviewed: []                 // 审核通过后通知父组件刷新分类资产
}>()

const activeTab = ref<'members' | 'pending' | 'mine'>('members')

// 是否有管理权限（拉人、设角色、审核）
const canManage = () => props.currentRole === 'owner' || props.currentRole === 'admin'

// ── 成员 ────────────────────────────────────────────────────────────────
const members = ref<ProjectMember[]>([])
const membersLoading = ref(false)

async function loadMembers() {
  membersLoading.value = true
  try {
    members.value = await listMembers(props.projectId, props.currentUserId)
  } catch {
    ElMessage.error('加载成员失败')
  } finally {
    membersLoading.value = false
  }
}

// ── 添加成员（候选用户选人） ──────────────────────────────────────────────
const showAddPanel = ref(false)
const candidates = ref<CandidateUser[]>([])
const candidatesLoading = ref(false)
const searchKeyword = ref('')
const addingId = ref<number | null>(null)

// 按关键字模糊过滤候选用户
const filteredCandidates = computed(() => {
  const kw = searchKeyword.value.trim().toLowerCase()
  if (!kw) return candidates.value
  return candidates.value.filter(u => (u.user_name || '').toLowerCase().includes(kw))
})

async function openAddPanel() {
  showAddPanel.value = true
  searchKeyword.value = ''
  candidatesLoading.value = true
  try {
    candidates.value = await listCandidateUsers(props.projectId, props.currentUserId)
  } catch {
    ElMessage.error('加载用户失败')
  } finally {
    candidatesLoading.value = false
  }
}

async function handleAddCandidate(u: CandidateUser) {
  addingId.value = u.id
  try {
    await addMember(props.projectId, props.currentUserId, u.user_name || '', 'member')
    ElMessage.success('已添加成员')
    candidates.value = candidates.value.filter(x => x.id !== u.id)
    await loadMembers()
  } catch (e: any) {
    ElMessage.error(e.message || '添加失败')
  } finally {
    addingId.value = null
  }
}

async function handleSetRole(m: ProjectMember, role: MemberRole) {
  if (m.role === role) return
  try {
    await setMemberRole(props.projectId, props.currentUserId, m.user_id, role)
    m.role = role
    ElMessage.success('角色已更新')
  } catch (e: any) {
    ElMessage.error(e.message || '更新失败')
  }
}

async function handleRemove(m: ProjectMember) {
  try {
    await removeMember(props.projectId, props.currentUserId, m.user_id)
    members.value = members.value.filter(x => x.user_id !== m.user_id)
    ElMessage.success('已移除成员')
  } catch (e: any) {
    ElMessage.error(e.message || '移除失败')
  }
}

// ── 待审核 ──────────────────────────────────────────────────────────────
const pending = ref<PendingAsset[]>([])
const pendingLoading = ref(false)

async function loadPending() {
  pendingLoading.value = true
  try {
    pending.value = await listPendingAssets(props.projectId, props.currentUserId)
  } catch {
    ElMessage.error('加载待审核失败')
  } finally {
    pendingLoading.value = false
  }
}

// 审核评语：记录每条待审项当前输入的评语（key = category_id-assets_id）
const reviewComments = ref<Record<string, string>>({})
const reviewingKey = ref<string | null>(null)

function itemKey(categoryId: number, assetsId: number) {
  return `${categoryId}-${assetsId}`
}

async function handleReview(item: PendingAsset, approve: boolean) {
  const key = itemKey(item.category_id, item.assets_id)
  reviewingKey.value = key
  try {
    const comment = (reviewComments.value[key] || '').trim() || undefined
    await reviewAsset(item.category_id, item.assets_id, props.currentUserId, approve, comment)
    pending.value = pending.value.filter(
      x => !(x.category_id === item.category_id && x.assets_id === item.assets_id)
    )
    delete reviewComments.value[key]
    ElMessage.success(approve ? '已通过' : '已驳回')
    if (approve) emit('reviewed')
  } catch (e: any) {
    ElMessage.error(e.message || '操作失败')
  } finally {
    reviewingKey.value = null
  }
}

// ── 我的提交（所有成员可查自己的提交进度） ──────────────────────────────────
const mySubmissions = ref<MySubmission[]>([])
const mineLoading = ref(false)

async function loadMySubmissions() {
  mineLoading.value = true
  try {
    mySubmissions.value = await listMySubmissions(props.projectId, props.currentUserId)
  } catch {
    ElMessage.error('加载我的提交失败')
  } finally {
    mineLoading.value = false
  }
}

const statusLabel: Record<string, string> = { pending: '待审核', approved: '已通过', rejected: '已驳回' }

// ── 审核时间线（点开某条提交查看完整过程） ──────────────────────────────────
const showTimeline = ref(false)
const timeline = ref<ReviewEvent[]>([])
const timelineLoading = ref(false)

async function openTimeline(categoryId: number, assetsId: number) {
  showTimeline.value = true
  timelineLoading.value = true
  timeline.value = []
  try {
    timeline.value = await fetchReviewTimeline(categoryId, assetsId, props.currentUserId)
  } catch {
    ElMessage.error('加载审核记录失败')
  } finally {
    timelineLoading.value = false
  }
}

const actionLabel: Record<string, string> = { submit: '提交', approve: '通过', reject: '驳回' }

function switchTab(tab: 'members' | 'pending' | 'mine') {
  activeTab.value = tab
  if (tab === 'members' && members.value.length === 0) loadMembers()
  if (tab === 'pending' && pending.value.length === 0) loadPending()
  if (tab === 'mine') loadMySubmissions()
}

function getMediaUrl(location: string | null) {
  if (!location) return ''
  return `/api/api-proxy/output/${location.split(/[/\\]/).pop()}`
}
function isVideoLoc(location: string | null) {
  const ext = location?.split('.').pop()?.toLowerCase()
  return ['mp4', 'mov', 'avi', 'webm'].includes(ext || '')
}

function handleClose() {
  emit('close')
}

watch(() => props.visible, (v) => {
  if (v) {
    activeTab.value = 'members'
    showAddPanel.value = false
    members.value = []
    pending.value = []
    loadMembers()
  }
})

const roleLabel: Record<MemberRole, string> = { owner: '所有者', admin: '管理员', member: '成员' }
</script>

<template>
  <Teleport to="body">
    <Transition name="team-dialog">
      <div v-if="visible" class="dialog-overlay" @click="handleClose">
        <div class="dialog-content" @click.stop>
          <div class="dialog-header">
            <span class="dialog-title">{{ projectName }} · 团队</span>
            <button class="dialog-close" @click="handleClose">✕</button>
          </div>

          <!-- tab 切换 -->
          <div class="tab-bar">
            <button class="tab" :class="{ active: activeTab === 'members' }" @click="switchTab('members')">成员</button>
            <button v-if="canManage()" class="tab" :class="{ active: activeTab === 'pending' }" @click="switchTab('pending')">待审核</button>
            <button class="tab" :class="{ active: activeTab === 'mine' }" @click="switchTab('mine')">我的提交</button>
          </div>

          <div class="dialog-body">
            <!-- ── 成员管理 ── -->
            <template v-if="activeTab === 'members'">
              <!-- 成员列表视图 -->
              <template v-if="!showAddPanel">
                <!-- 添加成员按钮（仅 owner/admin） -->
                <button v-if="canManage()" class="add-member-btn" @click="openAddPanel">
                  <span class="add-icon">＋</span> 添加成员
                </button>

                <div v-if="membersLoading" class="center-state"><div class="mini-spin" /></div>
                <div v-else class="member-list">
                  <div v-for="m in members" :key="m.user_id" class="member-item">
                    <span class="member-name">{{ m.user_name || `用户${m.user_id}` }}</span>
                    <!-- owner 不可改 -->
                    <template v-if="m.role === 'owner'">
                      <span class="role-badge owner">{{ roleLabel.owner }}</span>
                    </template>
                    <template v-else>
                      <template v-if="canManage()">
                        <select class="role-select" :value="m.role" @change="handleSetRole(m, ($event.target as HTMLSelectElement).value as MemberRole)">
                          <option value="member">成员</option>
                          <option value="admin">管理员</option>
                        </select>
                        <button class="member-del" @click="handleRemove(m)" title="移除">✕</button>
                      </template>
                      <span v-else class="role-badge">{{ roleLabel[m.role] }}</span>
                    </template>
                  </div>
                </div>
              </template>

              <!-- 候选用户选人视图 -->
              <template v-else>
                <div class="add-panel-header">
                  <button class="back-link" @click="showAddPanel = false">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
                    返回
                  </button>
                  <input class="search-input" v-model="searchKeyword" placeholder="搜索用户名" autofocus />
                </div>

                <div v-if="candidatesLoading" class="center-state"><div class="mini-spin" /></div>
                <div v-else-if="filteredCandidates.length === 0" class="center-state">
                  <p class="empty-hint">{{ candidates.length === 0 ? '没有可添加的用户' : '无匹配用户' }}</p>
                </div>
                <div v-else class="candidate-list">
                  <div v-for="u in filteredCandidates" :key="u.id" class="candidate-item">
                    <span class="candidate-name">{{ u.user_name || `用户${u.id}` }}</span>
                    <button class="candidate-add" :disabled="addingId === u.id" @click="handleAddCandidate(u)">
                      {{ addingId === u.id ? '添加中' : '添加' }}
                    </button>
                  </div>
                </div>
              </template>
            </template>

            <!-- ── 待审核 ── -->
            <template v-else-if="activeTab === 'pending'">
              <div v-if="pendingLoading" class="center-state"><div class="mini-spin" /></div>
              <div v-else-if="pending.length === 0" class="center-state">
                <p class="empty-hint">暂无待审核素材</p>
              </div>
              <div v-else class="pending-list">
                <div v-for="item in pending" :key="`${item.category_id}-${item.assets_id}`" class="pending-item">
                  <div class="pending-top">
                    <div class="pending-thumb">
                      <video v-if="isVideoLoc(item.location)" :src="getMediaUrl(item.location)" preload="metadata" />
                      <img v-else :src="getMediaUrl(item.location)" />
                    </div>
                    <div class="pending-info">
                      <span class="pending-cat">分类：{{ item.category_name }}</span>
                      <span class="pending-meta">提交人 ID：{{ item.submitted_by }}</span>
                      <button
                        v-if="item.reject_count > 0"
                        class="reject-count-badge"
                        @click="openTimeline(item.category_id, item.assets_id)"
                      >已被驳回 {{ item.reject_count }} 次 · 查看记录</button>
                    </div>
                  </div>
                  <textarea
                    class="review-comment"
                    :value="reviewComments[itemKey(item.category_id, item.assets_id)] || ''"
                    @input="reviewComments[itemKey(item.category_id, item.assets_id)] = ($event.target as HTMLTextAreaElement).value"
                    placeholder="评语 / 建议（可选，通过或驳回都会记录）"
                    rows="2"
                  />
                  <div class="pending-actions">
                    <button
                      class="review-btn approve"
                      :disabled="reviewingKey === itemKey(item.category_id, item.assets_id)"
                      @click="handleReview(item, true)"
                    >通过</button>
                    <button
                      class="review-btn reject"
                      :disabled="reviewingKey === itemKey(item.category_id, item.assets_id)"
                      @click="handleReview(item, false)"
                    >驳回</button>
                  </div>
                </div>
              </div>
            </template>

            <!-- ── 我的提交 ── -->
            <template v-else>
              <div v-if="mineLoading" class="center-state"><div class="mini-spin" /></div>
              <div v-else-if="mySubmissions.length === 0" class="center-state">
                <p class="empty-hint">你还没有提交过素材</p>
              </div>
              <div v-else class="pending-list">
                <div v-for="item in mySubmissions" :key="`${item.category_id}-${item.assets_id}`" class="pending-item">
                  <div class="pending-top">
                    <div class="pending-thumb">
                      <video v-if="isVideoLoc(item.location)" :src="getMediaUrl(item.location)" preload="metadata" />
                      <img v-else :src="getMediaUrl(item.location)" />
                    </div>
                    <div class="pending-info">
                      <span class="pending-cat">分类：{{ item.category_name }}</span>
                      <span class="status-badge" :class="item.review_status">{{ statusLabel[item.review_status] }}</span>
                      <span v-if="item.reject_count > 0" class="pending-meta">被驳回 {{ item.reject_count }} 次</span>
                    </div>
                  </div>
                  <div class="pending-actions">
                    <button class="review-btn detail" @click="openTimeline(item.category_id, item.assets_id)">查看审核记录</button>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>

  <!-- 审核记录时间线弹窗 -->
  <Teleport to="body">
    <Transition name="team-dialog">
      <div v-if="showTimeline" class="dialog-overlay" style="z-index:4100" @click="showTimeline = false">
        <div class="timeline-content" @click.stop>
          <div class="dialog-header">
            <span class="dialog-title">审核记录</span>
            <button class="dialog-close" @click="showTimeline = false">✕</button>
          </div>
          <div class="dialog-body">
            <div v-if="timelineLoading" class="center-state"><div class="mini-spin" /></div>
            <div v-else-if="timeline.length === 0" class="center-state">
              <p class="empty-hint">暂无记录</p>
            </div>
            <div v-else class="timeline-list">
              <div v-for="(ev, i) in timeline" :key="i" class="timeline-item">
                <span class="timeline-action" :class="ev.action">{{ actionLabel[ev.action] || ev.action }}</span>
                <div class="timeline-body">
                  <div class="timeline-meta">
                    <span>{{ ev.reviewer_name || `用户${ev.reviewer_id ?? ''}` }}</span>
                    <span class="timeline-time">{{ ev.created_at }}</span>
                  </div>
                  <div v-if="ev.comment" class="timeline-comment">{{ ev.comment }}</div>
                </div>
              </div>
            </div>
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
  max-width: 520px;
  max-height: 75vh;
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
.dialog-title { font-size: 15px; font-weight: 500; color: rgba(255, 255, 255, 0.9); }
.dialog-close {
  width: 28px; height: 28px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: transparent;
  color: rgba(255, 255, 255, 0.5);
  font-size: 16px;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.2s;
}
.dialog-close:hover { background: rgba(255, 255, 255, 0.08); color: rgba(255, 255, 255, 0.9); transform: rotate(90deg); }

.tab-bar {
  display: flex;
  gap: 4px;
  padding: 10px 20px 0;
  flex-shrink: 0;
}
.tab {
  padding: 8px 18px;
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.4);
  font-size: 13px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.2s;
}
.tab:hover { color: rgba(255, 255, 255, 0.7); }
.tab.active { color: rgba(255, 255, 255, 0.95); border-bottom-color: rgba(108, 99, 255, 0.8); }

.dialog-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  min-height: 240px;
}
.dialog-body::-webkit-scrollbar { width: 4px; }
.dialog-body::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }

/* 角色下拉（成员列表用） */
.role-select {
  background: rgba(40,40,48,0.98);
  border: 1px solid rgba(255,255,255,0.14);
  border-radius: 8px;
  color: rgba(255,255,255,0.85);
  font-size: 12px;
  padding: 6px 8px;
  cursor: pointer;
  outline: none;
}

/* 添加成员按钮 */
.add-member-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  margin-bottom: 14px;
  padding: 9px 0;
  border-radius: 8px;
  border: 1px dashed rgba(255,255,255,0.2);
  background: rgba(255,255,255,0.03);
  color: rgba(255,255,255,0.7);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.add-member-btn:hover { background: rgba(255,255,255,0.07); border-color: rgba(255,255,255,0.35); color: rgba(255,255,255,0.95); }
.add-icon { font-size: 15px; line-height: 1; }

/* 候选选人面板 */
.add-panel-header { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; }
.back-link {
  display: flex; align-items: center; gap: 4px;
  padding: 7px 10px;
  border-radius: 8px;
  border: 1px solid rgba(255,255,255,0.12);
  background: transparent;
  color: rgba(255,255,255,0.6);
  font-size: 12px;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.2s;
}
.back-link:hover { background: rgba(255,255,255,0.06); color: rgba(255,255,255,0.9); }
.search-input {
  flex: 1;
  background: rgba(255,255,255,0.06);
  border: 1px solid rgba(255,255,255,0.14);
  border-radius: 8px;
  color: rgba(255,255,255,0.9);
  font-size: 13px;
  padding: 8px 12px;
  outline: none;
}
.search-input:focus { border-color: rgba(108,99,255,0.6); }

.candidate-list { display: flex; flex-direction: column; gap: 6px; }
.candidate-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.06);
}
.candidate-name { flex: 1; font-size: 13px; color: rgba(255,255,255,0.85); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.candidate-add {
  padding: 5px 16px;
  border-radius: 8px;
  border: 1px solid rgba(108,99,255,0.6);
  background: rgba(108,99,255,0.3);
  color: rgba(255,255,255,0.95);
  font-size: 12px;
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.2s;
}
.candidate-add:hover:not(:disabled) { background: rgba(108,99,255,0.45); }
.candidate-add:disabled { opacity: 0.5; cursor: not-allowed; }

/* 成员列表 */
.member-list { display: flex; flex-direction: column; gap: 6px; }
.member-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.06);
}
.member-name { flex: 1; font-size: 13px; color: rgba(255,255,255,0.85); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.role-badge {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 10px;
  background: rgba(255,255,255,0.08);
  color: rgba(255,255,255,0.6);
}
.role-badge.owner { background: rgba(234,179,8,0.15); color: #eab308; }
.member-del {
  width: 24px; height: 24px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: rgba(255,255,255,0.3);
  cursor: pointer;
  transition: all 0.2s;
}
.member-del:hover { background: rgba(244,63,94,0.15); color: #f43f5e; }

/* 待审核 */
.pending-list { display: flex; flex-direction: column; gap: 8px; }
.pending-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  border-radius: 10px;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.06);
}
.pending-top {
  display: flex;
  align-items: center;
  gap: 12px;
}
.pending-thumb {
  width: 56px; height: 56px;
  border-radius: 8px;
  overflow: hidden;
  background: rgba(0,0,0,0.3);
  flex-shrink: 0;
}
.pending-thumb img, .pending-thumb video { width: 100%; height: 100%; object-fit: cover; display: block; }
.pending-info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.pending-cat { font-size: 13px; color: rgba(255,255,255,0.85); }
.pending-meta { font-size: 11px; color: rgba(255,255,255,0.35); }
.pending-actions { display: flex; gap: 6px; flex-shrink: 0; justify-content: flex-end; }
.review-btn {
  padding: 6px 14px;
  border-radius: 8px;
  font-size: 12px;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.2s;
}
.review-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.review-btn.approve { background: rgba(34,197,94,0.18); border-color: rgba(34,197,94,0.4); color: #4ade80; }
.review-btn.approve:hover:not(:disabled) { background: rgba(34,197,94,0.3); }
.review-btn.reject { background: rgba(244,63,94,0.15); border-color: rgba(244,63,94,0.35); color: #fb7185; }
.review-btn.reject:hover:not(:disabled) { background: rgba(244,63,94,0.28); }
.review-btn.detail { background: rgba(255,255,255,0.06); border-color: rgba(255,255,255,0.14); color: rgba(255,255,255,0.7); }
.review-btn.detail:hover { background: rgba(255,255,255,0.12); color: rgba(255,255,255,0.9); }

/* 评语输入框 */
.review-comment {
  width: 100%;
  box-sizing: border-box;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 8px;
  color: rgba(255,255,255,0.85);
  font-size: 12px;
  padding: 8px 10px;
  resize: vertical;
  outline: none;
  font-family: inherit;
}
.review-comment:focus { border-color: rgba(108,99,255,0.6); }

/* 驳回次数徽标（可点开时间线） */
.reject-count-badge {
  align-self: flex-start;
  padding: 2px 8px;
  border-radius: 8px;
  border: 1px solid rgba(244,63,94,0.35);
  background: rgba(244,63,94,0.12);
  color: #fb7185;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
}
.reject-count-badge:hover { background: rgba(244,63,94,0.22); }

/* 我的提交状态徽标 */
.status-badge {
  align-self: flex-start;
  font-size: 11px;
  padding: 2px 10px;
  border-radius: 10px;
}
.status-badge.pending { background: rgba(234,179,8,0.15); color: #eab308; }
.status-badge.approved { background: rgba(34,197,94,0.15); color: #4ade80; }
.status-badge.rejected { background: rgba(244,63,94,0.15); color: #fb7185; }

/* 时间线弹窗 */
.timeline-content {
  width: 90%;
  max-width: 440px;
  max-height: 70vh;
  background: rgba(25,25,30,0.98);
  border: 1px solid rgba(255,255,255,0.12);
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.5);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.timeline-list { display: flex; flex-direction: column; gap: 0; }
.timeline-item {
  display: flex;
  gap: 10px;
  padding-bottom: 16px;
}
.timeline-action {
  flex-shrink: 0;
  align-self: flex-start;
  font-size: 11px;
  padding: 2px 10px;
  border-radius: 10px;
  background: rgba(255,255,255,0.08);
  color: rgba(255,255,255,0.7);
}
.timeline-action.submit { background: rgba(96,165,250,0.15); color: #60a5fa; }
.timeline-action.approve { background: rgba(34,197,94,0.15); color: #4ade80; }
.timeline-action.reject { background: rgba(244,63,94,0.15); color: #fb7185; }
.timeline-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.timeline-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 11px;
  color: rgba(255,255,255,0.5);
}
.timeline-time { font-size: 10px; color: rgba(255,255,255,0.3); flex-shrink: 0; }
.timeline-comment {
  font-size: 12px;
  color: rgba(255,255,255,0.7);
  background: rgba(255,255,255,0.04);
  border-radius: 6px;
  padding: 6px 8px;
  white-space: pre-wrap;
  word-break: break-word;
}

/* 状态 */
.center-state { display: flex; align-items: center; justify-content: center; flex-direction: column; padding: 48px 0; }
.empty-hint { font-size: 12px; color: rgba(255,255,255,0.2); letter-spacing: 1px; }
.mini-spin {
  width: 24px; height: 24px;
  border-radius: 50%;
  border: 2px solid rgba(255,255,255,0.14);
  border-top-color: rgba(108,99,255,0.9);
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.team-dialog-enter-active, .team-dialog-leave-active { transition: opacity 0.25s ease; }
.team-dialog-enter-active .dialog-content, .team-dialog-leave-active .dialog-content { transition: transform 0.25s ease, opacity 0.25s ease; }
.team-dialog-enter-from, .team-dialog-leave-to { opacity: 0; }
.team-dialog-enter-from .dialog-content, .team-dialog-leave-to .dialog-content { transform: scale(0.9) translateY(20px); opacity: 0; }
</style>
