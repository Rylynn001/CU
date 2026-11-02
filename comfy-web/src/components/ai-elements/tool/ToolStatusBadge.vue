<!-- StatusBadge.vue -->
<script setup lang="ts">
import type { DynamicToolUIPart, ToolUIPart } from 'ai'
import type { Component } from 'vue'
import {
  CheckCircleIcon,
  CircleIcon,
  ClockIcon,
  XCircleIcon,
} from '@lucide/vue'
import { Badge } from '@/components/ui/badge'
import { computed } from 'vue'

export type ToolPart = ToolUIPart | DynamicToolUIPart

const props = defineProps<{
  state: ToolPart['state']
}>()

const label = computed(() => {
  const labels: Record<ToolPart['state'], string> = {
    'input-streaming': '等待中',
    'input-available': '执行中',
    'approval-requested': '等待确认',
    'approval-responded': '已确认',
    'output-available': '已完成',
    'output-error': '失败',
    'output-denied': '已取消',
  }
  return labels[props.state]
})

const icon = computed<Component>(() => {
  const icons: Record<ToolPart['state'], Component> = {
    'input-streaming': CircleIcon,
    'input-available': ClockIcon,
    'approval-requested': ClockIcon,
    'approval-responded': CheckCircleIcon,
    'output-available': CheckCircleIcon,
    'output-error': XCircleIcon,
    'output-denied': XCircleIcon,
  }
  return icons[props.state]
})

const iconClass = computed(() => {
  const classes: Record<ToolPart['state'], string> = {
    'input-streaming': 'size-4',
    'input-available': 'size-4 animate-pulse',
    'approval-requested': 'size-4 text-muted-foreground',
    'approval-responded': 'size-4 text-muted-foreground',
    'output-available': 'size-4 text-muted-foreground',
    'output-error': 'size-4 text-destructive',
    'output-denied': 'size-4 text-muted-foreground',
  }
  return classes[props.state]
})
</script>

<template>
  <Badge class="gap-1.5 rounded-full text-xs" variant="secondary">
    <component :is="icon" :class="iconClass" />
    <span>{{ label }}</span>
  </Badge>
</template>
