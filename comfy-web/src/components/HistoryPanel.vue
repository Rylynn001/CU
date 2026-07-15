<script setup lang="ts">
// 历史记录面板：搜索框 + 记录行（参考图/参考素材展开）+ RecordCard + 分页
// 图片页和视频页共用，结果区域（图片网格 / 视频播放器）通过 #result 插槽由父组件决定
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
  locatedRecordId?: string | null
}>(), {
  referenceLabel: '参考图',
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
</script>

<template>
  <div class="history-col">
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
          @delete="emit('delete', $event)"
          @retry="emit('retry', $event)"
          @edit="emit('edit', $event)"
        >
          <template #prompt><slot name="prompt" :record="rec" /></template>
          <template #progress><slot name="progress" :record="rec" /></template>
          <template #result><slot name="result" :record="rec" /></template>
        </RecordCard>
      </div>

      <!-- 分页控件 -->
      <div class="history-pagination">
        <div class="page-size-group">
          <span class="page-size-label">每页</span>
          <button
            v-for="n in [30, 50, 100]" :key="n"
            class="page-size-btn" :class="{ active: dbPageSize === n }"
            @click="emit('update:dbPageSize', n as 30 | 50 | 100); emit('page-size-change', n as 30 | 50 | 100)"
          >{{ n }}</button>
        </div>
        <button
          v-if="hasMoreInDb"
          class="load-more-btn"
          :disabled="loadingMore"
          @click="emit('load-more')"
        >{{ loadingMore ? '加载中...' : '加载更多' }}</button>
        <span v-else-if="totalCount > 0" class="no-more-text">已全部加载</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
@import '../styles/generation-page.css';
</style>
