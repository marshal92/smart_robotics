<template>
  <div class="hud-mono mono">
    <span>FSM: <b :style="{ color: fsmColor }">{{ store.telemetry.fsm_state }}</b></span>
    <span class="sep">|</span>
    <span>VEL: <b>{{ displaySpeed }} m/s</b></span>
    <span class="sep">|</span>
    <span>RAD: <b>{{ displayDose }} µSv/h</b></span>
    <span class="sep">|</span>
    <span>NAV: <b>{{ store.telemetry.nav_status }}</b></span>
    <span class="sep">|</span>
    <span class="light-indicator">LIGHT <b class="light-icon" :class="{ 'is-on': store.lightOn }">💡</b></span>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRosStore } from '../../stores/rosStore'

const store = useRosStore()

const displaySpeed = computed(() => {
  const v = Number(store.telemetry.linear_speed) || 0
  if (Math.abs(v) < 0.005) return '0.00'
  return v.toFixed(2)
})

const displayDose = computed(() => {
  const d = Number(store.telemetry.dose_rate) || 0
  if (Math.abs(d) < 0.005) return '0.0'
  return d.toFixed(1)
})

const fsmColor = computed(() => {
  const state = store.telemetry.fsm_state
  if (state === 'NORMAL') return 'var(--green)'
  if (state === 'WARNING') return 'var(--orange)'
  if (state === 'EVACUATING') return 'var(--red)'
  if (state === 'SAFE_HOLD') return '#3b82f6'
  if (state === 'DISABLED') return 'var(--muted)'
  return 'var(--accent)'
})
</script>

<style scoped>
.hud-mono {
  display: flex;
  align-items: center;
  gap: 10px;
  font-family: 'JetBrains Mono', monospace;
  font-variant-numeric: tabular-nums;
  font-size: 11px;
  color: var(--text);
  white-space: nowrap;
  user-select: none;
}

.hud-mono b {
  font-weight: 700;
}

.sep {
  color: var(--border);
  font-weight: normal;
  opacity: 0.8;
}

.light-indicator {
  display: flex;
  align-items: center;
  gap: 3px;
}

.light-icon {
  font-size: 13px;
  filter: grayscale(100%) opacity(0.35);
  transition: all 0.2s ease;
  line-height: 1;
}

.light-icon.is-on {
  filter: grayscale(0%) brightness(1.3);
}

@media (max-width: 900px) {
  .hud-mono {
    gap: 6px;
    font-size: 10px;
  }
}
</style>
