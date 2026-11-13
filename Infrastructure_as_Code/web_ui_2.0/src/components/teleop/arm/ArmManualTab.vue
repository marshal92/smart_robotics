<template>
  <div class="subtab-pane">
    <!-- Top Parameter Bar -->
    <div class="settings-card">
      <div class="speed-row">
        <span class="ctrl-label">SPEED: <span class="mono accent-text">{{ speedPercent }}%</span></span>
        <input
          type="range"
          min="10"
          max="100"
          step="5"
          v-model.number="speedPercent"
          class="compact-slider manual-speed-slider"
        />
      </div>

      <div class="manual-toggle-row">
        <label class="autolevel-label" title="Keep gripper pitch constant during boom R/Z motion">
          <input type="checkbox" v-model="autoLevelWrist" class="autolevel-checkbox" />
          <span class="ctrl-label" style="min-width: auto;">AUTO-LEVEL WRIST (J4)</span>
        </label>
        <span class="live-badge" :class="{ active: autoLevelWrist }">
          {{ autoLevelWrist ? 'ON' : 'OFF' }}
        </span>
      </div>

      <div class="planar-readout mono">
        <span>Reach R: <b>{{ Math.round(planarState.reachMm) }} mm</b></span>
        <span class="sep">|</span>
        <span>Height Z: <b>{{ Math.round(planarState.heightMm) }} mm</b></span>
        <span class="sep">|</span>
        <span>Pitch: <b>{{ planarState.pitchElevDeg.toFixed(1) }}°</b></span>
      </div>
    </div>

    <!-- Block 1: Cylindrical Boom Control (R / Z / Base Yaw) -->
    <div class="teleop-card">
      <div class="telemetry-header">
        <span>BOOM CONTROL (CYLINDRICAL R / Z / YAW)</span>
        <span class="live-badge" :class="{ active: !limitWarning, warn: !!limitWarning }">
          {{ limitWarning || '2.5D DLS' }}
        </span>
      </div>

      <div class="translation-layout">
        <div class="xy-dpad">
          <div class="dpad-slot"></div>
          <button
            class="jog-btn manual-dpad-btn"
            :class="{ 'jog-active': activeKey === 'reach_fwd' }"
            @mousedown="startJog('reach_fwd', { kind: 'boom', dR: 1, dZ: 0 })"
            @mouseup="stopManualJog"
            @mouseleave="stopManualJog"
            @touchstart.prevent="startJog('reach_fwd', { kind: 'boom', dR: 1, dZ: 0 })"
            @touchend.prevent="stopManualJog"
            @touchcancel.prevent="stopManualJog"
          >
            <span class="btn-main"><span class="axis-dot axis-x"></span> ▲ REACH +</span>
            <span class="btn-sub">(FWD)</span>
          </button>
          <div class="dpad-slot"></div>

          <button
            class="jog-btn manual-dpad-btn"
            :class="{ 'jog-active': activeKey === 'base_l' }"
            @mousedown="startJog('base_l', { kind: 'joint', idx: 0, dir: 1 })"
            @mouseup="stopManualJog"
            @mouseleave="stopManualJog"
            @touchstart.prevent="startJog('base_l', { kind: 'joint', idx: 0, dir: 1 })"
            @touchend.prevent="stopManualJog"
            @touchcancel.prevent="stopManualJog"
          >
            <span class="btn-main">◀ BASE L</span>
          </button>

          <div class="dpad-center boom-center mono">
            <span>J0 {{ degStr(0) }}°</span>
            <span>J1 {{ degStr(1) }}°</span>
            <span>J2 {{ degStr(2) }}°</span>
          </div>

          <button
            class="jog-btn manual-dpad-btn"
            :class="{ 'jog-active': activeKey === 'base_r' }"
            @mousedown="startJog('base_r', { kind: 'joint', idx: 0, dir: -1 })"
            @mouseup="stopManualJog"
            @mouseleave="stopManualJog"
            @touchstart.prevent="startJog('base_r', { kind: 'joint', idx: 0, dir: -1 })"
            @touchend.prevent="stopManualJog"
            @touchcancel.prevent="stopManualJog"
          >
            <span class="btn-main">BASE R ▶</span>
          </button>

          <div class="dpad-slot"></div>
          <button
            class="jog-btn manual-dpad-btn"
            :class="{ 'jog-active': activeKey === 'reach_back' }"
            @mousedown="startJog('reach_back', { kind: 'boom', dR: -1, dZ: 0 })"
            @mouseup="stopManualJog"
            @mouseleave="stopManualJog"
            @touchstart.prevent="startJog('reach_back', { kind: 'boom', dR: -1, dZ: 0 })"
            @touchend.prevent="stopManualJog"
            @touchcancel.prevent="stopManualJog"
          >
            <span class="btn-main"><span class="axis-dot axis-x"></span> ▼ REACH -</span>
            <span class="btn-sub">(BACK)</span>
          </button>
          <div class="dpad-slot"></div>
        </div>

        <div class="z-column">
          <button
            class="jog-btn manual-dpad-btn"
            :class="{ 'jog-active': activeKey === 'z_up' }"
            @mousedown="startJog('z_up', { kind: 'boom', dR: 0, dZ: 1 })"
            @mouseup="stopManualJog"
            @mouseleave="stopManualJog"
            @touchstart.prevent="startJog('z_up', { kind: 'boom', dR: 0, dZ: 1 })"
            @touchend.prevent="stopManualJog"
            @touchcancel.prevent="stopManualJog"
          >
            <span class="btn-main"><span class="axis-dot axis-z"></span> ▲ UP</span>
            <span class="btn-sub">(Z+)</span>
          </button>
          <div class="z-center mono">
            <span>HEIGHT</span>
            <span>{{ Math.round(planarState.heightMm) }}</span>
          </div>
          <button
            class="jog-btn manual-dpad-btn"
            :class="{ 'jog-active': activeKey === 'z_down' }"
            @mousedown="startJog('z_down', { kind: 'boom', dR: 0, dZ: -1 })"
            @mouseup="stopManualJog"
            @mouseleave="stopManualJog"
            @touchstart.prevent="startJog('z_down', { kind: 'boom', dR: 0, dZ: -1 })"
            @touchend.prevent="stopManualJog"
            @touchcancel.prevent="stopManualJog"
          >
            <span class="btn-main"><span class="axis-dot axis-z"></span> ▼ DOWN</span>
            <span class="btn-sub">(Z-)</span>
          </button>
        </div>
      </div>
    </div>

    <!-- Block 2: Wrist & Tool Control (Pitch / Compensated Wrist Yaw / Roll) -->
    <div class="teleop-card">
      <div class="telemetry-header">
        <span>WRIST &amp; TOOL CONTROL</span>
        <span class="live-badge">J3 + J5 LEVEL</span>
      </div>

      <div class="translation-layout">
        <div class="xy-dpad">
          <div class="dpad-slot"></div>
          <button
            class="jog-btn manual-dpad-btn"
            :class="{ 'jog-active': activeKey === 'pitch_up' }"
            @mousedown="startJog('pitch_up', { kind: 'joint', idx: 4, dir: 1 })"
            @mouseup="stopManualJog"
            @mouseleave="stopManualJog"
            @touchstart.prevent="startJog('pitch_up', { kind: 'joint', idx: 4, dir: 1 })"
            @touchend.prevent="stopManualJog"
            @touchcancel.prevent="stopManualJog"
          >
            <span class="btn-main">▲ PITCH UP</span>
          </button>
          <div class="dpad-slot"></div>

          <button
            class="jog-btn manual-dpad-btn"
            :class="{ 'jog-active': activeKey === 'wrist_l' }"
            @mousedown="startJog('wrist_l', { kind: 'wrist_yaw', dir: -1 })"
            @mouseup="stopManualJog"
            @mouseleave="stopManualJog"
            @touchstart.prevent="startJog('wrist_l', { kind: 'wrist_yaw', dir: -1 })"
            @touchend.prevent="stopManualJog"
            @touchcancel.prevent="stopManualJog"
          >
            <span class="btn-main">◀ WRIST L</span>
          </button>

          <div class="dpad-center wrist-center mono">
            <span>J3 {{ degStr(3) }}°</span>
            <span>J4 {{ degStr(4) }}°</span>
            <span>J5 {{ degStr(5) }}°</span>
          </div>

          <button
            class="jog-btn manual-dpad-btn"
            :class="{ 'jog-active': activeKey === 'wrist_r' }"
            @mousedown="startJog('wrist_r', { kind: 'wrist_yaw', dir: 1 })"
            @mouseup="stopManualJog"
            @mouseleave="stopManualJog"
            @touchstart.prevent="startJog('wrist_r', { kind: 'wrist_yaw', dir: 1 })"
            @touchend.prevent="stopManualJog"
            @touchcancel.prevent="stopManualJog"
          >
            <span class="btn-main">WRIST R ▶</span>
          </button>

          <div class="dpad-slot"></div>
          <button
            class="jog-btn manual-dpad-btn"
            :class="{ 'jog-active': activeKey === 'pitch_down' }"
            @mousedown="startJog('pitch_down', { kind: 'joint', idx: 4, dir: -1 })"
            @mouseup="stopManualJog"
            @mouseleave="stopManualJog"
            @touchstart.prevent="startJog('pitch_down', { kind: 'joint', idx: 4, dir: -1 })"
            @touchend.prevent="stopManualJog"
            @touchcancel.prevent="stopManualJog"
          >
            <span class="btn-main">▼ PITCH DOWN</span>
          </button>
          <div class="dpad-slot"></div>
        </div>

        <div class="z-column">
          <button
            class="jog-btn manual-dpad-btn"
            :class="{ 'jog-active': activeKey === 'roll_l' }"
            @mousedown="startJog('roll_l', { kind: 'joint', idx: 5, dir: -1 })"
            @mouseup="stopManualJog"
            @mouseleave="stopManualJog"
            @touchstart.prevent="startJog('roll_l', { kind: 'joint', idx: 5, dir: -1 })"
            @touchend.prevent="stopManualJog"
            @touchcancel.prevent="stopManualJog"
          >
            <span class="btn-main">↶ ROLL L</span>
          </button>
          <div class="z-center mono">
            <span>ROLL</span>
            <span>{{ degStr(5) }}°</span>
          </div>
          <button
            class="jog-btn manual-dpad-btn"
            :class="{ 'jog-active': activeKey === 'roll_r' }"
            @mousedown="startJog('roll_r', { kind: 'joint', idx: 5, dir: 1 })"
            @mouseup="stopManualJog"
            @mouseleave="stopManualJog"
            @touchstart.prevent="startJog('roll_r', { kind: 'joint', idx: 5, dir: 1 })"
            @touchend.prevent="stopManualJog"
            @touchcancel.prevent="stopManualJog"
          >
            <span class="btn-main">↷ ROLL R</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useArmRos } from './useArmRos'
