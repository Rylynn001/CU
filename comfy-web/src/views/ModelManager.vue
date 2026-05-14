<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElInput, ElSelect, ElOption, ElMessage } from 'element-plus'
import { Plus, Delete, Setting } from '@element-plus/icons-vue'
import {
  getApiModels, addApiModel, deleteApiModel,
  getApiConfig, saveApiConfig,
  type ApiModel,
} from '../api/apiService'

const models = ref<ApiModel[]>([])
const loading = ref(false)
const configLoading = ref(false)

// config panel
const showConfig = ref(false)
const configForm = ref({ api_key: '', base_url: '' })
const hasKey = ref(false)

// add model form
const showAdd = ref(false)
const addForm = ref({ id: '', name: '', description: '', type: 'image' })
const addLoading = ref(false)

async function loadModels() {
  loading.value = true
  try {
    models.value = await getApiModels()
  } catch (e: any) {
    ElMessage.error('加载模型失败：' + e.message)
  } finally {
    loading.value = false
  }
}

async function loadConfig() {
  try {
    const c = await getApiConfig()
    configForm.value.base_url = c.base_url
    hasKey.value = c.has_key
  } catch {}
}

async function handleSaveConfig() {
  configLoading.value = true
  try {
    await saveApiConfig({
      base_url: configForm.value.base_url || undefined,
      api_key: configForm.value.api_key || undefined,
    })
    hasKey.value = !!configForm.value.api_key || hasKey.value
    configForm.value.api_key = ''
    ElMessage.success('配置已保存')
    showConfig.value = false
  } catch (e: any) {
    ElMessage.error('保存失败：' + e.message)
  } finally {
    configLoading.value = false
  }
}

async function handleAddModel() {
  if (!addForm.value.id || !addForm.value.name) {
    ElMessage.warning('模型 ID 和名称不能为空')
    return
  }
  addLoading.value = true
  try {
    await addApiModel({ ...addForm.value })
    ElMessage.success('模型已添加')
    addForm.value = { id: '', name: '', description: '', type: 'image' }
    showAdd.value = false
    await loadModels()
  } catch (e: any) {
    ElMessage.error('添加失败：' + e.message)
  } finally {
    addLoading.value = false
  }
}

async function handleDelete(model: ApiModel) {
  try {
    await deleteApiModel(model.id)
    ElMessage.success(`已删除 ${model.name}`)
    await loadModels()
  } catch (e: any) {
    ElMessage.error('删除失败：' + e.message)
  }
}

onMounted(() => {
  loadModels()
  loadConfig()
})
</script>

