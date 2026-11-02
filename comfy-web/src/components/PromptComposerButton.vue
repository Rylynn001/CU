<script setup lang="ts">
import { ref } from 'vue'
import AiChatComposer from './AiChatComposer.vue'
import AiBlobWarpAvatar from './AiBlobWarpAvatar.vue'
import { Suggestion } from '@/components/ai-elements/suggestion'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger } from '@/components/ui/dialog'
const composer = ref<InstanceType<typeof AiChatComposer>>()
</script>

<template>
  <div class="ai-elements">
    <Dialog>
      <DialogTrigger as-child><button class="composer-trigger" aria-label="打开 AI 提示词助手" title="打开 AI 提示词助手"><AiBlobWarpAvatar /></button></DialogTrigger>
      <DialogContent class="ai-elements prompt-assistant-dialog" @open-auto-focus="(event) => { event.preventDefault(); composer?.focus() }">
        <DialogHeader>
          <DialogTitle class="flex items-center gap-2"><AiBlobWarpAvatar />提示词助手</DialogTitle>
          <DialogDescription>把画面、风格和细节写下来。</DialogDescription>
        </DialogHeader>
        <div class="flex flex-wrap gap-2"><Suggestion v-for="text in ['雨夜街头的电影感人像', '自然光下的产品摄影', '把想法整理成完整提示词']" :key="text" :suggestion="text" @click="composer?.setPrompt" /></div>
        <AiChatComposer ref="composer" preview-only />
      </DialogContent>
    </Dialog>
  </div>
</template>

<style scoped>
.composer-trigger { display: grid; place-items: center; width: 40px; height: 40px; padding: 4px; border-radius: 50%; border: 0; background: transparent; cursor: pointer; transition: transform .15s; }
.composer-trigger:hover { transform: scale(1.08); }
.composer-trigger:active { transform: scale(.96); }
@media (prefers-reduced-motion: reduce) { .composer-trigger { transition: none; } }
:global(.prompt-assistant-dialog) { max-width: min(640px, calc(100vw - 32px)); padding: 28px; gap: 24px; }
</style>
