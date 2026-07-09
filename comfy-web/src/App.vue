<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Brush, MagicStick } from '@element-plus/icons-vue'
import SideNav from './components/SideNav.vue'
import PrismBackground from './components/PrismBackground.vue'
import LightRaysBackground from './components/LightRaysBackground.vue'
import DotFieldBackground from './components/DotFieldBackground.vue'

const route = useRoute()
const keepPrismBackground = computed(() => route.path === '/login' || route.path === '/')
const businessTheme = ref(localStorage.getItem('business-theme') === 'dot' ? 'dot' : 'light')
const isDotTheme = computed(() => businessTheme.value === 'dot')

function toggleBusinessTheme() {
  businessTheme.value = isDotTheme.value ? 'light' : 'dot'
  localStorage.setItem('business-theme', businessTheme.value)
}
</script>

<template>
  <PrismBackground
    v-if="keepPrismBackground"
    animation-type="rotate"
    :time-scale="0.4"
    :height="3.4"
    :base-width="5.5"
    :scale="3.6"
    :hue-shift="0"
    :color-frequency="1"
    :noise="0"
    :glow="1"
  />
  <template v-else>
    <DotFieldBackground
      v-if="isDotTheme"
      :dot-radius="1.5"
      :dot-spacing="25"
      :bulge-strength="20"
      :glow-radius="160"
      :sparkle="false"
      :wave-amplitude="0"
      :cursor-radius="100"
      :cursor-force="0.03"
      :bulge-only="false"
      gradient-from="#ffffff"
      gradient-to="#B497CF"
      glow-color="#000000"
    />
    <LightRaysBackground
      v-else
      rays-origin="top-center"
      rays-color="#ffffff"
      :rays-speed="0.8"
      :light-spread="1"
      :ray-length="2"
      :fade-distance="1"
      :saturation="1"
      :mouse-influence="0.08"
      :noise-amount="0"
      :distortion="0.03"
    />
    <button
      type="button"
      class="theme-toggle"
      :aria-label="isDotTheme ? '切换到光束主题' : '切换到点阵主题'"
      :title="isDotTheme ? '切换到光束主题' : '切换到点阵主题'"
      @click="toggleBusinessTheme"
    >
      <el-icon aria-hidden="true">
        <component :is="isDotTheme ? MagicStick : Brush" />
      </el-icon>
    </button>
  </template>
  <SideNav />
  <div class="main-content" :class="{ 'theme-dot': isDotTheme && !keepPrismBackground }">
    <RouterView v-slot="{ Component, route }">
      <KeepAlive :include="['TextToImage', 'TextToVideo']">
        <component :is="Component" :key="route.name" />
      </KeepAlive>
    </RouterView>
  </div>
</template>

<style>
.main-content {
  margin-left: 64px;
  min-height: 100vh;
  transition: margin-left 0.25s ease;
}

.theme-toggle {
  position: fixed;
  top: 18px;
  right: 18px;
  z-index: 120;
  width: 42px;
  height: 42px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: rgba(5, 7, 12, 0.58);
  color: var(--color-text);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  backdrop-filter: var(--glass-blur);
  box-shadow: 0 16px 42px rgba(0, 0, 0, 0.24);
  transition: color 0.2s ease, border-color 0.2s ease, background 0.2s ease, transform 0.2s ease;
}

.theme-toggle:hover,
.theme-toggle:focus-visible {
  color: var(--color-primary);
  border-color: var(--color-border-strong);
  background: rgba(5, 7, 12, 0.74);
  transform: translateY(-1px);
}

.theme-toggle .el-icon {
  font-size: 18px;
}

.main-content.theme-dot .studio {
  background: transparent;
}
</style>
