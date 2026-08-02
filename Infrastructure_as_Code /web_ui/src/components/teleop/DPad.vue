<template>
  <div class="d-pad-container" :class="{ 'shadow-pad': isShadow }">
    <!-- Clean simple unicode triangles instead of emojis -->
    <div class="d-pad-row">
      <button class="d-pad-btn" :class="{ 'active-pad': moveState.up }" 
              @mousedown="padDown(1, 0)" @mouseup="padUp" 
              @touchstart.prevent="padDown(1, 0)" @touchend.prevent="padUp">&#9650;</button>
    </div>
    <div class="d-pad-row">
      <button class="d-pad-btn" :class="{ 'active-pad': moveState.left }" 
              @mousedown="padDown(0, 1)" @mouseup="padUp" 
              @touchstart.prevent="padDown(0, 1)" @touchend.prevent="padUp">&#9664;</button>
      <button class="d-pad-btn" :class="{ 'active-pad': moveState.down }" 
              @mousedown="padDown(-1, 0)" @mouseup="padUp" 
              @touchstart.prevent="padDown(-1, 0)" @touchend.prevent="padUp">&#9660;</button>
      <button class="d-pad-btn" :class="{ 'active-pad': moveState.right }" 
              @mousedown="padDown(0, -1)" @mouseup="padUp" 
              @touchstart.prevent="padDown(0, -1)" @touchend.prevent="padUp">&#9654;</button>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted } from 'vue'
import { moveState, startTeleopLoop, stopTeleopLoop } from '../../services/teleopCore'
import { useRosStore } from '../../stores/rosStore'

const props = defineProps({
  isShadow: {
    type: Boolean,
    default: false
  }
})

const store = useRosStore()

const padDown = (x, z) => {
  store.setActiveRobotType(props.isShadow ? 'shadow' : 'base')
  moveState.up = x > 0
  moveState.down = x < 0
  moveState.left = z > 0
  moveState.right = z < 0
  startTeleopLoop()
}

const padUp = () => {
  moveState.up = false
  moveState.down = false
  moveState.left = false
  moveState.right = false
  stopTeleopLoop()
}

const handleKeyDown = (e) => {
  if (e.target.tagName === 'INPUT' || e.repeat) return
  if (store.activeRobotType !== (props.isShadow ? 'shadow' : 'base')) return

  const key = e.key.toLowerCase()
  let changed = false

  if (key === 'w' || key === 'arrowup') { moveState.up = true; changed = true }
  if (key === 's' || key === 'arrowdown') { moveState.down = true; changed = true }
  if (key === 'a' || key === 'arrowleft') { moveState.left = true; changed = true }
  if (key === 'd' || key === 'arrowright') { moveState.right = true; changed = true }

  if (changed) {
    e.preventDefault()
    startTeleopLoop()
  }
}

const handleKeyUp = (e) => {
  if (e.target.tagName === 'INPUT') return
  if (store.activeRobotType !== (props.isShadow ? 'shadow' : 'base')) return

  const key = e.key.toLowerCase()
  let changed = false

  if (key === 'w' || key === 'arrowup') { moveState.up = false; changed = true }
  if (key === 's' || key === 'arrowdown') { moveState.down = false; changed = true }
  if (key === 'a' || key === 'arrowleft') { moveState.left = false; changed = true }
  if (key === 'd' || key === 'arrowright') { moveState.right = false; changed = true }

  if (changed) {
    if (!moveState.up && !moveState.down && !moveState.left && !moveState.right) {
      stopTeleopLoop()
    }
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeyDown)
  window.addEventListener('keyup', handleKeyUp)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown)
  window.removeEventListener('keyup', handleKeyUp)
})
</script>

<style scoped>
.d-pad-container { display: flex; flex-direction: column; align-items: center; gap: 8px; box-sizing: border-box;}
.d-pad-row { display: flex; gap: 8px; justify-content: center; }
.d-pad-btn { width: 50px; height: 50px; background: #444; color: white; border: none; border-radius: 8px; font-size: 18px; font-weight: bold; cursor: pointer; user-select: none; box-shadow: 0 4px 0 #222, 0 6px 8px rgba(0,0,0,0.5); transition: 0.1s; display: flex; align-items: center; justify-content: center;}
.d-pad-btn:active, .d-pad-btn.active-pad { transform: translateY(3px); box-shadow: 0 1px 0 #222, 0 2px 4px rgba(0,0,0,0.5); background: var(--accent); }
.shadow-pad .d-pad-btn:active, .shadow-pad .d-pad-btn.active-pad { background: #7b1fa2; }
</style>
