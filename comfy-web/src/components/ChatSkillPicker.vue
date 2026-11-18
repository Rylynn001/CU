<script setup lang="ts">
import { computed } from 'vue'
import { Sparkles, RefreshCw, X } from '@lucide/vue'
import { Button } from '@/components/ui/button'
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuRadioGroup, DropdownMenuRadioItem } from '@/components/ui/dropdown-menu'
import type { ChatSkill } from '@/api/workflow'

const props = defineProps<{ modelValue: string; skills: ChatSkill[]; loading?: boolean; error?: string; disabled?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [string]; refresh: [] }>()
const selectedSkill = computed(() => props.skills.find(skill => skill.id === props.modelValue))
</script>

<template>
  <div class="ai-elements skill-picker">
    <DropdownMenu @update:open="open => { if (open) emit('refresh') }">
      <DropdownMenuTrigger as-child>
        <Button type="button" variant="ghost" size="sm" class="skill-trigger" :disabled="disabled" aria-label="选择技能" :title="selectedSkill ? `当前技能：${selectedSkill.name}` : '选择本轮对话使用的技能'">
          <Sparkles :size="14" /><span>{{ selectedSkill?.name || '技能' }}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent class="ai-elements skill-menu" align="end">
        <DropdownMenuRadioGroup :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)">
          <DropdownMenuRadioItem value="">不指定技能</DropdownMenuRadioItem>
          <DropdownMenuRadioItem v-for="skill in skills" :key="skill.id" :value="skill.id" :title="skill.description">{{ skill.name }}</DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
        <p v-if="error" role="alert" class="skill-status">{{ error }}</p>
        <p v-else-if="!skills.length && !loading" class="skill-status">暂无可用技能</p>
        <DropdownMenuSeparator />
        <DropdownMenuItem :disabled="loading" @select.prevent="emit('refresh')"><RefreshCw :size="14" :class="{ 'animate-spin': loading }" />{{ loading ? '正在扫描…' : '刷新技能列表' }}</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
    <Button v-if="modelValue" type="button" variant="ghost" size="icon-xs" :disabled="disabled" aria-label="取消所选技能" title="取消所选技能" @click="emit('update:modelValue', '')"><X :size="12" /></Button>
  </div>
</template>

<style scoped>
.skill-picker { display: inline-flex; align-items: center; min-width: 0; max-width: min(150px, 40vw); flex-shrink: 1; }
.skill-trigger { min-width: 0; max-width: 125px; flex-shrink: 1; color: var(--color-muted); }
.skill-trigger span { display: block; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.skill-menu { max-width: min(320px, calc(100vw - 24px)); max-height: 320px; overflow-y: auto; }
.skill-status { padding: 8px; color: var(--color-muted); font-size: 12px; }
</style>