import {
  clampJointRad,
  computeArmToolFrame,
  computePlanarState,
  stepCylindricalBoom,
  stepWristYawWithRollComp
} from './armKinematics'

const DT_SEC = 0.05
const TRAJ_DURATION_SEC = 0.08
const MAX_LINEAR_MPS = 0.15
const MAX_ANGULAR_RAD_S = 0.7

const {
  currentJointAnglesRad,
  hubExecuting,
  resetHubTask,
  publishJointPositionsRad,
  registerStopCallback
} = useArmRos()

const speedPercent = ref(50)
const autoLevelWrist = ref(true)
const activeKey = ref(null)
const limitWarning = ref('')

let jogTimer = null
let latchedJoints = null
let targetJawRollZ = 0
let unregisterStop = null

const planarState = computed(() => computePlanarState(currentJointAnglesRad.value))

const degStr = (idx) => {
  const rad = currentJointAnglesRad.value[idx] || 0
  return ((rad * 180.0) / Math.PI).toFixed(1)
}

const stopManualJog = () => {
  if (jogTimer) {
    clearInterval(jogTimer)
    jogTimer = null
  }
  activeKey.value = null
  latchedJoints = null
  limitWarning.value = ''
}

const runJogTick = (action) => {
  if (!latchedJoints) return

  const scale = speedPercent.value / 100.0
  const vLin = MAX_LINEAR_MPS * scale
  const omega = MAX_ANGULAR_RAD_S * scale

  if (action.kind === 'boom') {
    const dR = action.dR * vLin * DT_SEC
    const dZ = action.dZ * vLin * DT_SEC
    const res = stepCylindricalBoom(latchedJoints, dR, dZ, autoLevelWrist.value)
    if (!res.applied) {
      limitWarning.value = res.reason === 'MAX_REACH' ? 'MAX REACH' : 'JOINT LIMIT'
      return
    }
    limitWarning.value = ''
    latchedJoints = res.joints
    publishJointPositionsRad(latchedJoints, TRAJ_DURATION_SEC)
    return
  }

  if (action.kind === 'wrist_yaw') {
    const dq3 = action.dir * omega * DT_SEC
    const res = stepWristYawWithRollComp(latchedJoints, dq3, targetJawRollZ)
    if (!res.applied) {
      limitWarning.value = 'WRIST LIMIT'
      return
    }
    limitWarning.value = ''
    latchedJoints = res.joints
    publishJointPositionsRad(latchedJoints, TRAJ_DURATION_SEC)
    return
  }

  if (action.kind === 'joint') {
    const dq = action.dir * omega * DT_SEC
    const prev = latchedJoints[action.idx]
    const next = clampJointRad(action.idx, prev + dq)
    if (Math.abs(next - prev) < 1e-6) {
      limitWarning.value = 'JOINT LIMIT'
      return
    }
    limitWarning.value = ''
    latchedJoints[action.idx] = next
    publishJointPositionsRad(latchedJoints, TRAJ_DURATION_SEC)
  }
}

