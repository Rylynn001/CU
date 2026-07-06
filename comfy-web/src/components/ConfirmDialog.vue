<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  visible: boolean
  title?: string
  message?: string
  confirmText?: string
  cancelText?: string
  type?: 'danger' | 'warning' | 'info'
  confirmLoading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: '确认操作',
  message: '确定要执行此操作吗？',
  confirmText: '确认',
  cancelText: '取消',
  type: 'danger',
  confirmLoading: false,
})

const emit = defineEmits<{
  (e: 'confirm'): void
  (e: 'cancel'): void
}>()

const typeColors = computed(() => {
  switch (props.type) {
    case 'danger':
      return {
        border: 'rgba(248, 113, 113, 0.3)',
        bg: 'rgba(248, 113, 113, 0.15)',
        hover: 'rgba(248, 113, 113, 0.25)',
        text: '#f87171',
      }
    case 'warning':
      return {
        border: 'rgba(251, 191, 36, 0.3)',
        bg: 'rgba(251, 191, 36, 0.15)',
        hover: 'rgba(251, 191, 36, 0.25)',
        text: '#fbbf24',
      }
    case 'info':
      return {
        border: 'rgba(108, 99, 255, 0.3)',
        bg: 'rgba(108, 99, 255, 0.15)',
        hover: 'rgba(108, 99, 255, 0.25)',
        text: '#a78bfa',
      }
    default:
      return {
        border: 'rgba(248, 113, 113, 0.3)',
        bg: 'rgba(248, 113, 113, 0.15)',
        hover: 'rgba(248, 113, 113, 0.25)',
        text: '#f87171',
      }
  }
})
</script>

<template>
  <Teleport to="body">
    <Transition name="dialog-fade">
      <div v-if="visible" class="confirm-dialog-overlay" @click="emit('cancel')">
        <Transition name="dialog-scale">
          <div v-if="visible" class="confirm-dialog-content" @click.stop>
            <div class="dialog-icon" :class="type">
              <svg v-if="type === 'danger'" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8" x2="12" y2="12"/>
                <line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
              <svg v-else-if="type === 'warning'" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                <line x1="12" y1="9" x2="12" y2="13"/>
                <line x1="12" y1="17" x2="12.01" y2="17"/>
              </svg>
              <svg v-else width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="16" x2="12" y2="12"/>
                <line x1="12" y1="8" x2="12.01" y2="8"/>
              </svg>
            </div>

            <h3 class="dialog-title">{{ title }}</h3>
            <p class="dialog-message">{{ message }}</p>

            <div class="dialog-actions">
              <button class="dialog-btn cancel-btn" @click="emit('cancel')" :disabled="confirmLoading">
                {{ cancelText }}
              </button>
              <button
                class="dialog-btn confirm-btn"
                :class="type"
                @click="emit('confirm')"
                :disabled="confirmLoading"
                :style="{
                  borderColor: typeColors.border,
                  background: typeColors.bg,
                  color: typeColors.text,
                }"
              >
                <span v-if="confirmLoading" class="loading-spinner"></span>
                <span v-else>{{ confirmText }}</span>
              </button>
            </div>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.confirm-dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 3000;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(8px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.confirm-dialog-content {
  position: relative;
  width: 100%;
  max-width: 420px;
  background: linear-gradient(135deg, rgba(20, 20, 35, 0.98) 0%, rgba(15, 15, 25, 0.98) 100%);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 20px;
  padding: 32px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

.dialog-icon {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  animation: icon-pulse 2s ease-in-out infinite;
}

.dialog-icon.danger {
  background: rgba(248, 113, 113, 0.1);
  border: 2px solid rgba(248, 113, 113, 0.3);
  color: #f87171;
}

.dialog-icon.warning {
  background: rgba(251, 191, 36, 0.1);
  border: 2px solid rgba(251, 191, 36, 0.3);
  color: #fbbf24;
}

.dialog-icon.info {
  background: rgba(108, 99, 255, 0.1);
  border: 2px solid rgba(108, 99, 255, 0.3);
  color: #a78bfa;
}

@keyframes icon-pulse {
  0%, 100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.05);
    opacity: 0.9;
  }
}

.dialog-title {
  font-size: 20px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.95);
  margin: 0;
  text-align: center;
  letter-spacing: 0.3px;
}

.dialog-message {
  font-size: 14px;
  color: rgba(255, 255, 255, 0.6);
  margin: 0;
  text-align: center;
  line-height: 1.6;
  max-width: 320px;
}

.dialog-actions {
  display: flex;
  gap: 12px;
  width: 100%;
  margin-top: 8px;
}

.dialog-btn {
  flex: 1;
  height: 44px;
  border-radius: 12px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  border: 1px solid;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
}

.dialog-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.cancel-btn {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.1);
  color: rgba(255, 255, 255, 0.7);
}

.cancel-btn:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.2);
  color: rgba(255, 255, 255, 0.9);
  transform: translateY(-1px);
}

.cancel-btn:active:not(:disabled) {
  transform: translateY(0);
}

.confirm-btn {
  position: relative;
}

.confirm-btn:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 8px 20px rgba(0, 0, 0, 0.3);
  opacity: 0.9;
}

.confirm-btn:active:not(:disabled) {
  transform: translateY(0);
}

.confirm-btn.danger:hover:not(:disabled) {
  background: rgba(248, 113, 113, 0.25) !important;
  border-color: rgba(248, 113, 113, 0.5) !important;
}

.confirm-btn.warning:hover:not(:disabled) {
  background: rgba(251, 191, 36, 0.25) !important;
  border-color: rgba(251, 191, 36, 0.5) !important;
}

.confirm-btn.info:hover:not(:disabled) {
  background: rgba(108, 99, 255, 0.25) !important;
  border-color: rgba(108, 99, 255, 0.5) !important;
}

.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.2);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 动画 */
.dialog-fade-enter-active,
.dialog-fade-leave-active {
  transition: opacity 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.dialog-fade-enter-from,
.dialog-fade-leave-to {
  opacity: 0;
}

.dialog-scale-enter-active {
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.dialog-scale-leave-active {
  transition: all 0.2s cubic-bezier(0.4, 0, 1, 1);
}

.dialog-scale-enter-from {
  opacity: 0;
  transform: scale(0.9) translateY(-20px);
}

.dialog-scale-leave-to {
  opacity: 0;
  transform: scale(0.95) translateY(10px);
}
</style>
