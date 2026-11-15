<template>
  <div class="subtab-pane manual-pane">
    <!-- Compact Top Settings Row (Speed + Auto-Level J4 + Gamepad Switch) -->
    <div class="settings-card manual-settings-card">
      <div class="manual-settings-row">
        <span class="ctrl-label manual-speed-lbl">SPEED: <span class="mono accent-text">{{ speedPercent }}%</span></span>
        <input
          type="range"
          min="10"
          max="100"
          step="5"
          v-model.number="speedPercent"
          class="compact-slider manual-speed-slider"
        />
        <label class="autolevel-label" title="Keep gripper pitch constant during boom R/Z motion">
          <input type="checkbox" v-model="autoLevelWrist" class="autolevel-checkbox" />
          <span class="autolevel-text">LVL J4</span>
          <span class="live-badge" :class="{ active: autoLevelWrist }">
            {{ autoLevelWrist ? 'ON' : 'OFF' }}
          </span>
        </label>
      </div>

      <div class="manual-gamepad-row">
        <span
          class="gp-status-lbl"
          :title="store.gamepadName || 'Connect Xbox Series X (USB/BT) & press any button to wake'"
        >
          <span class="status-dot gp-dot" :class="{ 'is-on': store.gamepadConnected }"></span>
          <span>XBOX</span>
        </span>
        <div class="segmented-control gp-switch">
          <button
            type="button"
            class="seg-btn"
            :class="{ active: store.gamepadMode === 'off' }"
            @click="store.setGamepadMode('off')"
            title="Mute gamepad input"
          >
            OFF
          </button>
          <button
            type="button"
            class="seg-btn"
            :class="{ active: store.gamepadMode === 'drive', 'gp-shadow': store.gamepadMode === 'drive' && store.driveTarget === 'shadow' }"
            @click="store.setGamepadMode('drive')"
            :title="`Drive ${store.driveTarget === 'shadow' ? 'Shadow Twin (/cmd_vel_shadow)' : 'Base Robot (/cmd_vel)'} with RT/LT + Left Stick`"
          >
            {{ store.driveTarget === 'shadow' ? 'DRIVE · SHD' : 'DRIVE · BASE' }}
          </button>
          <button
            type="button"
            class="seg-btn"
            :class="{ active: store.gamepadMode === 'arm' }"
            @click="store.setGamepadMode('arm')"
            title="Control 2.5D Manipulator + Gripper with Xbox sticks, triggers, bumpers & A/X"
          >
            ARM
          </button>
        </div>
      </div>

      <div v-if="store.gamepadConnected || store.gamepadMode === 'arm'" class="gp-hint mono">
        <template v-if="store.gamepadMode === 'arm'">
          L: R/Base · R: Pitch/Wrist(inv) · RT/LT: Z+/- · LB/RB: Roll · A/X: Grip · D↕: Unfold/Fold · D↔: Spd · View: Mode · Y: Light · B: Stop
        </template>
        <template v-else-if="store.gamepadMode === 'drive'">
          RT/LT: Fwd/Rev · L: Steer ({{ store.driveTarget.toUpperCase() }}) · R: Cam · R3: Follow · D↕: Unfold/Fold · D↔: Spd · View: Mode · Y: Light · B: Stop
        </template>
        <template v-else>
          Gamepad muted (switch to DRIVE or ARM to enable).
        </template>
      </div>
    </div>

    <!-- Dual Side-by-Side D-Pads (Boom Left | Wrist Right) + Z & Roll Strips + Gripper -->
    <div class="teleop-card manual-pad-card">
      <div class="manual-dual-grid">
        <!-- Left Column: Boom Cylindrical D-Pad + Z Lift Strip -->
        <div class="manual-col">
          <div class="telemetry-header mini-header">
            <span>BOOM (R / YAW)</span>
            <span class="live-badge" :class="{ active: !limitWarning, warn: !!limitWarning }">
              {{ limitWarning || `R:${Math.round(planarState.reachMm)}mm` }}
            </span>
          </div>

          <div class="mini-dpad">
            <div class="dpad-slot"></div>
            <button
              class="jog-btn manual-dpad-btn"
              :class="{ 'jog-active': activeKey === 'reach_fwd' }"
              v-on="jogEvents('reach_fwd', { kind: 'boom', dR: 1, dZ: 0 })"
            >
              <span class="btn-main"><span class="axis-dot axis-x"></span>▲ R+</span>
            </button>
            <div class="dpad-slot"></div>

            <button
              class="jog-btn manual-dpad-btn"
              :class="{ 'jog-active': activeKey === 'base_l' }"
              v-on="jogEvents('base_l', { kind: 'joint', idx: 0, dir: 1 })"
            >
              <span class="btn-main">◀ BASE</span>
            </button>

            <div class="dpad-center mini-center mono">
              <span>J0 {{ degStr(0) }}°</span>
              <span>J1 {{ degStr(1) }}°</span>
              <span>J2 {{ degStr(2) }}°</span>
            </div>

            <button
              class="jog-btn manual-dpad-btn"
              :class="{ 'jog-active': activeKey === 'base_r' }"
              v-on="jogEvents('base_r', { kind: 'joint', idx: 0, dir: -1 })"
            >
              <span class="btn-main">BASE ▶</span>
            </button>

            <div class="dpad-slot"></div>
            <button
              class="jog-btn manual-dpad-btn"
              :class="{ 'jog-active': activeKey === 'reach_back' }"
              v-on="jogEvents('reach_back', { kind: 'boom', dR: -1, dZ: 0 })"
            >
              <span class="btn-main"><span class="axis-dot axis-x"></span>▼ R-</span>
            </button>
            <div class="dpad-slot"></div>
          </div>

          <!-- Z Height Strip directly under Boom D-Pad -->
          <div class="manual-strip-row">
            <button
              class="jog-btn manual-strip-btn"
              :class="{ 'jog-active': activeKey === 'z_down' }"
              v-on="jogEvents('z_down', { kind: 'boom', dR: 0, dZ: -1 })"
            >
              <span class="axis-dot axis-z"></span>▼ Z-
            </button>
            <div class="z-center strip-center mono">
              <span>Z</span>
              <span>{{ Math.round(planarState.heightMm) }}</span>
            </div>
            <button
              class="jog-btn manual-strip-btn"
              :class="{ 'jog-active': activeKey === 'z_up' }"
              v-on="jogEvents('z_up', { kind: 'boom', dR: 0, dZ: 1 })"
            >
              <span class="axis-dot axis-z"></span>▲ Z+
            </button>
          </div>
        </div>

        <!-- Right Column: Wrist D-Pad + Roll Strip -->
        <div class="manual-col">
          <div class="telemetry-header mini-header">
            <span>WRIST</span>
            <span class="live-badge">J3+J5 LVL</span>
          </div>

          <div class="mini-dpad">
            <div class="dpad-slot"></div>
            <button
              class="jog-btn manual-dpad-btn"
              :class="{ 'jog-active': activeKey === 'pitch_up' }"
              v-on="jogEvents('pitch_up', { kind: 'joint', idx: 4, dir: 1 })"
            >
              <span class="btn-main">▲ PITCH</span>
            </button>
            <div class="dpad-slot"></div>

            <button
              class="jog-btn manual-dpad-btn"
              :class="{ 'jog-active': activeKey === 'wrist_l' }"
              v-on="jogEvents('wrist_l', { kind: 'wrist_yaw', dir: -1 })"
            >
              <span class="btn-main">◀ WRIST</span>
            </button>

            <div class="dpad-center mini-center mono">
              <span>J3 {{ degStr(3) }}°</span>
              <span>J4 {{ degStr(4) }}°</span>
              <span>J5 {{ degStr(5) }}°</span>
            </div>

            <button
              class="jog-btn manual-dpad-btn"
              :class="{ 'jog-active': activeKey === 'wrist_r' }"
              v-on="jogEvents('wrist_r', { kind: 'wrist_yaw', dir: 1 })"
            >
              <span class="btn-main">WRIST ▶</span>
            </button>

            <div class="dpad-slot"></div>
            <button
              class="jog-btn manual-dpad-btn"
              :class="{ 'jog-active': activeKey === 'pitch_down' }"
              v-on="jogEvents('pitch_down', { kind: 'joint', idx: 4, dir: -1 })"
            >
              <span class="btn-main">▼ PITCH</span>
            </button>
            <div class="dpad-slot"></div>
          </div>

          <!-- Roll Strip directly under Wrist D-Pad -->
          <div class="manual-strip-row">
            <button
              class="jog-btn manual-strip-btn"
              :class="{ 'jog-active': activeKey === 'roll_l' }"
              v-on="jogEvents('roll_l', { kind: 'joint', idx: 5, dir: -1 })"
            >
              ↶ ROLL L
            </button>
            <div class="z-center strip-center mono">
              <span>ROLL</span>
              <span>{{ degStr(5) }}°</span>
            </div>
            <button
              class="jog-btn manual-strip-btn"
              :class="{ 'jog-active': activeKey === 'roll_r' }"
              v-on="jogEvents('roll_r', { kind: 'joint', idx: 5, dir: 1 })"
            >
              ROLL R ↷
            </button>
          </div>
        </div>
      </div>

      <!-- Compact Gripper Bar -->
      <div class="manual-gripper-bar">
        <span class="grip-lbl" :class="{ warn: !!clampWarning }">
          {{ clampWarning || 'GRIP' }}
        </span>
        <button
          class="jog-btn manual-strip-btn grip-btn"
          :class="{ 'jog-active': activeKey === 'clamp_close' }"
          v-on="jogEvents('clamp_close', { kind: 'clamp', dir: -1 })"
        >
          ◀ CLOSE
        </button>
        <div class="z-center grip-center mono" :title="`Clamp joint: ${currentClampRad.toFixed(2)} rad`">
          <span>{{ clampPctStr }}%</span>
          <span class="btn-sub">{{ currentClampRad.toFixed(2) }}rad</span>
        </div>
        <button
          class="jog-btn manual-strip-btn grip-btn"
          :class="{ 'jog-active': activeKey === 'clamp_open' }"
          v-on="jogEvents('clamp_open', { kind: 'clamp', dir: 1 })"
        >
          OPEN ▶
        </button>
      </div>
    </div>

    <!-- Sequential Joint Route Builder (Snapshot from Robot -> Playback) -->
    <ArmRouteSequencer ref="routeSeqRef" @before-run="stopManualJog" />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useArmRos } from './useArmRos'
