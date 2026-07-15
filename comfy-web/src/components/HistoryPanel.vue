<script setup lang="ts">
// 历史记录面板：搜索框 + 记录行（参考图/参考素材展开）+ RecordCard + 分页
// 图片页和视频页共用，结果区域（图片网格 / 视频播放器）通过 #result 插槽由父组件决定
import { ref, onMounted, onUnmounted } from 'vue'
import RecordCard from './RecordCard.vue'

interface BaseRecord {
  id: string
  status: 'generating' | 'done' | 'error'
  taskId?: string
  createdAt: number
  modelName: string
  errorMsg?: string
  inputAssetUrls?: Array<{ url: string; type: string }>
  inputPreviews?: string[]
}

const props = withDefaults(defineProps<{
  records: BaseRecord[]
  totalCount: number
  referenceLabel?: string
  searchQuery: string
  expandedInputs: Set<string>
  dbPageSize: 30 | 50 | 100
  hasMoreInDb: boolean
  loadingMore: boolean
  editingRecordId?: string
  showRecordEditor?: boolean
  showEditButton?: boolean
  locatedRecordId?: string | null
}>(), {
  referenceLabel: '参考图',
  showEditButton: true,
})

const emit = defineEmits<{
  (e: 'update:searchQuery', v: string): void
  (e: 'update:dbPageSize', v: 30 | 50 | 100): void
  (e: 'toggle-input-expand', id: string): void
  (e: 'preview-image', url: string): void
  (e: 'delete', id: string): void
  (e: 'retry', record: any): void
  (e: 'edit', id: string): void
  (e: 'page-size-change', n: 30 | 50 | 100): void
  (e: 'load-more'): void
}>()

function hasReference(rec: BaseRecord) {
  return !!(rec.inputAssetUrls?.length || rec.inputPreviews?.length)
}

const historyColRef = ref<HTMLElement | null>(null)

function onScroll() {
  const el = historyColRef.value
  if (!el || props.loadingMore || !props.hasMoreInDb) return
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 150) {
    emit('load-more')
  }
}

onMounted(() => {
  historyColRef.value?.addEventListener('scroll', onScroll, { passive: true })
})
onUnmounted(() => {
  historyColRef.value?.removeEventListener('scroll', onScroll)
})
</script>

<template>
  <div class="history-col" ref="historyColRef">
    <div v-if="records.length === 0 && totalCount === 0" class="empty-wrap">
      <div class="empty-orb" />
      <p class="empty-text">等待生成</p>
    </div>
    <div v-else class="stream">
      <!-- 搜索框 -->
      <div class="stream-header">
        <span class="stream-title">历史记录 ({{ records.length }})</span>
        <input
          :value="searchQuery"
          class="search-input"
          placeholder="搜索提示词..."
          @input="emit('update:searchQuery', ($event.target as HTMLInputElement).value)"
        />
      </div>

      <div
        v-for="rec in records" :key="rec.id" class="record-row" :data-record-id="rec.id"
        :class="{ 'editing': showRecordEditor && editingRecordId === rec.id, 'record-located': locatedRecordId === rec.id }"
      >
        <!-- 左侧参考图/参考素材 -->
        <div class="record-input-col">
          <template v-if="hasReference(rec)">
            <button class="input-toggle-btn" @click="emit('toggle-input-expand', rec.id)">
              {{ referenceLabel }}
              <span class="input-toggle-arrow" :class="{ open: expandedInputs.has(rec.id) }">›</span>
            </button>
            <template v-if="expandedInputs.has(rec.id)">
              <template v-if="rec.inputAssetUrls && rec.inputAssetUrls.length">
                <template v-for="(a, i) in rec.inputAssetUrls" :key="'a' + i">
                  <video v-if="a.type === 'video'" :src="a.url" class="input-panel-thumb" controls />
                  <img v-else :src="a.url" class="input-panel-thumb" @click="emit('preview-image', a.url)" />
                </template>
              </template>
              <template v-else-if="rec.inputPreviews && rec.inputPreviews.length">
                <img v-for="(p, i) in rec.inputPreviews" :key="i" :src="p" class="input-panel-thumb" @click="emit('preview-image', p)" />
              </template>
            </template>
          </template>
        </div>
        <!-- 右侧卡片 -->
        <RecordCard
          class="record-card-flex" :record="rec as any"
          :show-edit-button="showEditButton"
          @delete="emit('delete', $event)"
          @retry="emit('retry', $event)"
          @edit="emit('edit', $event)"
        >
          <template #prompt><slot name="prompt" :record="rec" /></template>
          <template #progress><slot name="progress" :record="rec" /></template>
          <template #result><slot name="result" :record="rec" /></template>
        </RecordCard>
      </div>

      <div class="history-pagination">
        <span v-if="loadingMore" class="no-more-text">加载中...</span>
        <span v-else-if="!hasMoreInDb && totalCount > 0" class="no-more-text">已全部加载</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
@import '../styles/generation-page.css';

.history-pagination {
  display: flex;
  justify-content: center;
  width: 100%;
  padding: 18px 0 8px;
}

.no-more-text {
  display: flex;
  align-items: center;
  width: min(240px, 72%);
  gap: 12px;
  color: rgba(255, 255, 255, 0.32);
  font-size: 12px;
  line-height: 1;
  text-align: center;
  white-space: nowrap;
}

.no-more-text::before,
.no-more-text::after {
  content: '';
  height: 1px;
  flex: 1;
  background: rgba(255, 255, 255, 0.08);
}
</style>