<template>
  <div class="manager-page">
    <div class="orb orb-1" />
    <div class="orb orb-2" />

    <div class="manager-wrap">
      <!-- header -->
      <div class="page-header">
        <div class="header-left">
          <span class="breath-dot" />
          <h1 class="page-title">模型管理</h1>
        </div>
        <div class="header-actions">
          <button class="icon-action-btn" @click="showConfig = !showConfig" title="API 配置">
            <el-icon><Setting /></el-icon>
          </button>
          <button class="add-btn" @click="showAdd = !showAdd">
            <el-icon><Plus /></el-icon>
            添加模型
          </button>
        </div>
      </div>

      <!-- config panel -->
      <div class="config-panel" :class="{ visible: showConfig }">
        <div class="config-inner">
          <div class="config-title">API 配置</div>
          <div class="config-row">
            <span class="config-label">Base URL</span>
            <ElInput v-model="configForm.base_url" placeholder="https://your-relay.com" class="config-input" />
          </div>
          <div class="config-row">
            <span class="config-label">API Key</span>
            <ElInput
              v-model="configForm.api_key"
              type="password"
              :placeholder="hasKey ? '已配置（留空不修改）' : '输入 API Key'"
              show-password
              class="config-input"
            />
          </div>
          <div class="config-footer">
            <span class="key-status" :class="{ active: hasKey }">
              {{ hasKey ? '● Key 已配置' : '○ 未配置 Key' }}
            </span>
            <button class="save-btn" :disabled="configLoading" @click="handleSaveConfig">
              {{ configLoading ? '保存中...' : '保存' }}
            </button>
          </div>
        </div>
      </div>

      <!-- add model panel -->
      <div class="config-panel" :class="{ visible: showAdd }">
        <div class="config-inner">
          <div class="config-title">添加模型</div>
          <div class="config-row">
            <span class="config-label">模型 ID</span>
            <ElInput v-model="addForm.id" placeholder="如 gpt-image-1 / flux-pro" class="config-input" />
          </div>
          <div class="config-row">
            <span class="config-label">显示名称</span>
            <ElInput v-model="addForm.name" placeholder="如 FLUX Pro" class="config-input" />
          </div>
          <div class="config-row">
            <span class="config-label">模型类型</span>
            <ElSelect v-model="addForm.type" class="config-input">
              <ElOption label="图片模型" value="image" />
              <ElOption label="视频模型" value="video" />
            </ElSelect>
          </div>
          <div class="config-row">
            <span class="config-label">描述</span>
            <ElInput v-model="addForm.description" placeholder="可选" class="config-input" />
          </div>
          <div class="config-footer">
            <button class="save-btn" :disabled="addLoading" @click="handleAddModel">
              {{ addLoading ? '添加中...' : '确认添加' }}
            </button>
          </div>
        </div>
      </div>

      <!-- model list -->
      <div v-if="loading" class="empty-wrap">
        <div class="empty-orb" />
        <p class="empty-text">加载中...</p>
      </div>

      <div v-else-if="models.length === 0" class="empty-wrap">
        <div class="empty-orb" />
        <p class="empty-text">暂无模型，点击右上角添加</p>
      </div>

      <div v-else class="model-grid">
        <div v-for="m in models" :key="m.id" class="model-card">
          <div class="card-glow" />
          <div class="model-top">
            <div class="model-icon">{{ m.name.charAt(0).toUpperCase() }}</div>
            <button class="delete-btn" @click="handleDelete(m)" title="删除">
              <el-icon><Delete /></el-icon>
            </button>
          </div>
          <div class="model-name">{{ m.name }}</div>
          <div class="model-id">{{ m.id }}</div>
          <div class="model-type-badge">{{ m.type === 'video' ? '视频' : '图片' }}</div>
          <div v-if="m.description" class="model-desc">{{ m.description }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.manager-page {
  min-height: 100vh;
  position: relative;
  overflow: hidden;
  padding: 40px 48px;
}

.orb {
  position: fixed;
  border-radius: 50%;
  filter: blur(90px);
  pointer-events: none;
  z-index: 0;
  animation: breathe 7s ease-in-out infinite;
}
.orb-1 {
  width: 500px; height: 500px;
  background: radial-gradient(circle, rgba(108,99,255,0.12) 0%, transparent 70%);
  top: -120px; left: -80px;
}
.orb-2 {
  width: 400px; height: 400px;
  background: radial-gradient(circle, rgba(167,139,250,0.1) 0%, transparent 70%);
  bottom: -100px; right: -60px;
  animation-delay: 3.5s;
}

.manager-wrap {
  position: relative;
  z-index: 1;
  max-width: 960px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* header */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.breath-dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: #a78bfa;
  animation: pulse-dot 2.5s ease-in-out infinite;
}

.page-title {
  font-size: 22px;
  font-weight: 600;
  color: rgba(255,255,255,0.9);
  letter-spacing: 2px;
  margin: 0;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.icon-action-btn {
  width: 36px; height: 36px;
  border-radius: 10px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.08);
  color: rgba(255,255,255,0.5);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background 0.2s, color 0.2s;
}
.icon-action-btn:hover { background: rgba(108,99,255,0.2); color: #fff; }

.add-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 10px;
  background: linear-gradient(135deg, #6c63ff, #a78bfa);
  border: none;
  color: #fff;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.2s, transform 0.15s;
}
.add-btn:hover { opacity: 0.88; transform: translateY(-1px); }

/* config / add panel */
.config-panel {
  max-height: 0;
  overflow: hidden;
  opacity: 0;
  transition: max-height 0.35s ease, opacity 0.25s ease;
}
.config-panel.visible { max-height: 400px; opacity: 1; }

.config-inner {
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 16px;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  animation: breathe-border 4s ease-in-out infinite;
}

.config-title {
  font-size: 12px;
  color: rgba(255,255,255,0.35);
  letter-spacing: 2px;
  text-transform: uppercase;
}

.config-row {
  display: flex;
  align-items: center;
  gap: 16px;
}

.config-label {
  font-size: 12px;
  color: rgba(255,255,255,0.4);
  width: 72px;
  flex-shrink: 0;
}

.config-input { flex: 1; }

.config-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 4px;
}

.key-status {
  font-size: 11px;
  color: rgba(255,255,255,0.25);
  letter-spacing: 1px;
}
.key-status.active { color: rgba(167,139,250,0.7); }

.save-btn {
  padding: 7px 20px;
  border-radius: 8px;
  background: linear-gradient(135deg, #6c63ff, #a78bfa);
  border: none;
  color: #fff;
  font-size: 12px;
  cursor: pointer;
  transition: opacity 0.2s;
}
.save-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.save-btn:not(:disabled):hover { opacity: 0.85; }

/* model grid */
.model-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
}

.model-card {
  position: relative;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.07);
  border-radius: 16px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: hidden;
  transition: border-color 0.3s, background 0.3s, transform 0.2s;
  animation: breathe-border 5s ease-in-out infinite;
}
.model-card:hover {
  border-color: rgba(108,99,255,0.4);
  background: rgba(108,99,255,0.05);
  transform: translateY(-2px);
}
.model-card:hover .card-glow { opacity: 1; }