import ArmRouteSequencer from './ArmRouteSequencer.vue'
import { registerArmGamepadHandlers } from '../../../services/gamepadService'
import {
  CLAMP_MIN_RAD,
  CLAMP_MAX_RAD,
  clampGripperRad,
  clampJointRad,
  computeArmToolFrame,
  computePlanarState,
  stepCylindricalBoom,
  stepWristYawWithRollComp
} from './armKinematics'

const emit = defineEmits(['unfold', 'fold'])

const DT_SEC = 0.05
const TRAJ_DURATION_SEC = 0.08
const MAX_LINEAR_MPS = 0.15
const MAX_ANGULAR_RAD_S = 0.7

const {
  store,
  currentJointAnglesRad,
  currentClampRad,
  hubExecuting,
  resetHubTask,
  publishJointPositionsRad,
  publishClampRad,
  registerStopCallback
} = useArmRos()

const routeSeqRef = ref(null)
const speedPercent = ref(50)
const autoLevelWrist = ref(true)
const activeKey = ref(null)
const limitWarning = ref('')
const clampWarning = ref('')

let jogTimer = null
let latchedJoints = null
let latchedClampRad = 0
let targetJawRollZ = 0
let wristYawLatched = false
let gamepadArmActive = false
let presetMoveUntil = 0
let unregisterStop = null
let unregisterGamepad = null

