<template>
  <div
    class="touch-joystick"
    @pointerdown.stop
    @touchstart.stop
  >
    <div class="tj-header">
      <span :class="['tj-target', { 'is-shadow': isShadow }]">
        {{ isShadow ? 'SHADOW' : 'BASE' }}
      </span>
      <div class="tj-speed-stepper">
        <button
          type="button"
          class="tj-step-btn"
          @click="adjustSpeed(-0.1)"
          title="Decrease teleop speed"
          aria-label="Decrease teleop speed"
        >-</button>
        <span class="tj-speed-val">{{ teleopSpeed.toFixed(1) }} m/s</span>
        <button
          type="button"
          class="tj-step-btn"
          @click="adjustSpeed(0.1)"
          title="Increase teleop speed"
          aria-label="Increase teleop speed"
        >+</button>
      </div>
    </div>

    <div
      ref="padRef"
      class="tj-pad"
      :class="{ 'is-dragging': isDragging }"
      @pointerdown="onPointerDown"
      @lostpointercapture="releaseStick"
      @contextmenu.prevent
    >
      <div class="tj-axis tj-axis-h"></div>
      <div class="tj-axis tj-axis-v"></div>
      <div class="tj-deadzone"></div>
      <div class="tj-knob" :style="knobStyle">
        <div class="tj-knob-core"></div>
      </div>
    </div>

    <div class="tj-readout">
      <span>V: {{ formatSigned(liveLinear) }}</span>
      <span>W: {{ formatSigned(liveAngular) }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  teleopSpeed,
  setTeleopSpeed,
  setAnalogTeleop,
  clearAnalogTeleop
} from '../../services/teleopCore'
import { useRosStore } from '../../stores/rosStore'

const DEADZONE = 0.10
const KNOB_RADIUS_PX = 22

const store = useRosStore()
const padRef = ref(null)
const isDragging = ref(false)
const knobOffsetX = ref(0)
const knobOffsetY = ref(0)
const normLinear = ref(0)
const normAngular = ref(0)

let activePointerId = null

const isShadow = computed(() => store.activeRobotType === 'shadow')
const liveLinear = computed(() => normLinear.value * teleopSpeed.value)
const liveAngular = computed(() => normAngular.value * teleopSpeed.value)

const knobStyle = computed(() => ({
  transform: `translate(calc(-50% + ${knobOffsetX.value.toFixed(1)}px), calc(-50% + ${knobOffsetY.value.toFixed(1)}px))`
}))

function formatSigned(val) {
  const num = Number(val) || 0
  if (Math.abs(num) < 0.005) return ' 0.00'
  return `${num > 0 ? '+' : ''}${num.toFixed(2)}`
}

function adjustSpeed(delta) {
  setTeleopSpeed(teleopSpeed.value + delta)
}

function updateFromClientPos(clientX, clientY) {
  const el = padRef.value
  if (!el) return

  const rect = el.getBoundingClientRect()
  const maxTravel = Math.max(20, rect.width / 2 - KNOB_RADIUS_PX)
  const centerX = rect.left + rect.width / 2
  const centerY = rect.top + rect.height / 2

  const dx = clientX - centerX
  const dy = clientY - centerY
  const dist = Math.hypot(dx, dy)
  const clampedDist = Math.min(dist, maxTravel)
  const scale = dist > 1e-6 ? clampedDist / dist : 0

  // Screen right -> +X, Screen up -> +Y
  knobOffsetX.value = dx * scale
  knobOffsetY.value = dy * scale

  const rawMag = clampedDist / maxTravel
  if (rawMag <= DEADZONE) {
    normLinear.value = 0
    normAngular.value = 0
    setAnalogTeleop(0, 0)
    return
  }

  const rx = (dx * scale) / maxTravel
  const ry = -(dy * scale) / maxTravel
  const effectiveMag = (rawMag - DEADZONE) / (1 - DEADZONE)
  const ux = rx / rawMag
  const uy = ry / rawMag

  const lin = uy * effectiveMag
  const ang = -ux * effectiveMag // Right stick turns clockwise (-angular.z in ROS)

  normLinear.value = lin
  normAngular.value = ang
  setAnalogTeleop(lin, ang)
}

function releaseStick() {
  activePointerId = null
  isDragging.value = false
  knobOffsetX.value = 0
  knobOffsetY.value = 0
  normLinear.value = 0
  normAngular.value = 0
  clearAnalogTeleop()
}

function onPointerDown(e) {
  if (e.pointerType === 'mouse' && e.button !== 0) return
  if (activePointerId !== null) return

  e.preventDefault()
  e.stopPropagation()

  activePointerId = e.pointerId
  isDragging.value = true
  try {
    padRef.value?.setPointerCapture?.(e.pointerId)
  } catch {
    // Ignore environments where pointer capture is unavailable
  }
  updateFromClientPos(e.clientX, e.clientY)
}