.card-glow {
  position: absolute; inset: 0;
  background: radial-gradient(ellipse at top left, rgba(108,99,255,0.08) 0%, transparent 60%);
  opacity: 0;
  transition: opacity 0.3s;
  pointer-events: none;
}

.model-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.model-icon {
  width: 40px; height: 40px;
  border-radius: 12px;
  background: rgba(108,99,255,0.15);
  border: 1px solid rgba(108,99,255,0.2);
  display: flex; align-items: center; justify-content: center;
  font-size: 16px;
  font-weight: 700;
  color: #a78bfa;
}

.delete-btn {
  width: 28px; height: 28px;
  border-radius: 8px;
  background: none;
  border: 1px solid rgba(255,255,255,0.06);
  color: rgba(255,255,255,0.3);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px;
  transition: background 0.2s, color 0.2s, border-color 0.2s;
}
.delete-btn:hover {
  background: rgba(248,113,113,0.15);
  border-color: rgba(248,113,113,0.3);
  color: #f87171;
}

.model-name {
  font-size: 15px;
  font-weight: 600;
  color: rgba(255,255,255,0.88);
}

.model-id {
  font-size: 11px;
  color: rgba(255,255,255,0.3);
  letter-spacing: 0.5px;
  font-family: monospace;
}

.model-type-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 10px;
  color: rgba(167,139,250,0.9);
  background: rgba(108,99,255,0.15);
  border: 1px solid rgba(108,99,255,0.2);
  letter-spacing: 0.5px;
  width: fit-content;
}

.model-desc {
  font-size: 12px;
  color: rgba(255,255,255,0.35);
  line-height: 1.5;
}

/* empty */
.empty-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 80px 0;
}

.empty-orb {
  width: 60px; height: 60px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(108,99,255,0.12) 0%, transparent 70%);
  border: 1px solid rgba(108,99,255,0.15);
  animation: breathe 4s ease-in-out infinite;
}

.empty-text {
  font-size: 13px;
  color: rgba(255,255,255,0.25);
  letter-spacing: 1px;
}

@media (max-width: 768px) {
  .manager-page { padding: 24px 20px; }
  .model-grid { grid-template-columns: 1fr 1fr; }
}
</style>