const planarState = computed(() => computePlanarState(currentJointAnglesRad.value))
const clampPctStr = computed(() => {
  const span = CLAMP_MAX_RAD - CLAMP_MIN_RAD
  const pct = ((currentClampRad.value - CLAMP_MIN_RAD) / span) * 100.0
  return Math.round(Math.min(100, Math.max(0, pct)))
})

const degStr = (idx) => {
  const rad = currentJointAnglesRad.value[idx] || 0
  return ((rad * 180.0) / Math.PI).toFixed(1)
}

const clearLatch = () => {
  latchedJoints = null
  wristYawLatched = false
  limitWarning.value = ''
  clampWarning.value = ''
}

const stopManualJog = () => {
  if (jogTimer) {
    clearInterval(jogTimer)
    jogTimer = null
  }
  activeKey.value = null
  gamepadArmActive = false
  clearLatch()
}

const stopJointRoute = (holdCurrent = true) => {
  routeSeqRef.value?.stopJointRoute(holdCurrent)
}

// Convert legacy single-button jog descriptor into unified multi-axis motion vector
function actionToMotion(action) {
  if (action.kind === 'clamp') return { grip: action.dir }
  if (action.kind === 'boom') return { reach: action.dR || 0, z: action.dZ || 0 }
  if (action.kind === 'wrist_yaw') return { wristYaw: action.dir }
  if (action.kind === 'joint') {
    if (action.idx === 0) return { baseYaw: action.dir }
    if (action.idx === 4) return { pitch: action.dir }
    if (action.idx === 5) return { roll: action.dir }
  }
  return {}
}