const startJog = (key, action) => {
  if (hubExecuting.value) {
    resetHubTask()
  }
  stopManualJog()

  activeKey.value = key
  // Latch current /joint_states once on press so small steps accumulate cleanly over 50ms ticks
  latchedJoints = [...currentJointAnglesRad.value]
  if (action.kind === 'wrist_yaw') {
    const z0 = computeArmToolFrame(latchedJoints).zAxis[2]
    targetJawRollZ = Math.abs(z0) < 0.08 ? 0 : z0
  }

  runJogTick(action)
  jogTimer = setInterval(() => runJogTick(action), DT_SEC * 1000)
}

onMounted(() => {
  unregisterStop = registerStopCallback(stopManualJog)
  window.addEventListener('mouseup', stopManualJog)
  window.addEventListener('touchend', stopManualJog)
  window.addEventListener('touchcancel', stopManualJog)
  window.addEventListener('blur', stopManualJog)
})

onBeforeUnmount(() => {
  window.removeEventListener('mouseup', stopManualJog)
  window.removeEventListener('touchend', stopManualJog)
  window.removeEventListener('touchcancel', stopManualJog)
  window.removeEventListener('blur', stopManualJog)
  unregisterStop?.()
  stopManualJog()
})

defineExpose({
  stopManualJog
})
</script>

