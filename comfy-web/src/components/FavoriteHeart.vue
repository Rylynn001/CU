<script setup lang="ts">
import { ref, onBeforeUnmount } from 'vue'

const props = withDefaults(defineProps<{
  tag?: number
  size?: number
}>(), { tag: 0, size: 15 })

const emit = defineEmits<{
  change: [tag: 0 | 1 | 2 | 3 | 4]
}>()

// 收藏颜色定义：0=取消收藏，1=红，2=黄，3=绿，4=蓝
const COLORS: { tag: 0 | 1 | 2 | 3 | 4; color: string; label: string }[] = [
  { tag: 0, color: 'rgba(255,255,255,0.55)', label: '取消收藏' },
  { tag: 1, color: '#f43f5e', label: '红' },
  { tag: 2, color: '#eab308', label: '黄' },
  { tag: 3, color: '#22c55e', label: '绿' },
  { tag: 4, color: '#3b82f6', label: '蓝' },
]

function colorOf(tag: number) {
  return COLORS.find(c => c.tag === tag)?.color || 'rgba(255,255,255,0.6)'
}

const wrapRef = ref<HTMLElement | null>(null)
const open = ref(false)
const placement = ref<'above' | 'below'>('above')
const popupStyle = ref<Record<string, string>>({})
let closeTimer: number | undefined

function showPopup() {
  if (closeTimer) { clearTimeout(closeTimer); closeTimer = undefined }
  const el = wrapRef.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  placement.value = rect.top < 70 ? 'below' : 'above'
  popupStyle.value = {
    left: `${rect.left + rect.width / 2}px`,
    top: placement.value === 'above' ? `${rect.top}px` : `${rect.bottom}px`,
  }
  open.value = true
}

function hidePopup() {
  closeTimer = window.setTimeout(() => { open.value = false }, 150)
}

function pick(tag: 0 | 1 | 2 | 3 | 4) {
  open.value = false
  if (tag !== props.tag) emit('change', tag)
}

function quickToggle() {
  pick(props.tag > 0 ? 0 : 1)
}

onBeforeUnmount(() => { if (closeTimer) clearTimeout(closeTimer) })
</script>

<template>
  <span
    ref="wrapRef"
    class="favorite-heart"
    @mouseenter="showPopup"
    @mouseleave="hidePopup"
  >
    <button
      class="heart-btn"
      :class="{ favorited: tag > 0 }"
      :style="{ width: `${size * 2}px`, height: `${size * 2}px`, color: tag > 0 ? colorOf(tag) : undefined, background: tag > 0 ? `${colorOf(tag)}26` : undefined }"
      @click.stop="quickToggle"
      title="收藏"
    >
      <svg
        :width="size" :height="size" viewBox="0 0 24 24"
        :fill="tag > 0 ? colorOf(tag) : 'none'" stroke="currentColor"
        stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
      >
        <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
      </svg>
    </button>

    <Teleport to="body">
      <Transition name="heart-pop">
        <div
          v-if="open"
          class="heart-popup"
          :class="placement"
          :style="popupStyle"
          @mouseenter="showPopup"
          @mouseleave="hidePopup"
        >
          <button
            v-for="(c, i) in COLORS"
            :key="c.tag"
            class="mini-heart"
            :class="{ active: tag === c.tag, empty: c.tag === 0 }"
            :style="{ '--delay': `${i * 30}ms`, color: c.color }"
            :title="c.label"
            @click.stop="pick(c.tag)"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" :fill="c.tag === 0 ? 'none' : 'currentColor'" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z"/>
            </svg>
          </button>
        </div>
      </Transition>
    </Teleport>
  </span>
</template>

<style scoped>
.favorite-heart {
  display: inline-flex;
}
.heart-btn {
  width: 30px; height: 30px;
  border-radius: 50%;
  background: rgba(0,0,0,0.5);
  border: none;
  color: rgba(255,255,255,0.6);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  backdrop-filter: blur(4px);
}
.heart-btn:hover { transform: scale(1.15); }
.heart-btn.favorited { transform: scale(1); }
</style>

<style>
/* 弹出面板需 Teleport 到 body，不能用 scoped 样式 */
.heart-popup {
  position: fixed;
  display: flex;
  gap: 6px;
  padding: 7px 9px;
  border-radius: 999px;
  background: rgba(24,22,32,0.92);
  border: 1px solid rgba(255,255,255,0.12);
  backdrop-filter: blur(10px);
  box-shadow: 0 10px 28px rgba(0,0,0,0.4);
  z-index: 3000;
  opacity: 1;
  transition: opacity 0.5s;
}
.heart-popup.above { transform: translate(-50%, calc(-100% - 10px)); }
.heart-popup.below { transform: translate(-50%, 10px); }

.mini-heart {
  width: 24px; height: 24px;
  border-radius: 50%;
  border: none;
  background: rgba(255,255,255,0.06);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, transform 0.15s;
}
.mini-heart:hover { background: rgba(255,255,255,0.14); transform: scale(1.2); }
.mini-heart.active { background: rgba(255,255,255,0.18); box-shadow: 0 0 0 1.5px currentColor inset; }
.mini-heart.empty svg { opacity: 0.85; }

.heart-pop-enter-from { opacity: 0; }
.heart-pop-leave-to { opacity: 0; }
.heart-pop-leave-active { transition: opacity 0.15s ease; }

.heart-popup.heart-pop-enter-active .mini-heart {
  animation: heart-pop-in 0.36s cubic-bezier(0.34, 1.56, 0.64, 1) both;
  animation-delay: var(--delay);
}

@keyframes heart-pop-in {
  0% { transform: scale(0) translateY(6px); opacity: 0; }
  60% { transform: scale(1.18) translateY(-2px); opacity: 1; }
  100% { transform: scale(1) translateY(0); opacity: 1; }
}
</style>