function stepManualMotion(motion) {
  const reach = Number(motion.reach) || 0
  const z = Number(motion.z) || 0
  const baseYaw = Number(motion.baseYaw) || 0
  const pitch = Number(motion.pitch) || 0
  const wristYaw = Number(motion.wristYaw) || 0
  const roll = Number(motion.roll) || 0
  const grip = Number(motion.grip) || 0

  const scale = speedPercent.value / 100.0
  const vLin = MAX_LINEAR_MPS * scale
  const omega = MAX_ANGULAR_RAD_S * scale

  if (!latchedJoints) {
    latchedJoints = [...currentJointAnglesRad.value]
    latchedClampRad = currentClampRad.value
    wristYawLatched = false
  }

  if (Math.abs(grip) > 0) {
    const nextClamp = clampGripperRad(latchedClampRad + grip * omega * DT_SEC)
    if (Math.abs(nextClamp - latchedClampRad) < 1e-6) {
      clampWarning.value = grip < 0 ? 'CLOSED' : 'OPEN'
    } else {
      clampWarning.value = ''
      latchedClampRad = nextClamp
      publishClampRad(nextClamp, TRAJ_DURATION_SEC)
    }
  } else {
    clampWarning.value = ''
  }

  let q = [...latchedJoints]
  let jointsChanged = false
  let warn = ''

  if (Math.abs(reach) > 0 || Math.abs(z) > 0) {
    const dR = reach * vLin * DT_SEC
    const dZ = z * vLin * DT_SEC
    const res = stepCylindricalBoom(q, dR, dZ, autoLevelWrist.value)
    if (res.applied) {
      q = res.joints
      jointsChanged = true
    } else {
      warn = res.reason === 'MAX_REACH' ? 'MAX REACH' : 'JOINT LIMIT'
    }
  }

  if (Math.abs(baseYaw) > 0) {
    const next0 = clampJointRad(0, q[0] + baseYaw * omega * DT_SEC)
    if (Math.abs(next0 - q[0]) >= 1e-6) {
      q[0] = next0
      jointsChanged = true
    } else if (!warn) {
      warn = 'JOINT LIMIT'
    }
  }

  if (Math.abs(wristYaw) > 0) {
    if (!wristYawLatched) {
      const z0 = computeArmToolFrame(q).zAxis[2]
      targetJawRollZ = Math.abs(z0) < 0.08 ? 0 : z0
      wristYawLatched = true
    }
    const dq3 = wristYaw * omega * DT_SEC
    const res = stepWristYawWithRollComp(q, dq3, targetJawRollZ)
    if (res.applied) {
      q = res.joints
      jointsChanged = true
    } else if (!warn) {
      warn = 'WRIST LIMIT'
    }
  } else {
    wristYawLatched = false
  }

  if (Math.abs(pitch) > 0) {
    const next4 = clampJointRad(4, q[4] + pitch * omega * DT_SEC)
    if (Math.abs(next4 - q[4]) >= 1e-6) {
      q[4] = next4
      jointsChanged = true
    } else if (!warn) {
      warn = 'JOINT LIMIT'
    }
  }

  if (Math.abs(roll) > 0) {
    const next5 = clampJointRad(5, q[5] + roll * omega * DT_SEC)
    if (Math.abs(next5 - q[5]) >= 1e-6) {
      q[5] = next5
      jointsChanged = true
      wristYawLatched = false
    } else if (!warn) {
      warn = 'JOINT LIMIT'
    }
  }

  limitWarning.value = warn
  if (jointsChanged) {
    presetMoveUntil = 0
    latchedJoints = q
    publishJointPositionsRad(latchedJoints, TRAJ_DURATION_SEC)
  }
}

