<script setup lang="ts">
import { watch, onBeforeUnmount } from 'vue'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ 'update:visible': [boolean]; 'capture': [File] }>()

async function dataUrlToFile(dataUrl: string, fileName: string) {
  const res = await fetch(dataUrl)
  const blob = await res.blob()
  return new File([blob], fileName, { type: blob.type })
}

function handleMessage(event: MessageEvent) {
  if (!event.data || typeof event.data.type !== 'string') return

  if (event.data.type === 'storyai:director-desk-close') {
    emit('update:visible', false)
    return
  }

  if (event.data.type === 'storyai:director-desk-captures-sent') {
    const captures = event.data.payload?.captures
    if (!Array.isArray(captures)) return
    for (const capture of captures) {
      if (capture?.dataUrl) {
        dataUrlToFile(capture.dataUrl, capture.fileName ?? 'capture.png')
          .then(file => emit('capture', file))
      }
    }
  }
}

watch(() => props.visible, (val) => {
  if (val) {
    window.addEventListener('message', handleMessage)
  } else {
    window.removeEventListener('message', handleMessage)
  }
}, { immediate: true })

onBeforeUnmount(() => {
  window.removeEventListener('message', handleMessage)
})
</script>

<template>
  <teleport to="body">
    <transition name="mv-fade">
      <div v-if="visible" class="mv-overlay">
        <iframe
          class="mv-frame"
          src="/director/index.html"
          allow="accelerometer; camera; fullscreen; gyroscope; microphone"
          title="3D导演台"
        />
      </div>
    </transition>
  </teleport>
</template>

<style scoped>
.mv-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  background: #000;
}

.mv-frame {
  width: 100%;
  height: 100%;
  border: none;
}

.mv-fade-enter-active,
.mv-fade-leave-active {
  transition: opacity 0.2s ease;
}

.mv-fade-enter-from,
.mv-fade-leave-to {
  opacity: 0;
}
</style>
