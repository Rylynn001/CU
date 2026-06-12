<script setup lang="ts">
import SideNav from './components/SideNav.vue'
import ParticleBackground from './components/ParticleBackground.vue'
</script>

<template>
  <ParticleBackground />
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
  margin-left: 56px;
  min-height: 100vh;
  transition: margin-left 0.25s ease;
}
</style>
