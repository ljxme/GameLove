<template>
  <div class="container mx-auto px-4 py-8 max-w-7xl">
    <HeaderBar />
    <ControlsBar />
    <StatsOverview />
    <PlatformsContainer />
    <FooterBar />
  </div>
</template>

<script setup lang="ts">
import HeaderBar from './components/HeaderBar.vue';
import ControlsBar from './components/ControlsBar.vue';
import StatsOverview from './components/StatsOverview.vue';
import PlatformsContainer from './components/PlatformsContainer.vue';
import FooterBar from './components/FooterBar.vue';
</script>

<style scoped>
/* 依赖全局 Tailwind 与 style.css；各子组件内已保留必要 ID */
</style>