function onWindowPointerMove(e) {
  if (e.pointerId !== activePointerId) return
  e.preventDefault()
  updateFromClientPos(e.clientX, e.clientY)
}

function onWindowPointerEnd(e) {
  if (e.pointerId !== activePointerId) return
  try {
    if (padRef.value?.hasPointerCapture?.(e.pointerId)) {
      padRef.value.releasePointerCapture(e.pointerId)
    }
  } catch {
    // Ignore release error
  }
  releaseStick()
}

function onVisibilityChange() {
  if (document.hidden && activePointerId !== null) {
    releaseStick()
  }
}

onMounted(() => {
  window.addEventListener('pointermove', onWindowPointerMove, { passive: false })
  window.addEventListener('pointerup', onWindowPointerEnd)
  window.addEventListener('pointercancel', onWindowPointerEnd)
  window.addEventListener('blur', releaseStick)
  document.addEventListener('visibilitychange', onVisibilityChange)
})

onBeforeUnmount(() => {
  window.removeEventListener('pointermove', onWindowPointerMove)
  window.removeEventListener('pointerup', onWindowPointerEnd)
  window.removeEventListener('pointercancel', onWindowPointerEnd)
  window.removeEventListener('blur', releaseStick)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  releaseStick()
})
</script>

<style scoped>
.touch-joystick {
  background: var(--dt-panel-bg, rgba(16, 20, 29, 0.86));
  backdrop-filter: blur(8px);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 7px;
  user-select: none;
  -webkit-user-select: none;
  touch-action: none;
}

.tj-header {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.tj-target {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.6px;
  padding: 2px 5px;
  border-radius: 3px;
  background: var(--bg-item);
  border: 1px solid var(--border);
  color: var(--text-dim);
}

.tj-target.is-shadow {
  color: var(--accent);
  border-color: var(--accent);
}

.tj-speed-stepper {
  display: flex;
  align-items: center;
  gap: 4px;
}

.tj-step-btn {
  width: 20px;
  height: 20px;
  padding: 0;
  border-radius: 3px;
  border: 1px solid var(--border);
  background: var(--bg-item);
  color: var(--text);
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.tj-step-btn:active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.tj-speed-val {
  font-family: 'JetBrains Mono', monospace;
  font-variant-numeric: tabular-nums;
  font-size: 10px;
  color: var(--text-dim);
  min-width: 44px;
  text-align: center;
}

.tj-pad {
  position: relative;
  width: 124px;
  height: 124px;
  border-radius: 50%;
  background: radial-gradient(circle at center, rgba(59, 130, 246, 0.12) 0%, rgba(10, 14, 22, 0.72) 72%);
  border: 1.5px solid var(--border-focus);
  box-shadow: inset 0 0 18px rgba(0, 0, 0, 0.45);
  touch-action: none;
  cursor: grab;
  overflow: hidden;
}

.tj-pad.is-dragging {
  cursor: grabbing;
  border-color: var(--accent);
  box-shadow: inset 0 0 18px rgba(59, 130, 246, 0.25), 0 0 12px rgba(59, 130, 246, 0.25);
}

.tj-axis {
  position: absolute;
  background: rgba(148, 163, 184, 0.2);
  pointer-events: none;
}

.tj-axis-h {
  left: 10%;
  right: 10%;
  top: 50%;
  height: 1px;
}

.tj-axis-v {
  top: 10%;
  bottom: 10%;
  left: 50%;
  width: 1px;
}

.tj-deadzone {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 24px;
  height: 24px;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  border: 1px dashed rgba(148, 163, 184, 0.35);
  pointer-events: none;
}

.tj-knob {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: radial-gradient(circle at 35% 35%, rgba(96, 165, 250, 0.92), rgba(37, 99, 235, 0.78));
  border: 2px solid rgba(255, 255, 255, 0.45);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.45);
  pointer-events: none;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: transform 0.04s linear;
}

.tj-pad:not(.is-dragging) .tj-knob {
  transition: transform 0.14s cubic-bezier(0.22, 1, 0.36, 1);
}

.tj-knob-core {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.85);
}

.tj-readout {
  width: 100%;
  display: flex;
  justify-content: space-between;
  font-family: 'JetBrains Mono', monospace;
  font-variant-numeric: tabular-nums;
  font-size: 10px;
  color: var(--green);
}

@media (max-width: 768px) {
  .tj-pad {
    width: 132px;
    height: 132px;
  }
}
</style>
