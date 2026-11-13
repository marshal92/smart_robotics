<template>
  <div class="d-pad-container" :class="{ 'shadow-pad': isShadow }">
    <!-- Clean simple unicode triangles instead of emojis -->
    <div class="d-pad-row">
      <button class="d-pad-btn" :class="{ 'active-pad': moveState.up }" 
              @mousedown="padDown(1, 0)" @mouseup="padUp" @mouseleave="handleMouseLeave"
              @touchstart.prevent="padDown(1, 0)" @touchend.prevent="padUp" @touchcancel.prevent="padUp">&#9650;</button>
    </div>
    <div class="d-pad-row">
      <button class="d-pad-btn" :class="{ 'active-pad': moveState.left }" 
              @mousedown="padDown(0, 1)" @mouseup="padUp" @mouseleave="handleMouseLeave"
              @touchstart.prevent="padDown(0, 1)" @touchend.prevent="padUp" @touchcancel.prevent="padUp">&#9664;</button>
      <button class="d-pad-btn" :class="{ 'active-pad': moveState.down }" 
              @mousedown="padDown(-1, 0)" @mouseup="padUp" @mouseleave="handleMouseLeave"
              @touchstart.prevent="padDown(-1, 0)" @touchend.prevent="padUp" @touchcancel.prevent="padUp">&#9660;</button>
      <button class="d-pad-btn" :class="{ 'active-pad': moveState.right }" 
              @mousedown="padDown(0, -1)" @mouseup="padUp" @mouseleave="handleMouseLeave"
              @touchstart.prevent="padDown(0, -1)" @touchend.prevent="padUp" @touchcancel.prevent="padUp">&#9654;</button>
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
let isPointerActive = false

const padDown = (x, z) => {
  isPointerActive = true
  store.setActiveRobotType(props.isShadow ? 'shadow' : 'base')
  moveState.up = x > 0
  moveState.down = x < 0
  moveState.left = z > 0
  moveState.right = z < 0
  startTeleopLoop()
}

const padUp = () => {
  if (!isPointerActive && !moveState.up && !moveState.down && !moveState.left && !moveState.right) {
    return
  }
  isPointerActive = false
  moveState.up = false
  moveState.down = false
  moveState.left = false
  moveState.right = false
  stopTeleopLoop()
}

const handleMouseLeave = () => {
  if (isPointerActive) {
    padUp()
  }
}

const handleGlobalPointerUp = () => {
  if (isPointerActive) {
    padUp()
  }
}

const handleWindowBlur = () => {
  if (isPointerActive || moveState.up || moveState.down || moveState.left || moveState.right) {
    padUp()
  }
}

const isEditableTarget = (target) => {
  if (!target) return false
  const tag = target.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target.isContentEditable
}

const handleKeyDown = (e) => {
  if (isEditableTarget(e.target) || e.repeat) return
  
  if (!store.activeRobotType) {
    store.setActiveRobotType('base')
  }

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
  if (isEditableTarget(e.target)) return
  
  if (!store.activeRobotType) {
    store.setActiveRobotType('base')
  }

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
  window.addEventListener('mouseup', handleGlobalPointerUp)
  window.addEventListener('touchend', handleGlobalPointerUp)
  window.addEventListener('touchcancel', handleGlobalPointerUp)
  window.addEventListener('blur', handleWindowBlur)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeyDown)
  window.removeEventListener('keyup', handleKeyUp)
  window.removeEventListener('mouseup', handleGlobalPointerUp)
  window.removeEventListener('touchend', handleGlobalPointerUp)
  window.removeEventListener('touchcancel', handleGlobalPointerUp)
  window.removeEventListener('blur', handleWindowBlur)
  if (isPointerActive) {
    padUp()
  }
})
</script>

<style scoped>
.d-pad-container { display: flex; flex-direction: column; align-items: center; gap: 6px; box-sizing: border-box;}
.d-pad-row { display: flex; gap: 6px; justify-content: center; }
.d-pad-btn { 
  width: 44px; 
  height: 44px; 
  background: var(--bg-item); 
  color: var(--text); 
  border: 1px solid var(--border); 
  border-radius: 4px; 
  font-size: 16px; 
  font-weight: 700; 
  cursor: pointer; 
  user-select: none; 
  box-shadow: none; 
  transition: background 0.1s, border-color 0.1s, transform 0.05s; 
  display: flex; 
  align-items: center; 
  justify-content: center;
}
.d-pad-btn:hover {
  background: var(--bg-item-hover);
  border-color: var(--border-focus);
}
.d-pad-btn:active, .d-pad-btn.active-pad { 
  transform: translateY(1px); 
  box-shadow: none; 
  background: var(--accent); 
  color: #ffffff;
  border-color: var(--accent);
}
.shadow-pad .d-pad-btn:active, .shadow-pad .d-pad-btn.active-pad { 
  background: var(--purple); 
  color: #ffffff;
  border-color: var(--purple);
}
</style>
