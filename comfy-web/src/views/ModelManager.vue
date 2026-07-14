<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElIcon, ElInput, ElMessage } from 'element-plus'
import { Delete, Plus, Setting } from '@element-plus/icons-vue'
import {
  addApiModel, deleteApiModel, getApiConfig, getApiModels, saveApiConfig,
  type ApiModel,
} from '../api/apiService'

const models = ref<ApiModel[]>([])
const loading = ref(false)
const showConfig = ref(false)
const showAdd = ref(false)
const configLoading = ref(false)
const addLoading = ref(false)
const hasKey = ref(false)
const configForm = ref({ api_key: '', base_url: '' })
const addForm = ref({ id: '', name: '', description: '', type: 'image' as const })

const imageModels = computed(() => models.value.filter(model => model.type === 'image'))

async function loadModels() {
  loading.value = true
  try { models.value = await getApiModels('image') }
  catch (error: any) { ElMessage.error(`加载模型失败：${error.message}`) }
  finally { loading.value = false }
}

async function loadConfig() {
  try {
    const config = await getApiConfig()
    configForm.value.base_url = config.base_url
    hasKey.value = config.has_key
  } catch { /* 配置状态不影响默认模型展示 */ }
}

async function handleSaveConfig() {
  configLoading.value = true
  try {
    await saveApiConfig({
      base_url: configForm.value.base_url || undefined,
      api_key: configForm.value.api_key || undefined,
    })
    hasKey.value = Boolean(configForm.value.api_key) || hasKey.value
    configForm.value.api_key = ''
    showConfig.value = false
    await loadModels()
    ElMessage.success('API 配置已保存')
  } catch (error: any) { ElMessage.error(`保存失败：${error.message}`) }
  finally { configLoading.value = false }
}

async function handleAddModel() {
  if (!addForm.value.id || !addForm.value.name) {
    ElMessage.warning('请填写模型 ID 和显示名称')
    return
  }
  addLoading.value = true
  try {
    await addApiModel({ ...addForm.value })
    addForm.value = { id: '', name: '', description: '', type: 'image' }
    showAdd.value = false
    await loadModels()
    ElMessage.success('模型已添加')
  } catch (error: any) { ElMessage.error(`添加失败：${error.message}`) }
  finally { addLoading.value = false }
}

async function handleDelete(model: ApiModel) {
  if (!model.databaseId) {
    ElMessage.info('默认模型不可删除')
    return
  }
  try {
    await deleteApiModel(String(model.databaseId))
    await loadModels()
    ElMessage.success(`已删除 ${model.name}`)
  } catch (error: any) { ElMessage.error(`删除失败：${error.message}`) }
}

onMounted(() => { loadModels(); loadConfig() })
</script>

<template>
  <main class="model-manager">
    <header class="page-head">
      <div>
        <p>开发者工具</p>
        <h1>模型管理</h1>
        <span>管理图片生成所使用的 API 模型与服务配置。</span>
      </div>
      <div class="head-actions">
        <button class="quiet-btn" @click="showConfig = !showConfig"><el-icon><Setting /></el-icon> API 配置</button>
        <button class="primary-btn" @click="showAdd = !showAdd"><el-icon><Plus /></el-icon> 添加模型</button>
      </div>
    </header>

    <section v-if="showConfig" class="editor-panel">
      <div class="panel-heading"><h2>APIYi 配置</h2><span :class="{ active: hasKey }">{{ hasKey ? 'API Key 已配置' : 'API Key 未配置' }}</span></div>
      <label><span>Base URL</span><ElInput v-model="configForm.base_url" placeholder="https://api.apiyi.com/v1" /></label>
      <label><span>API Key</span><ElInput v-model="configForm.api_key" type="password" show-password :placeholder="hasKey ? '留空则不修改' : '输入 API Key'" /></label>
      <div class="panel-footer"><button class="primary-btn" :disabled="configLoading" @click="handleSaveConfig">{{ configLoading ? '保存中…' : '保存配置' }}</button></div>
    </section>

    <section v-if="showAdd" class="editor-panel">
      <div class="panel-heading"><h2>添加图片模型</h2></div>
      <label><span>模型 ID</span><ElInput v-model="addForm.id" placeholder="例如 gpt-image-2" /></label>
      <label><span>显示名称</span><ElInput v-model="addForm.name" placeholder="例如 GPT Image 2" /></label>
      <label><span>描述</span><ElInput v-model="addForm.description" placeholder="可选" /></label>
      <div class="panel-footer"><button class="primary-btn" :disabled="addLoading" @click="handleAddModel">{{ addLoading ? '添加中…' : '确认添加' }}</button></div>
    </section>

    <section class="model-section">
      <div class="section-head"><div><h2>图片模型</h2><span>{{ imageModels.length }} 个可用模型</span></div></div>
      <div v-if="loading" class="empty-state">正在加载模型…</div>
      <div v-else class="model-list">
        <article v-for="model in imageModels" :key="model.id" class="model-row">
          <div class="provider-mark" :class="model.provider">{{ model.provider === 'gemini' ? 'G' : 'O' }}</div>
          <div class="model-copy">
            <div class="model-title"><strong>{{ model.name }}</strong><span>{{ model.provider === 'gemini' ? 'Gemini' : 'OpenAI' }}</span></div>
            <code>{{ model.id }}</code>
            <p>{{ model.description }}</p>
          </div>
          <div class="model-status"><i /> 可用</div>
          <button v-if="model.databaseId" class="delete-btn" title="删除模型" @click="handleDelete(model)"><el-icon><Delete /></el-icon></button>
        </article>
      </div>
    </section>
  </main>
