<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import TopNav from './components/TopNav.vue'
import ThreeDWindowManager from './components/ThreeDWindowManager.vue'

const PrismBackground = defineAsyncComponent(() => import('./components/PrismBackground.vue'))
const LightRaysBackground = defineAsyncComponent(() => import('./components/LightRaysBackground.vue'))
const DotFieldBackground = defineAsyncComponent(() => import('./components/DotFieldBackground.vue'))

const route = useRoute()
const isLoginPage = computed(() => route.path === '/login')
const keepPrismBackground = computed(() => route.path === '/' || route.path.startsWith('/projects'))
const isGenerationPage = computed(() => route.path === '/image' || route.path === '/video' || route.path === '/create')
const businessTheme = ref(localStorage.getItem('business-theme') === 'dot' ? 'dot' : 'light')
const isDotTheme = computed(() => businessTheme.value === 'dot')
const showLoginReveal = ref(false)
const revealingHome = ref(false)
let revealTimer: ReturnType<typeof setTimeout> | undefined

watch(() => route.path, async (path) => {
  if (path !== '/' || sessionStorage.getItem('login-reveal-home') !== '1') return
  sessionStorage.removeItem('login-reveal-home')
  showLoginReveal.value = true
  revealingHome.value = false
  await nextTick()
  requestAnimationFrame(() => requestAnimationFrame(() => { revealingHome.value = true }))
  revealTimer = setTimeout(() => {
    showLoginReveal.value = false
    revealingHome.value = false
  }, 850)
})

onBeforeUnmount(() => clearTimeout(revealTimer))

</script>

<template>
  <PrismBackground
    v-if="keepPrismBackground"
    class="workbench-background"
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
      v-if="isDotTheme && !isGenerationPage"
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
  </template>

  <TopNav v-if="!isLoginPage" />
  <div class="main-content" :class="{ 'theme-dot': isDotTheme && !keepPrismBackground, 'login-content': isLoginPage }">
    <RouterView v-slot="{ Component, route }">
      <KeepAlive :include="['TextToImage', 'TextToVideo']">
        <component :is="Component" :key="route.name" />
      </KeepAlive>
    </RouterView>
  </div>
  <div v-if="showLoginReveal" class="login-reveal" :class="{ revealing: revealingHome }" aria-hidden="true" />
  <ThreeDWindowManager v-if="!isLoginPage" />
</template>

<style>
.main-content {
  position: relative;
  z-index: 1;
  margin-left: 0;
  padding-top: 22px;
  min-height: 100vh;
}

.main-content.theme-dot .studio { background: transparent; }
.main-content.login-content { padding-top: 0; }
.main-content > .page,
.main-content > .workbench,
.main-content > .developer-panel,
.main-content > .studio { min-height: calc(100vh - 22px); }

@media (max-width: 760px) {
  .main-content { padding-top: 56px; }
  .main-content > .page,
  .main-content > .workbench,
  .main-content > .developer-panel,
  .main-content > .studio { min-height: calc(100vh - 56px); }
}

.workbench-background {
  filter: blur(24px) brightness(0.5) saturate(0.72);
  transform: scale(1.08);
  transform-origin: center;
}

.login-reveal {
  position: fixed;
  inset: 0;
  z-index: 2000;
  background: #000;
  opacity: 1;
  pointer-events: none;
  transition: opacity 0.8s ease;
}
.login-reveal.revealing { opacity: 0; }
</style>