<style scoped>
.manual-toggle-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 2px;
}

.autolevel-label {
  display: flex;
  align-items: center;
  gap: 7px;
  cursor: pointer;
  user-select: none;
}

.autolevel-checkbox {
  width: 14px;
  height: 14px;
  accent-color: var(--accent);
  cursor: pointer;
}

.planar-readout {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
  flex-wrap: wrap;
  font-size: 10px;
  color: var(--muted);
  background: var(--bg-item);
  border: 1px solid var(--border-subtle);
  border-radius: 3px;
  padding: 5px 8px;
}

.planar-readout b {
  color: var(--text);
}

.planar-readout .sep {
  opacity: 0.4;
}

.manual-dpad-btn {
  flex-direction: column;
  gap: 1px;
  padding: 3px 4px;
  font-size: 11px;
  line-height: 1.1;
}

.btn-main {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.btn-sub {
  font-size: 8px;
  font-weight: 600;
  color: var(--muted);
  line-height: 1;
}

.jog-active {
  background: var(--accent) !important;
  color: #ffffff !important;
  border-color: var(--accent) !important;
}

.jog-active .btn-sub {
  color: rgba(255, 255, 255, 0.85);
}

.boom-center,
.wrist-center {
  font-size: 9px;
}

.live-badge.warn {
  background: rgba(245, 158, 11, 0.2);
  color: var(--orange);
}
</style>
