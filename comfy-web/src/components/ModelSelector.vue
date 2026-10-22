<template>
  <div ref="menuRef" class="relative shrink-0">
    <button
      type="button"
      @click="toggleMenu"
      :disabled="disabled"
      class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-xl bg-zinc-100 dark:bg-white/5 hover:bg-zinc-200/70 dark:hover:bg-white/10 text-xs font-semibold text-zinc-900 dark:text-zinc-100 transition-all cursor-pointer shrink-0 whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed"
    >
      <span :class="['shrink-0', selectedModel.badgeColor]">●</span>
      <span class="truncate max-w-22.5 sm:max-w-32.5 whitespace-nowrap">
        {{ selectedModel.name }}
      </span>

      <span
        class="px-1.5 py-0.5 rounded-md text-[9px] font-mono uppercase font-bold tracking-wider bg-zinc-200/70 dark:bg-white/10 text-zinc-700 dark:text-zinc-300 shrink-0 whitespace-nowrap"
      >
        {{ currentEffortLabel }}
      </span>

      <span
        :class="[
          'text-zinc-500 dark:text-zinc-400 transition-transform shrink-0',
          { 'rotate-180': isOpen }
        ]"
      >
        ▼
      </span>
    </button>

    <!-- Dropdown Menu -->
    <transition name="dropdown">
      <div
        v-if="isOpen && !disabled"
        class="absolute bottom-full mb-2 left-0 z-30 w-68 sm:w-76 p-2.5 rounded-2xl bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-white/10 shadow-[0_15px_40px_rgba(0,0,0,0.12)] dark:shadow-[0_20px_50px_rgba(0,0,0,0.6)]"
      >
        <!-- Header -->
        <div
          class="px-2 py-1 text-[10px] font-mono uppercase tracking-wider text-zinc-500 dark:text-zinc-400 font-bold flex items-center justify-between"
        >
          <span>AI 模型</span>
          <span class="text-[9px] font-mono opacity-80">2026</span>
        </div>

        <!-- Model List -->
        <div class="space-y-0.5">
          <button
            v-for="model in models"
            :key="model.id"
            type="button"
            @click="selectModel(model)"
            :class="[
              'w-full flex items-center justify-between p-2 rounded-xl text-xs font-medium transition-colors cursor-pointer',
              selectedModel.id === model.id
                ? 'bg-zinc-100 dark:bg-white/10 text-zinc-950 dark:text-white font-semibold'
                : 'hover:bg-zinc-100/70 dark:hover:bg-white/5 text-zinc-700 dark:text-zinc-300'
            ]"
          >
            <div class="flex items-center gap-2.5">
              <span :class="model.badgeColor">●</span>
              <div class="text-left">
                <div class="leading-tight flex items-center gap-1.5">
                  <span class="font-semibold">{{ model.name }}</span>
                  <span
                    v-if="model.tag"
                    class="text-[9px] px-1 py-0.2 rounded bg-zinc-200/70 dark:bg-white/10 text-zinc-600 dark:text-zinc-300 font-mono"
                  >
                    {{ model.tag }}
                  </span>
                </div>
                <div class="text-[10px] text-zinc-500 dark:text-zinc-400 font-mono">
                  {{ model.provider }} · {{ getModelEffort(model.id).toUpperCase() }}
                </div>
              </div>
            </div>
            <span v-if="selectedModel.id === model.id" class="text-emerald-500">✓</span>
          </button>
        </div>

        <!-- Effort Level Selector -->
        <div class="mt-2.5 pt-2.5 border-t border-zinc-200 dark:border-white/10">
          <div class="px-2 pb-1.5 flex items-center justify-between">
            <span class="text-[10px] font-mono uppercase tracking-wider text-zinc-500 dark:text-zinc-400 font-bold">
              {{ selectedModel.reasoningTitle }}
            </span>
            <span class="text-[10px] font-mono uppercase font-bold text-zinc-800 dark:text-zinc-200">
              {{ currentEffortLabel }}
            </span>
          </div>

          <div
            class="grid gap-1 p-1 rounded-xl bg-zinc-100 dark:bg-white/5"
            :style="{ gridTemplateColumns: `repeat(${selectedModel.levels.length}, minmax(0, 1fr))` }"
          >
            <button
              v-for="level in selectedModel.levels"
              :key="level.id"
              type="button"
              @click="selectEffort(level.id)"
              :class="[
                'py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer text-center',
                currentEffortId === level.id
                  ? 'bg-white dark:bg-zinc-800 text-zinc-950 dark:text-white shadow-xs border border-zinc-200 dark:border-white/10'
                  : 'text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-white hover:bg-zinc-200/50 dark:hover:bg-white/5'
              ]"
            >
              <span>{{ level.label }}</span>
            </button>
          </div>

          <div class="px-2 pt-1.5 text-[10px] text-zinc-600 dark:text-zinc-400 leading-tight">
            {{ currentEffortDesc }}
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import type { AIModel } from './AiMascotInput.vue'

export interface ModelSelectorProps {
  selectedModel: AIModel
  modelEfforts: Record<string, string>
  models: AIModel[]
  disabled?: boolean
}

const props = withDefaults(defineProps<ModelSelectorProps>(), {
  disabled: false,
})

const emit = defineEmits<{
  'update:selectedModel': [model: AIModel]
  'update:modelEfforts': [efforts: Record<string, string>]
}>()

const isOpen = ref(false)
const menuRef = ref<HTMLElement | null>(null)

const currentEffortId = computed(
  () => props.modelEfforts[props.selectedModel.id] || props.selectedModel.defaultLevel
)

const currentEffortObj = computed(
  () => props.selectedModel.levels.find((l) => l.id === currentEffortId.value) || props.selectedModel.levels[0]
)

const currentEffortLabel = computed(() => currentEffortObj.value.label)
const currentEffortDesc = computed(() => currentEffortObj.value.desc)

const toggleMenu = () => {
  if (props.disabled) return
  isOpen.value = !isOpen.value
}

const selectModel = (model: AIModel) => {
  emit('update:selectedModel', model)
  // 菜单保持打开，方便调整 effort
}

const selectEffort = (levelId: string) => {
  const newEfforts = { ...props.modelEfforts }
  newEfforts[props.selectedModel.id] = levelId
  emit('update:modelEfforts', newEfforts)
}

const getModelEffort = (modelId: string) => {
  return props.modelEfforts[modelId] || props.models.find((m) => m.id === modelId)?.defaultLevel || 'medium'
}

// 点击外部关闭菜单
const handleClickOutside = (e: MouseEvent) => {
  if (menuRef.value && !menuRef.value.contains(e.target as Node)) {
    isOpen.value = false
  }
}

watch(isOpen, (newVal) => {
  if (newVal) {
    document.addEventListener('mousedown', handleClickOutside)
  } else {
    document.removeEventListener('mousedown', handleClickOutside)
  }
})

onUnmounted(() => {
  document.removeEventListener('mousedown', handleClickOutside)
})
</script>

<style scoped>
.dropdown-enter-active,
.dropdown-leave-active {
  transition: all 0.15s;
}

.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(8px) scale(0.95);
}
</style>
