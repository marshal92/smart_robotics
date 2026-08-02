<template>
  <div class="hud-panel">
    <div class="hud-item">
      <span class="hud-label">FSM State</span>
      <span class="hud-val" :style="{ color: fsmColor }">{{ store.telemetry.fsm_state }}</span>
    </div>
    <div class="hud-item">
      <span class="hud-label">Linear Vel</span>
      <span class="hud-val">{{ store.telemetry.linear_speed.toFixed(2) }} m/s</span>
    </div>
    <div class="hud-item">
      <span class="hud-label">Radiation</span>
      <span class="hud-val" style="color: var(--orange);">{{ store.telemetry.dose_rate.toFixed(1) }} µSv/h</span>
    </div>
    <div class="hud-item">
      <span class="hud-label">Nav Status</span>
      <span class="hud-val" style="color: #aaa;">{{ store.telemetry.nav_status }}</span>
    </div>
    <div class="hud-item">
      <span class="hud-label">Light</span>
      <span class="hud-val light-icon" :class="{ 'is-on': store.lightOn }">💡</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRosStore } from '../../stores/rosStore'

const store = useRosStore()

const fsmColor = computed(() => {
  const state = store.telemetry.fsm_state
  if (state === 'NORMAL') return 'var(--green)'
  if (state === 'WARNING') return 'var(--orange)'
  if (state === 'EVACUATING') return 'var(--red)'
  if (state === 'SAFE_HOLD') return '#3b82f6'
  if (state === 'DISABLED') return '#aaaaaa'
  return 'var(--accent)'
})
</script>

<style scoped>
.hud-panel { 
  display: flex; 
  gap: 20px; 
  padding: 10px 0; /* Removed background and borders */
  align-items: center;
}
.hud-item { display: flex; flex-direction: column; align-items: center; justify-content: center; min-width: 80px;}
.hud-label { font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 1px;}
.hud-val { font-size: 18px; font-weight: bold; color: var(--accent); font-family: monospace;}

.light-icon {
  font-size: 20px;
  filter: grayscale(100%) opacity(0.3); /* Off state */
  transition: all 0.3s ease;
}
.light-icon.is-on {
  filter: grayscale(0%) brightness(1.5) drop-shadow(0 0 8px rgba(255, 255, 0, 0.8)); /* On state */
}
</style>
