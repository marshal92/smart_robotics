<template>
  <div class="speed-control">
    <label><span class="speed-val">{{ speed.toFixed(1) }}</span><br/><span class="speed-unit">m/s</span></label>
    <div class="slider-wrapper">
      <input type="range" orient="vertical" min="0.1" max="2.0" step="0.1" v-model.number="speed" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { teleopSpeed, setTeleopSpeed } from '../../services/teleopCore'

const speed = computed({
  get: () => teleopSpeed.value,
  set: (val) => setTeleopSpeed(val)
})
</script>

<style scoped>
.speed-control { 
  text-align: center; 
  display: flex; 
  flex-direction: column; 
  align-items: center; 
  justify-content: center; 
  width: 60px; 
  box-sizing: border-box; 
  height: 160px; 
}
.speed-control label { 
  font-size: 10px; 
  font-weight: 700;
  color: var(--muted); 
  text-transform: uppercase;
  margin-bottom: 8px; 
  line-height: 1.2; 
}
.speed-val {
  color: var(--text); 
  font-weight: 700;
  font-size: 13px;
  font-family: 'JetBrains Mono', monospace;
  font-variant-numeric: tabular-nums;
}
.speed-unit {
  font-size: 9px;
  color: var(--muted);
}
.slider-wrapper {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.speed-control input[type=range] { 
  -webkit-appearance: slider-vertical;
  width: 8px; 
  height: 90px; 
  cursor: pointer; 
}
</style>