</template>

<style scoped>
.model-manager { min-height: calc(100vh - 22px); padding: 52px 48px 80px; box-sizing:border-box; display:flex; flex-direction:column; align-items:center; color: var(--color-text); background: rgba(2,4,8,.72); }
.page-head { display:flex; align-items:flex-end; justify-content:space-between; gap:28px; width:min(100%,960px); }
.page-head p { margin:0 0 10px; color:var(--color-primary); font-size:11px; }
.page-head h1 { margin:0; font-size:30px; font-weight:600; letter-spacing:-.02em; }
.page-head span { display:block; margin-top:12px; color:var(--color-muted); font-size:13px; }
.head-actions { display:flex; gap:10px; flex-shrink:0; }
button { height:36px; padding:0 14px; border-radius:8px; color:var(--color-text); font-size:12px; cursor:pointer; display:inline-flex; align-items:center; gap:7px; }
.quiet-btn { border:1px solid var(--color-border); background:rgba(255,255,255,.045); }
.quiet-btn:hover { background:rgba(255,255,255,.08); }
.primary-btn { border:1px solid rgba(166,231,226,.34); background:rgba(166,231,226,.12); color:var(--color-primary-strong); }
.primary-btn:hover { background:rgba(166,231,226,.18); }.primary-btn:disabled { opacity:.45; cursor:not-allowed; }
.editor-panel { width:min(100%,720px); margin-top:34px; padding:22px 0; border-top:1px solid var(--color-border); border-bottom:1px solid var(--color-border); display:grid; gap:16px; }
.panel-heading { display:flex; justify-content:space-between; align-items:center; }.panel-heading h2 { margin:0; font-size:16px; font-weight:500; }.panel-heading span { color:var(--color-faint); font-size:11px; }.panel-heading span.active { color:var(--color-success); }
.editor-panel label { display:grid; grid-template-columns:100px 1fr; align-items:center; gap:18px; }.editor-panel label>span { color:var(--color-muted); font-size:12px; }.panel-footer { display:flex; justify-content:flex-end; }
.model-section { width:min(100%,960px); margin-top:52px; }.section-head { padding-bottom:16px; border-bottom:1px solid var(--color-border); }.section-head h2 { display:inline; margin:0; font-size:18px; font-weight:500; }.section-head span { margin-left:12px; color:var(--color-faint); font-size:11px; }
.model-list { display:flex; flex-direction:column; }.model-row { min-height:104px; display:grid; grid-template-columns:42px minmax(0,1fr) auto 32px; align-items:center; gap:18px; padding:18px 4px; border-bottom:1px solid rgba(255,255,255,.08); }
.provider-mark { width:38px; height:38px; border-radius:8px; display:grid; place-items:center; background:rgba(255,255,255,.06); color:var(--color-text); font-size:14px; font-weight:600; }.provider-mark.gemini { color:#b9b9ff; background:rgba(130,120,255,.12); }.provider-mark.openai { color:var(--color-primary); background:rgba(166,231,226,.1); }
.model-copy { min-width:0; }.model-title { display:flex; align-items:center; gap:10px; }.model-title strong { font-size:14px; font-weight:500; }.model-title span { padding:2px 6px; border:1px solid var(--color-border); border-radius:4px; color:var(--color-muted); font-size:10px; }.model-copy code { display:block; margin-top:7px; color:var(--color-muted); font-size:11px; }.model-copy p { margin:6px 0 0; color:var(--color-faint); font-size:11px; }
.model-status { color:var(--color-muted); font-size:11px; white-space:nowrap; }.model-status i { display:inline-block; width:6px; height:6px; margin-right:6px; border-radius:50%; background:var(--color-success); }.delete-btn { width:30px; padding:0; justify-content:center; border:0; background:transparent; color:var(--color-faint); }.delete-btn:hover { color:var(--color-danger); background:rgba(251,113,133,.08); }.empty-state { padding:70px 0; color:var(--color-faint); font-size:12px; text-align:center; }
@media (max-width:760px) { .model-manager{padding:32px 22px 60px}.page-head{align-items:flex-start;flex-direction:column}.head-actions{width:100%}.head-actions button{flex:1;justify-content:center}.editor-panel label{grid-template-columns:1fr;gap:7px}.model-row{grid-template-columns:38px minmax(0,1fr) auto}.model-status{display:none} }
</style>
