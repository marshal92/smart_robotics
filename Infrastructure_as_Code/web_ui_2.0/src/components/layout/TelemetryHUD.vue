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
    <template v-if="store.gamepadConnected">
      <span class="sep">|</span>
      <button
        type="button"
        class="gp-hud-pill"
        :class="`mode-${store.gamepadMode}`"
        @click="cycleGamepadMode"
        :title="`${store.gamepadName || 'Xbox Controller'} — Click to switch DRIVE / ARM`"
      >
        {{ gpLabel }}
      </button>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRosStore } from '../../stores/rosStore'

const store = useRosStore()

const gpLabel = computed(() => {
  if (store.gamepadMode === 'arm') return 'PAD:ARM'
  if (store.gamepadMode === 'off') return 'PAD:OFF'
  return store.driveTarget === 'shadow' ? 'PAD:SHD' : 'PAD:DRV'
})

const cycleGamepadMode = () => {
  const next = store.gamepadMode === 'drive' ? 'arm' : 'drive'
  store.setGamepadMode(next)
}

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

.gp-hud-pill {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9.5px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 3px;
  border: 1px solid var(--border);
  background: var(--bg-item);
  color: var(--text);
  cursor: pointer;
  line-height: 1.3;
}

.gp-hud-pill.mode-drive {
  border-color: var(--green);
  color: var(--green);
}

.gp-hud-pill.mode-arm {
  border-color: var(--accent);
  color: var(--accent);
}

.gp-hud-pill.mode-off {
  color: var(--muted);
  opacity: 0.75;
}

@media (max-width: 900px) {
  .hud-mono {
    gap: 6px;
    font-size: 10px;
  }
}
</style>
