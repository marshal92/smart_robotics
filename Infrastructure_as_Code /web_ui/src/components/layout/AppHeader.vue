<template>
  <div class="header">
    <h2>Supervisory control</h2>
    <TelemetryHUD />
    <ConnectionBox />
  </div>
</template>

<script setup>
import TelemetryHUD from './TelemetryHUD.vue'
import ConnectionBox from './ConnectionBox.vue'
</script>

<style scoped>
.header { 
  display: flex; 
  justify-content: space-between; 
  align-items: center; 
  background: var(--panel-bg); 
  padding: 2px 20px; 
  border-radius: 8px; 
  margin-bottom: 10px; 
  box-shadow: 0 4px 6px rgba(0,0,0,0.3); 
}
.header h2 {
  margin: 0;
  font-size: 18px;
}
</style>
