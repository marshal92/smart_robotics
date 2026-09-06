<template>
  <div class="block-container mission-block">
    <h3 class="block-title mission-title">Block 2: Navigation & Waypoints</h3>
    
    <WaypointCreator activeMissionTab="global" />
  </div>
</template>

<script setup>
import WaypointCreator from './WaypointCreator.vue'
</script>

<style scoped>
.mission-block {
  margin-top: 10px;
  margin-bottom: 10px;
  padding: 10px 15px;
}
.mission-title {
  border-bottom: none;
  margin-bottom: 5px;
}
</style>
