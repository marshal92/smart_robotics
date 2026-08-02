<template>
  <div class="speed-control">
    <label><span class="speed-val">{{ speed }}</span><br/><span class="speed-unit">m/s</span></label>
    <div class="slider-wrapper">
      <input type="range" orient="vertical" min="0.1" max="2.0" step="0.1" v-model="speed" @input="updateSpeed" />
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { setTeleopSpeed } from '../../services/teleopCore'

const speed = ref(0.5)

const updateSpeed = () => {
  setTeleopSpeed(speed.value)
}

// Initial set
updateSpeed()
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
  font-size: 11px; 
  color: #aaa; 
  margin-bottom: 10px; 
  line-height: 1.2; 
}
.speed-val {
  color: white; 
  font-weight: bold;
  font-size: 14px;
}
.speed-unit {
  font-size: 10px;
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
