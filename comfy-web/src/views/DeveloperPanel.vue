<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElDialog, ElMessage, ElMessageBox } from 'element-plus'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import { showTopNotice } from '../utils/topNotice'

const user = computed(() => {
  try { return JSON.parse(localStorage.getItem('user') || 'null') } catch { return null }
})

const runtimeItems = computed(() => [
  { label: '运行模式', value: import.meta.env.MODE },
  { label: '登录身份', value: user.value?.username || '未知用户' },
  { label: 'Debug 会话', value: user.value?.debug ? '已启用' : '未启用' },
  { label: '前端地址', value: window.location.origin },
  { label: '路由模式', value: 'Hash History' },
])

const showStandardDialog = ref(false)
const customDialogType = ref<'danger' | 'warning' | 'info' | null>(null)

function showMessage(type: 'success' | 'warning' | 'error' | 'info') {
  ElMessage[type](`${type.toUpperCase()}：这是一条提示信息`)
}

async function showSystemConfirm() {
  try {
    await ElMessageBox.confirm('用于检查系统确认框的正文内容和按钮状态。', '系统确认框', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      type: 'warning',
    })
    ElMessage.success('已确认')
  } catch {
    ElMessage.info('已取消')
  }
}
</script>

<template>
  <main class="developer-panel">
    <header>
      <p>开发者功能</p>
      <h1>开发者面板</h1>
      <span>查看当前前端运行环境和调试会话状态。</span>
    </header>

    <dl class="runtime-list">
      <div v-for="item in runtimeItems" :key="item.label">
        <dt>{{ item.label }}</dt>
        <dd>{{ item.value }}</dd>
      </div>
    </dl>

    <section class="prompt-section">
      <div class="section-heading">
        <h2>提示框调试</h2>
        <span>点击按钮检查项目当前使用的提示样式。</span>
      </div>

      <div class="prompt-group">
        <h3>轻提示</h3>
        <div class="prompt-actions">
          <button @click="showTopNotice('任务已成功提交', 'success')">顶栏成功通知</button>
          <button @click="showTopNotice('当前队列负载较高', 'warning')">顶栏警告通知</button>
          <button @click="showTopNotice('任务处理失败', 'error')">顶栏错误通知</button>
          <button @click="showTopNotice('新的生成任务已进入队列', 'info')">顶栏信息通知</button>
          <button @click="showMessage('success')">成功提示</button>
          <button @click="showMessage('warning')">警告提示</button>
          <button @click="showMessage('error')">错误提示</button>
          <button @click="showMessage('info')">信息提示</button>
        </div>
      </div>

      <div class="prompt-group">
        <h3>对话框</h3>
        <div class="prompt-actions">
          <button @click="showSystemConfirm">系统确认框</button>
          <button @click="showStandardDialog = true">普通对话框</button>
          <button @click="customDialogType = 'danger'">危险确认框</button>
          <button @click="customDialogType = 'warning'">警告确认框</button>
          <button @click="customDialogType = 'info'">信息确认框</button>
        </div>
      </div>
    </section>

    <ElDialog v-model="showStandardDialog" title="普通对话框" width="420px" align-center>
      <p class="dialog-copy">用于检查普通业务弹窗的标题、正文、遮罩和底部操作区。</p>
      <template #footer>
        <button class="dialog-action muted" @click="showStandardDialog = false">取消</button>
        <button class="dialog-action" @click="showStandardDialog = false">确认</button>
      </template>
    </ElDialog>

    <ConfirmDialog
      :visible="customDialogType !== null"
      :type="customDialogType || 'info'"
      :title="customDialogType === 'danger' ? '危险操作' : customDialogType === 'warning' ? '操作提醒' : '信息确认'"
      message="用于检查自定义确认框的视觉样式和交互状态。"
      confirm-text="确认"
      cancel-text="取消"
      @confirm="customDialogType = null"
      @cancel="customDialogType = null"
    />
  </main>
</template>

<style scoped>
.developer-panel {
  min-height: calc(100vh - 22px);
  padding: 52px 48px;
  background: rgba(2, 4, 8, 0.72);
}

header p {
  margin: 0 0 10px;
  color: var(--color-primary);
  font-size: 11px;
}

h1 {
  margin: 0;
  font-size: 30px;
  font-weight: 600;
}

header span {
  display: block;
  margin-top: 12px;
  color: var(--color-muted);
  font-size: 13px;
}

.runtime-list {
  width: min(100%, 720px);
  margin: 48px 0 0;
}

.prompt-section {
  width: min(100%, 720px);
  margin-top: 58px;
}

.section-heading h2 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.section-heading span {
  display: block;
  margin-top: 8px;
  color: var(--color-muted);
  font-size: 12px;
}

.prompt-group {
  margin-top: 30px;
}

.prompt-group h3 {
  margin: 0 0 12px;
  color: var(--color-muted);
  font-size: 11px;
  font-weight: 400;
}

.prompt-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.prompt-actions button,
.dialog-action {
  height: 36px;
  padding: 0 14px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.05);
  color: var(--color-text);
  cursor: pointer;
}

.prompt-actions button:hover,
.dialog-action:hover {
  background: rgba(255, 255, 255, 0.1);
}

.dialog-copy {
  margin: 0;
  color: var(--color-muted);
  line-height: 1.7;
}

.dialog-action.muted {
  color: var(--color-muted);
}

.runtime-list > div {
  display: grid;
  grid-template-columns: 150px 1fr;
  gap: 24px;
  padding: 17px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

dt {
  color: var(--color-muted);
  font-size: 12px;
}

dd {
  margin: 0;
  color: var(--color-text);
  font-size: 13px;
}

@media (max-width: 700px) {
  .developer-panel { padding: 32px 22px; }
  .runtime-list > div { grid-template-columns: 1fr; gap: 7px; }
}
</style>
