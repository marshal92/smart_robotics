<template>
  <div class="subtab-pane">
    <!-- MoveIt Servo + Teleop Manager Lifecycle Controls -->
    <div class="arm-backend-pair">
      <button class="cmd-btn border-btn b-orange compact-btn" @click="pubSmartCommand('system', 'arm_servo_on')">
        Servo ON
      </button>
      <button class="cmd-btn border-btn b-red compact-btn" @click="pubSmartCommand('system', 'arm_servo_off')">
        Servo OFF
      </button>
    </div>

    <!-- Speed & Reference Frame Settings -->
    <div class="settings-card">
      <div class="speed-row">
        <span class="ctrl-label">SPEED: <span class="mono accent-text">{{ speedPercent }}%</span></span>
        <input type="range" min="1" max="100" v-model.number="speedPercent" class="compact-slider" />
      </div>

      <div class="frame-row">
        <span class="ctrl-label">FRAME:</span>
        <div class="segmented-control">
          <button
            class="seg-btn"
            :class="{ active: selectedFrame === 'arm_base_link' }"
            @click="selectedFrame = 'arm_base_link'"
          >
            BASE (GLOBAL)
          </button>
          <button
            class="seg-btn"
            :class="{ active: selectedFrame === 'arm_tool0' }"
            @click="selectedFrame = 'arm_tool0'"
          >
            TOOL (LOCAL)
          </button>
        </div>
      </div>
    </div>

    <!-- Cartesian IK Controls (D-Pad + Z + R/P/Y) -->
    <div class="teleop-card">
      <div class="section-title">TRANSLATION (SERVO IK)</div>

      <div class="translation-layout">
        <!-- 3x3 D-Pad for X/Y (Y+ Left, Y- Right) -->
        <div class="xy-dpad">
          <div class="dpad-slot"></div>
          <button
            class="jog-btn"
            @mousedown="startTwist(1, 0, 0, 0, 0, 0)"
            @mouseup="endTwist"
            @mouseleave="endTwist"
            @touchstart.prevent="startTwist(1, 0, 0, 0, 0, 0)"
            @touchend.prevent="endTwist"
          >
            <span class="axis-dot axis-x"></span> X+
          </button>
          <div class="dpad-slot"></div>

          <button
            class="jog-btn"
            @mousedown="startTwist(0, 1, 0, 0, 0, 0)"
            @mouseup="endTwist"
            @mouseleave="endTwist"
            @touchstart.prevent="startTwist(0, 1, 0, 0, 0, 0)"
            @touchend.prevent="endTwist"
          >
            <span class="axis-dot axis-y"></span> Y+
          </button>
          <div class="dpad-center">
            <span class="crosshair-icon">┼</span>
          </div>
          <button
            class="jog-btn"
            @mousedown="startTwist(0, -1, 0, 0, 0, 0)"
            @mouseup="endTwist"
            @mouseleave="endTwist"
            @touchstart.prevent="startTwist(0, -1, 0, 0, 0, 0)"
            @touchend.prevent="endTwist"
          >
            <span class="axis-dot axis-y"></span> Y-
          </button>

          <div class="dpad-slot"></div>
          <button
            class="jog-btn"
            @mousedown="startTwist(-1, 0, 0, 0, 0, 0)"
            @mouseup="endTwist"
            @mouseleave="endTwist"
            @touchstart.prevent="startTwist(-1, 0, 0, 0, 0, 0)"
            @touchend.prevent="endTwist"
          >
            <span class="axis-dot axis-x"></span> X-
          </button>
          <div class="dpad-slot"></div>
        </div>

        <!-- 1x3 Column for Z Axis -->
        <div class="z-column">
          <button
            class="jog-btn"
            @mousedown="startTwist(0, 0, 1, 0, 0, 0)"
            @mouseup="endTwist"
            @mouseleave="endTwist"
            @touchstart.prevent="startTwist(0, 0, 1, 0, 0, 0)"
            @touchend.prevent="endTwist"
          >
            <span class="axis-dot axis-z"></span> Z+
          </button>
          <div class="z-center">
            <span>Z AXIS</span>
          </div>
          <button
            class="jog-btn"
            @mousedown="startTwist(0, 0, -1, 0, 0, 0)"
            @mouseup="endTwist"
            @mouseleave="endTwist"
            @touchstart.prevent="startTwist(0, 0, -1, 0, 0, 0)"
            @touchend.prevent="endTwist"
          >
            <span class="axis-dot axis-z"></span> Z-
          </button>
        </div>
      </div>

      <!-- Rotation Controls: Pitch / Roll / Yaw -->
      <div class="section-title" style="margin-top: 14px;">ROTATION (PITCH / ROLL / YAW)</div>
      <div class="rotation-grid">
        <button
          v-for="rot in rotationButtons"
          :key="rot.label"
          class="jog-btn"
          @mousedown="startTwist(0, 0, 0, rot.ax, rot.ay, rot.az)"
          @mouseup="endTwist"
          @mouseleave="endTwist"
          @touchstart.prevent="startTwist(0, 0, 0, rot.ax, rot.ay, rot.az)"
          @touchend.prevent="endTwist"
        >
          <span class="axis-dot" :class="rot.dotClass"></span> {{ rot.label }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { useArmRos } from './useArmRos'

const emit = defineEmits(['stop-other-motion'])

const {
  pubSmartCommand,
  hubExecuting,
  sendTwist,
  resetHubTask,
  registerStopCallback
} = useArmRos()

const speedPercent = ref(50)
const selectedFrame = ref('arm_base_link')

const rotationButtons = [
  { label: 'PITCH (Y) +', ax: 0, ay: 1, az: 0, dotClass: 'axis-y' },
  { label: 'ROLL (X) +', ax: 1, ay: 0, az: 0, dotClass: 'axis-x' },
  { label: 'YAW (Z) +', ax: 0, ay: 0, az: 1, dotClass: 'axis-z' },
  { label: 'PITCH (Y) -', ax: 0, ay: -1, az: 0, dotClass: 'axis-y' },
  { label: 'ROLL (X) -', ax: -1, ay: 0, az: 0, dotClass: 'axis-x' },
  { label: 'YAW (Z) -', ax: 0, ay: 0, az: -1, dotClass: 'axis-z' }
]

let activeJogInterval = null
let stopJogTimer = null
let isJogging = false
let unregisterStop = null

const publishScaledTwist = (lx, ly, lz, ax, ay, az) => {
  const s = speedPercent.value / 100.0
  sendTwist(selectedFrame.value, lx * s, ly * s, lz * s, ax * s, ay * s, az * s)
}

const endTwist = () => {
  if (!isJogging && !activeJogInterval) return
  isJogging = false
  if (activeJogInterval) {
    clearInterval(activeJogInterval)
    activeJogInterval = null
  }
  if (stopJogTimer) {
    clearTimeout(stopJogTimer)
    stopJogTimer = null
  }

  sendTwist(selectedFrame.value, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
  // Send zero twice to guarantee immediate halt across bridge
  stopJogTimer = setTimeout(() => {
    stopJogTimer = null
    if (!isJogging) {
      sendTwist(selectedFrame.value, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    }
  }, 40)
}

const startTwist = (lx, ly, lz, ax, ay, az) => {
  if (hubExecuting.value) {
    resetHubTask()
  }
  emit('stop-other-motion')
  isJogging = true
  if (stopJogTimer) {
    clearTimeout(stopJogTimer)
    stopJogTimer = null
  }
  if (activeJogInterval) clearInterval(activeJogInterval)

  publishScaledTwist(lx, ly, lz, ax, ay, az)
  activeJogInterval = setInterval(() => {
    if (isJogging) {
      publishScaledTwist(lx, ly, lz, ax, ay, az)
    }
  }, 100)
}

onMounted(() => {
  unregisterStop = registerStopCallback(endTwist)
  window.addEventListener('mouseup', endTwist)
  window.addEventListener('touchend', endTwist)
  window.addEventListener('touchcancel', endTwist)
  window.addEventListener('blur', endTwist)
})

onBeforeUnmount(() => {
  window.removeEventListener('mouseup', endTwist)
  window.removeEventListener('touchend', endTwist)
  window.removeEventListener('touchcancel', endTwist)
  window.removeEventListener('blur', endTwist)
  unregisterStop?.()
  endTwist()
})

defineExpose({
  endTwist
})
</script>

<style scoped>
.frame-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.segmented-control {
  display: flex;
  flex: 1;
  gap: 4px;
  background: var(--bg-item);
  padding: 2px;
  border-radius: 3px;
  border: 1px solid var(--border);
}

.seg-btn {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--muted);
  padding: 4px 6px;
  font-size: 10px;
  font-weight: 700;
  border-radius: 2px;
  cursor: pointer;
  transition: all 0.15s;
}

.seg-btn.active {
  background: var(--border-focus);
  color: #ffffff;
}

.rotation-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  grid-template-rows: repeat(2, 38px);
  gap: 6px;
}
</style>
