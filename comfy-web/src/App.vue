<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import SideNav from './components/SideNav.vue'
import PrismBackground from './components/PrismBackground.vue'
import LightRaysBackground from './components/LightRaysBackground.vue'

const route = useRoute()
const keepPrismBackground = computed(() => route.path === '/login' || route.path === '/')
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
  <SideNav />
  <div class="main-content">
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
</style>