const startJog = (key, action) => {
  if (hubExecuting.value) {
    resetHubTask()
  }
  routeSeqRef.value?.stopJointRoute(false)
  stopManualJog()

  activeKey.value = key
  const motion = actionToMotion(action)
  stepManualMotion(motion)
  jogTimer = setInterval(() => stepManualMotion(motion), DT_SEC * 1000)
}

const jogEvents = (key, action) => ({
  mousedown: () => startJog(key, action),
  mouseup: stopManualJog,
  mouseleave: stopManualJog,
  touchstart: (e) => {
    e.preventDefault()
    startJog(key, action)
  },
  touchend: (e) => {
    e.preventDefault()
    stopManualJog()
  },
  touchcancel: (e) => {
    e.preventDefault()
    stopManualJog()
  }
})

onMounted(() => {
  unregisterStop = registerStopCallback(stopManualJog)
  unregisterGamepad = registerArmGamepadHandlers({
    onStep: (motion) => {
      if (!store.isConnected || hubExecuting.value) return
      if (!gamepadArmActive) {
        if (jogTimer) {
          clearInterval(jogTimer)
          jogTimer = null
          activeKey.value = null
        }
        routeSeqRef.value?.stopJointRoute(false)
        clearLatch()
        gamepadArmActive = true
      }
      stepManualMotion(motion)
    },
    onStop: () => {
      if (gamepadArmActive) {
        gamepadArmActive = false
        clearLatch()
      }
    },
    onEmergencyStop: () => {
      stopManualJog()
      routeSeqRef.value?.stopJointRoute(true)
      if (Date.now() < presetMoveUntil) {
        presetMoveUntil = 0
        publishJointPositionsRad(currentJointAnglesRad.value, 0.1)
      }
      if (hubExecuting.value) {
        resetHubTask()
      }
    },
    onUnfold: () => {
      presetMoveUntil = Date.now() + 3200
      emit('unfold')
    },
    onFold: () => {
      presetMoveUntil = Date.now() + 3200
      emit('fold')
    },
    onStepSpeed: (delta) => {
      speedPercent.value = Math.min(100, Math.max(10, speedPercent.value + delta))
    },
    onToggleAutoLevel: () => {
      autoLevelWrist.value = !autoLevelWrist.value
    }
  })

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
  unregisterGamepad?.()
  unregisterStop?.()
  stopManualJog()
})

