<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Brain, Check, ChevronDown, CircleAlert, LoaderCircle } from '@lucide/vue'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { Tool, ToolContent, ToolHeader, ToolInput, ToolOutput } from '@/components/ai-elements/tool'
import type { WorkflowTrace } from '@/api/workflow'

const props = defineProps<{
  events?: WorkflowTrace[]
  steps?: string[]
  processing: boolean
  failed?: boolean
}>()
const expanded = ref(props.processing)
watch(() => props.processing, value => { expanded.value = value })

const toolNames: Record<string, string> = {
  discover_tools: '查找可用工具',
  txt2img: '文字生成图片',
  txt2video: '文字生成视频',
  img2img: '参考图片生成图片',
  img2video: '参考图片生成视频',
  generation_plan: '创建多步生成计划',
}

const entries = computed(() => {
  const events = props.events ?? []
  return events.flatMap((event, index) => {
    if (event.type === 'tool_result') return []
    if (event.type === 'model_request') return [{ key: `model-${index}`, event, result: undefined }]
    const result = events.find(candidate => candidate.type === 'tool_result'
      && candidate.round === event.round && candidate.call_id === event.call_id)
    return [{ key: `tool-${index}`, event, result: result?.type === 'tool_result' ? result : undefined }]
  })
})

function toolError(entry: typeof entries.value[number]) {
  const error = entry.result?.output.error
  if (error) return typeof error === 'string' ? error : JSON.stringify(error)
  if (!entry.result && !props.processing) return '未收到工具返回结果。'
  return undefined
}

function toolState(entry: typeof entries.value[number]) {
  if (toolError(entry)) return 'output-error' as const
  if (entry.result?.output.selection_required) return 'approval-requested' as const
  return entry.result ? 'output-available' as const : 'input-available' as const
}
</script>

<template>
  <Collapsible v-model:open="expanded" class="ai-elements execution-trace">
    <CollapsibleTrigger class="trace-trigger">
      <LoaderCircle v-if="processing" :size="15" class="trace-spinner" />
      <CircleAlert v-else-if="failed" :size="15" class="trace-error" />
      <Brain v-else :size="15" />
      <span>{{ processing ? '正在思考与执行' : failed ? '处理已中断' : '思考与执行过程' }}</span>
      <span v-if="entries.length" class="trace-count">{{ entries.length }} 个步骤</span>
      <ChevronDown :size="14" class="trace-chevron" :class="{ expanded }" />
    </CollapsibleTrigger>
    <CollapsibleContent class="trace-content">
      <div v-for="(step, index) in steps" :key="index" class="trace-step">
        <LoaderCircle v-if="processing && index === (steps?.length ?? 0) - 1" :size="13" class="trace-spinner" />
        <CircleAlert v-else-if="failed && index === (steps?.length ?? 0) - 1" :size="13" class="trace-error" />
        <Check v-else :size="13" />
        <span>{{ step }}</span>
      </div>
      <template v-for="entry in entries" :key="entry.key">
        <div v-if="entry.event.type === 'model_request'" class="trace-step model-step">
          <Brain :size="14" />
          <div><span>模型思考 · 第 {{ entry.event.round }} 轮</span><small>{{ entry.event.model }}</small></div>
        </div>
        <Tool v-else class="trace-tool">
          <ToolHeader type="dynamic-tool" :tool-name="entry.event.name" :title="toolNames[entry.event.name] || entry.event.name" :state="toolState(entry)" />
          <ToolContent class="trace-tool-content">
            <ToolInput :input="entry.event.input" />
            <ToolOutput :output="entry.result?.output" :error-text="toolError(entry)" />
          </ToolContent>
        </Tool>
      </template>
      <p v-if="!steps?.length && !entries.length" class="trace-waiting">正在等待模型响应…</p>
    </CollapsibleContent>
  </Collapsible>
</template>

<style scoped>
.execution-trace { width: 100%; min-width: 0; margin-bottom: 10px; color: var(--color-muted); }
.trace-trigger { display: flex; align-items: center; gap: 8px; width: 100%; padding: 8px 0; border: 0; background: transparent; color: inherit; text-align: left; font-size: 12px; cursor: pointer; }
.trace-trigger:hover { color: var(--color-text); }
.trace-trigger > svg { flex-shrink: 0; }
.trace-count { margin-left: auto; font-size: 11px; color: var(--color-faint); }
.trace-chevron { margin-left: auto; transition: transform .2s; }
.trace-count + .trace-chevron { margin-left: 0; }
.trace-chevron.expanded { transform: rotate(180deg); }
.trace-content { padding: 6px 0 2px 14px; border-left: 1px solid var(--color-border); margin-left: 7px; }
.trace-step { display: flex; align-items: flex-start; gap: 8px; padding: 5px 0; font-size: 12px; line-height: 1.6; overflow-wrap: anywhere; }
.trace-step > svg { flex-shrink: 0; margin-top: 3px; }
.model-step small { display: block; color: var(--color-faint); font-size: 11px; }
.trace-tool { margin: 8px 0; overflow: hidden; border-radius: 10px; background: var(--color-surface-soft); }
.trace-tool :deep(button) { gap: 8px; text-align: left; }
.trace-tool :deep(button > div) { min-width: 0; flex-wrap: wrap; }
.trace-tool :deep(button .font-medium) { font-size: 12px; overflow-wrap: anywhere; }
.trace-tool-content { max-height: 280px; overflow: auto; }
.trace-waiting { padding: 5px 0; font-size: 12px; }
.trace-error { color: var(--color-danger); }
.trace-spinner { animation: trace-spin 1s linear infinite; }
@keyframes trace-spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .trace-spinner { animation: none; } .trace-chevron { transition: none; } }
</style>
