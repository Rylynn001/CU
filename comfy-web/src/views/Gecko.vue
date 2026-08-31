<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'

interface GeckoAccount {
  success: boolean
  name: string | null
  id: string | null
  department: string | null
  ip: string | null
}

interface GeckoTask {
  [key: string]: any
}

// ── 账号信息（原 Gecko 初始化）──────────────────────────────────────────
const account = ref<GeckoAccount | null>(null)
const accountDialogVisible = ref(false)
const accountDialogMessage = ref('')

async function initAccount() {
  try {
    const res = await fetch('/api/api-proxy/gecko/init', { method: 'POST' })
    const data = await res.json()
    account.value = {
      success: data.success,
      name: data.name || null,
      id: data.id || null,
      department: data.department || null,
      ip: data.ip || null,
    }
    accountDialogMessage.value = data.success ? '' : (data.message || '请先登录Gecko')
    accountDialogVisible.value = true
  } catch (e: any) {
    account.value = { success: false, name: null, id: null, department: null, ip: null }
    accountDialogMessage.value = '初始化失败'
    accountDialogVisible.value = true
  }
}

// ── 当前任务列表 ────────────────────────────────────────────────────────
const tasks = ref<GeckoTask[]>([])
const totalCount = ref(0)
const currentPage = ref(1)
const pageSize = 50
const tasksLoading = ref(false)

async function loadTasks(page = 1) {
  tasksLoading.value = true
  try {
    const res = await fetch('/api/api-proxy/gecko/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ page }),
    })
    const data = await res.json()
    if (!data.success) {
      ElMessage.error(data.message || '获取任务失败')
      return
    }
    tasks.value = data.data_list || []
    totalCount.value = data.total_count || 0
    currentPage.value = page
  } catch (e: any) {
    ElMessage.error(e.message || '获取任务失败')
  } finally {
    tasksLoading.value = false
  }
}

function handlePageChange(page: number) {
  loadTasks(page)
}

onMounted(() => {
  initAccount()
  loadTasks(1)
})
</script>

<template>
  <div class="gecko-page">
    <div class="header">
      <h2 class="title">Gecko 当前任务</h2>
      <button class="refresh-btn" @click="loadTasks(currentPage)" :disabled="tasksLoading">
        {{ tasksLoading ? '加载中...' : '刷新' }}
      </button>
    </div>

    <el-table :data="tasks" v-loading="tasksLoading" style="width: 100%">
      <el-table-column v-for="key in Object.keys(tasks[0] || {})" :key="key" :prop="key" :label="key" min-width="140" show-overflow-tooltip />
    </el-table>

    <div v-if="!tasksLoading && tasks.length === 0" class="empty-text">暂无任务数据</div>

    <div class="pagination-bar">
      <el-pagination
        v-model:current-page="currentPage"
        :page-size="pageSize"
        :total="totalCount"
        layout="prev, pager, next, total"
        @current-change="handlePageChange"
      />
    </div>

    <!-- 账号信息弹窗 -->
    <el-dialog
      v-model="accountDialogVisible"
      title="Gecko 账号信息"
      width="360px"
      align-center
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="true"
    >
      <template v-if="account?.success">
        <div class="gecko-dialog-info">
          <p><span class="gecko-info-label">姓名：</span><span class="gecko-info-value">{{ account.name }}</span></p>
          <p><span class="gecko-info-label">部门：</span><span class="gecko-info-value">{{ account.department }}</span></p>
          <p><span class="gecko-info-label">ID：</span><span class="gecko-info-value">{{ account.id }}</span></p>
          <p><span class="gecko-info-label">IP：</span><span class="gecko-info-value">{{ account.ip }}</span></p>
        </div>
        <p class="gecko-dialog-warning">
          请仔细核对以上信息是否与您本人一致。如信息有误，请先检查当前登录的 Gecko 客户端账户是否为您本人的账户；若账户确认无误但信息仍不一致，请联系管理员处理。
        </p>
      </template>
      <template v-else>
        <p class="gecko-dialog-warning">{{ accountDialogMessage }}</p>
      </template>
      <template #footer>
        <button class="dlg-btn confirm" @click="accountDialogVisible = false">我已确认</button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.gecko-page {
  padding: 40px 32px;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.title {
  font-size: 26px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.9);
  letter-spacing: 2px;
  margin: 0;
}

.refresh-btn {
  padding: 7px 18px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.13);
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.8);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.refresh-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.24);
}
.refresh-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.empty-text {
  text-align: center;
  padding: 40px 0;
  color: rgba(255, 255, 255, 0.3);
  font-size: 13px;
}

.pagination-bar {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
}

.pagination-bar :deep(.el-pagination) {
  --el-pagination-bg-color: transparent;
  --el-pagination-button-color: rgba(255, 255, 255, 0.8);
  --el-pagination-hover-color: rgba(255, 255, 255, 0.95);
}

.pagination-bar :deep(.el-pagination__total) {
  color: rgba(255, 255, 255, 0.5);
}

.pagination-bar :deep(.btn-prev),
.pagination-bar :deep(.btn-next),
.pagination-bar :deep(.el-pager li) {
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.13);
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.8);
  margin: 0 4px;
  transition: all 0.2s;
}

.pagination-bar :deep(.btn-prev:hover),
.pagination-bar :deep(.btn-next:hover),
.pagination-bar :deep(.el-pager li:hover) {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.24);
  color: rgba(255, 255, 255, 0.95);
}

.pagination-bar :deep(.btn-prev:disabled) {
  opacity: 0.4;
  cursor: not-allowed;
}

.pagination-bar :deep(.el-pager li.is-active) {
  background: rgba(255, 255, 255, 0.2);
  border-color: rgba(255, 255, 255, 0.34);
  color: #ffffff;
  font-weight: 600;
}

.gecko-dialog-warning {
  padding: 10px 12px;
  border: 1px solid rgba(245, 108, 108, 0.65);
  border-radius: 6px;
  background: rgba(245, 108, 108, 0.08);
  color: #f56c6c;
  font-size: 13px;
  line-height: 1.6;
  margin: 0;
}

.gecko-dialog-info + .gecko-dialog-warning {
  margin-top: 14px;
}

.gecko-dialog-info {
  color: #ffffff;
  font-size: 13px;
  line-height: 1.8;
}

.gecko-dialog-info p {
  margin: 0;
}

.gecko-info-label {
  color: rgba(255, 255, 255, 0.6);
}

.gecko-info-value {
  color: #ffffff;
}

.dlg-btn {
  padding: 7px 20px;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.dlg-btn.confirm {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.24);
  color: rgba(255, 255, 255, 0.95);
}

.dlg-btn.confirm:hover:not(:disabled) { background: rgba(255, 255, 255, 0.18); }
</style>