defineExpose({
  stopManualJog,
  stopJointRoute
})
</script>

<style scoped>
.manual-pane {
  gap: 8px;
}

.manual-settings-card {
  padding: 6px 8px;
}

.manual-settings-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.manual-speed-lbl {
  min-width: 68px;
  font-size: 10px;
}

.autolevel-label {
  display: flex;
  align-items: center;
  gap: 5px;
  cursor: pointer;
  user-select: none;
  flex-shrink: 0;
}

.autolevel-checkbox {
  width: 13px;
  height: 13px;
  accent-color: var(--accent);
  cursor: pointer;
  margin: 0;
}

.autolevel-text {
  font-size: 10px;
  font-weight: 700;
  color: var(--muted);
}

.manual-gamepad-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px solid var(--border-subtle);
}

.gp-status-lbl {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  font-weight: 700;
  color: var(--muted);
  letter-spacing: 0.4px;
  flex-shrink: 0;
}

.gp-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #64748b;
  transition: all 0.2s;
}

.gp-dot.is-on {
  background: var(--green);
  box-shadow: 0 0 6px var(--green);
}

.gp-switch .seg-btn.active.gp-shadow {
  background: #0284c7;
}

.gp-hint {
  margin-top: 4px;
  font-size: 8.5px;
  line-height: 1.25;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.manual-pad-card {
  padding: 8px;
}

.manual-dual-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  align-items: start;
}

.manual-col {
  display: flex;
  flex-direction: column;
  gap: 5px;
  min-width: 0;
}

.mini-header {
  margin-bottom: 1px;
  font-size: 9.5px;
}

.mini-dpad {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  grid-template-rows: repeat(3, 35px);
  gap: 4px;
  width: 100%;
}

.manual-dpad-btn {
  flex-direction: column;
  gap: 1px;
  padding: 2px 3px;
  font-size: 9.5px;
  line-height: 1.05;
  min-width: 0;
  overflow: hidden;
}

.mini-center {
  font-size: 8.5px;
  line-height: 1.15;
  padding: 1px;
  overflow: hidden;
}

.btn-main {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
}

.btn-sub {
  font-size: 8px;
  font-weight: 600;
  color: var(--muted);
  line-height: 1;
}

.manual-strip-row {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 4px;
  height: 30px;
  align-items: stretch;
}

.manual-strip-btn {
  padding: 2px 4px;
  font-size: 9.5px;
  gap: 3px;
  min-width: 0;
}

.strip-center {
  min-width: 44px;
  padding: 1px 4px;
  font-size: 8.5px;
  line-height: 1.05;
}

.manual-gripper-bar {
  display: grid;
  grid-template-columns: auto 1fr auto 1fr;
  gap: 6px;
  align-items: stretch;
  margin-top: 7px;
  padding-top: 7px;
  border-top: 1px solid var(--border-subtle);
  height: 30px;
}

.grip-lbl {
  display: flex;
  align-items: center;
  font-size: 9.5px;
  font-weight: 700;
  color: var(--muted);
  padding-right: 2px;
  letter-spacing: 0.4px;
}

.grip-lbl.warn {
  color: var(--orange);
}

.grip-btn {
  min-height: 30px;
}

.grip-center {
  min-width: 70px;
  padding: 1px 6px;
  font-size: 9px;
  line-height: 1.05;
}

.jog-active {
  background: var(--accent) !important;
  color: #ffffff !important;
  border-color: var(--accent) !important;
}

.live-badge.warn {
  background: rgba(245, 158, 11, 0.2);
  color: var(--orange);
}

@media (max-width: 420px) {
  .manual-dual-grid {
    grid-template-columns: 1fr;
  }
}
</style>
