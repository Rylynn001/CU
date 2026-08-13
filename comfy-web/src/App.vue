<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import SideNav from './components/SideNav.vue'
import PrismBackground from './components/PrismBackground.vue'
import LightRaysBackground from './components/LightRaysBackground.vue'
import DotFieldBackground from './components/DotFieldBackground.vue'

const route = useRoute()
const keepPrismBackground = computed(() => route.path === '/login' || route.path === '/')
const hideSideNav = computed(() => route.path === '/node-panel')
type BusinessTheme = 'light' | 'dot' | 'black'

const savedTheme = localStorage.getItem('business-theme')
const businessTheme = ref<BusinessTheme>(
  savedTheme === 'dot' || savedTheme === 'black' ? savedTheme : 'light',
)
const isDotTheme = computed(() => businessTheme.value === 'dot')
const isBlackTheme = computed(() => businessTheme.value === 'black')

function toggleBusinessTheme() {
  const themes: BusinessTheme[] = ['light', 'dot', 'black']
  const currentIndex = themes.indexOf(businessTheme.value)
  businessTheme.value = themes[(currentIndex + 1) % themes.length]
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
      gradient-to="rgba(255,255,255,0.82)"
      glow-color="#000000"
    />
    <LightRaysBackground
      v-else-if="!isBlackTheme"
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
    <div v-else class="black-background" aria-hidden="true" />
  </template>
  <SideNav
    v-if="!hideSideNav"
    :business-theme="businessTheme"
    :show-theme-toggle="!keepPrismBackground"
    @toggle-theme="toggleBusinessTheme"
  />
  <div
    class="main-content"
    :class="{
      'theme-dot': isDotTheme && !keepPrismBackground,
      'theme-black': isBlackTheme && !keepPrismBackground,
      'no-sidenav': hideSideNav,
    }"
  >
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

.main-content.no-sidenav {
  margin-left: 0;
}

.black-background {
  position: fixed;
  inset: 0;
  z-index: 0;
  background: #000000;
}

.main-content.theme-dot .studio {
  background: transparent;
}

.main-content.theme-black .studio,
.main-content.theme-black .page {
  background: #000000;
}

.main-content.theme-black .orb {
  display: none;
}
</style>
