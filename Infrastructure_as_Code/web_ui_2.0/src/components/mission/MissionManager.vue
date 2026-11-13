<template>
  <div class="mission-block">
    <WaypointCreator activeMissionTab="global" />
  </div>
</template>

<script setup>
import WaypointCreator from './WaypointCreator.vue'
</script>

<style scoped>
.mission-block {
  padding: 8px 12px;
  background: var(--bg-panel);
  height: 100%;
  box-sizing: border-box;
  overflow-y: auto;
}
</style>
