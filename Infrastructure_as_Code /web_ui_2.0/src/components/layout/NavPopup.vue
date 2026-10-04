<template>
  <div class="nav-popup">
    <div class="nav-popup-grid">
      <button class="unified-btn c-red" @click="cancelNav">
        <div class="waypoint-name">CANCEL</div>
      </button>
      <button v-for="(data, name) in store.waypoints" :key="name"
              class="unified-btn" :class="data.type === 'route' ? 'c-purple' : 'c-blue'"
              @click="goTo(name)">
        <div class="waypoint-name">{{ name.toUpperCase() }}</div>
        <div class="waypoint-coords" v-if="data.x !== undefined">{{ data.x.toFixed(1) }}, {{ data.y.toFixed(1) }}, {{ data.yaw.toFixed(1) }}</div>
      </button>
    </div>
  </div>
</template>

<script setup>
import { useRosStore } from '../../stores/rosStore'
import { pubSmartCommand } from '../../services/rosConnection'

const store = useRosStore()
const emit = defineEmits(['close'])

const goTo = (name) => {
  pubSmartCommand('nav', 'go_to_named', { name })
  emit('close') // Optional: close popup after selection
}

const cancelNav = () => {
  pubSmartCommand('nav', 'cancel', { x: 0, y: 0, yaw: 0 })
  emit('close')
}
</script>

<style scoped>
.nav-popup {
  position: absolute;
  bottom: 60px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(30, 30, 30, 0.95);
  border: 1px solid #444;
  border-radius: 8px;
  padding: 10px;
  width: 90%;
  max-width: 400px;
  z-index: 50;
  box-shadow: 0 10px 25px rgba(0,0,0,0.5);
  backdrop-filter: blur(4px);
}
.nav-popup-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}
</style>
