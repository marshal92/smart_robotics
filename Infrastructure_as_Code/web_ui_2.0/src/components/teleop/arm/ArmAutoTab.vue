<template>
  <div class="subtab-pane">
    <!-- MoveIt + Control Hub Lifecycle Controls (No RViz) -->
    <div class="arm-backend-pair">
      <button class="cmd-btn border-btn b-orange compact-btn" @click="pubSmartCommand('system', 'arm_moveit_on')">
        MoveIt ON
      </button>
      <button class="cmd-btn border-btn b-red compact-btn" @click="pubSmartCommand('system', 'arm_moveit_off')">
        MoveIt OFF
      </button>
    </div>

    <div class="teleop-card">
      <div class="section-title">CONTROL HUB (AUTO MISSIONS)</div>

      <div class="hub-select-row">
        <select v-model="selectedHubTask" class="map-input compact-input hub-select" :disabled="hubExecuting">
          <option value="/home/oleksandr/ros2_ws/src/manipulator_stack/manipulator_control/manipulator_control/test/square_horizontal.csv">
            Draw Square (Horizontal CSV)
          </option>
          <option value="/home/oleksandr/ros2_ws/src/manipulator_stack/manipulator_control/manipulator_control/test/square_vertical.csv">
            Draw Square (Vertical CSV)
          </option>
        </select>
      </div>

      <div class="settings-card" style="margin-top: 8px;">
        <div class="speed-row">
          <span class="ctrl-label">SPEED: <span class="mono accent-text">{{ autoSpeedPercent }}%</span></span>
          <input
            type="range"
            min="5"
            max="100"
            step="5"
            v-model.number="autoSpeedPercent"
            class="compact-slider"
            :disabled="hubExecuting"
          />
        </div>
      </div>

      <div class="hub-btn-grid">
        <button
          class="cmd-btn border-btn b-blue hub-run-btn"
          :disabled="hubExecuting"
          @click="handleStartTask"
        >
          {{ hubExecuting && activeHubCmd === 'auto' ? '⏳ EXECUTING TASK...' : '▶ START TASK' }}
        </button>
        <button class="cmd-btn border-btn b-red hub-reset-btn" @click="resetHubTask">
          ⏹ RESET
        </button>
      </div>

      <div class="progress-wrap">
        <div class="progress-bar-bg">
          <div
            class="progress-bar-fill"
            :style="{ width: hubProgress + '%', backgroundColor: hubProgressColor }"
          ></div>
        </div>
        <div class="hub-status-text mono">
          <span>{{ hubStatusState }}</span>
          <span>{{ hubProgress }}%</span>
        </div>
      </div>
    </div>

    <!-- Go To Coordinates (uses control_hub + move_group IK/planner) -->
    <div class="teleop-card">
      <div class="section-title">GO TO COORDINATES (BASE, MM)</div>
      <div class="goto-xyz-grid">
        <div class="goto-input-wrap">
          <label class="goto-lbl"><span class="axis-dot axis-x"></span> X</label>
          <input type="number" v-model.number="manualTargetMm.x" step="5" class="map-input compact-input goto-input" placeholder="mm" />
        </div>
        <div class="goto-input-wrap">
          <label class="goto-lbl"><span class="axis-dot axis-y"></span> Y</label>
          <input type="number" v-model.number="manualTargetMm.y" step="5" class="map-input compact-input goto-input" placeholder="mm" />
        </div>
        <div class="goto-input-wrap">
          <label class="goto-lbl"><span class="axis-dot axis-z"></span> Z</label>
          <input type="number" v-model.number="manualTargetMm.z" step="5" class="map-input compact-input goto-input" placeholder="mm" />
        </div>
      </div>
      <div class="goto-btn-row">
        <button
          class="cmd-btn compact-btn"
          @click="syncManualTargetFromPose"
          :disabled="!hasToolPoseData"
          title="Fill inputs with live TCP pose"
        >
          SYNC
        </button>
        <button
          class="cmd-btn border-btn b-blue compact-btn"
          @click="handleStartGoto"
          :disabled="hubExecuting || !isValidManualCoords"
        >
          {{ hubExecuting && activeHubCmd === 'goto' ? '⏳ MOVING...' : '▶ GO TO XYZ' }}
        </button>
        <button class="cmd-btn border-btn b-red compact-btn" @click="resetHubTask">
          ⏹ STOP
        </button>
      </div>
      <div v-if="gotoStatusText" class="goto-status mono" :class="gotoStatusType">
        {{ gotoStatusText }}
      </div>
    </div>

    <!-- Execution Logs Box -->
    <div class="telemetry-card">
      <div class="telemetry-header">
        <span>EXECUTION LOGS</span>
        <button class="clear-log-btn" @click="hubLogs = []">CLEAR</button>
      </div>
      <div class="hub-log-box mono">
        <div v-if="hubLogs.length === 0" class="log-placeholder">Waiting for task execution...</div>
        <div v-for="(log, idx) in hubLogs" :key="idx" class="log-entry" :class="log.type">
          <span class="log-time">[{{ log.time }}]</span> {{ log.text }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useArmRos } from './useArmRos'

const props = defineProps({
  active: {
    type: Boolean,
    default: false
  }
})

const {
  store,
  pubSmartCommand,
  hasToolPoseData,
  toolPose,
  hubExecuting,
  activeHubCmd,
  hubProgress,
  hubStatusState,
  hubProgressColor,
  hubLogs,
  gotoStatusText,
  gotoStatusType,
  startHubCsvTask,
  startHubGotoXyz,
  resetHubTask,
  stopAllMotion
} = useArmRos()

const selectedHubTask = ref(
  '/home/oleksandr/ros2_ws/src/manipulator_stack/manipulator_control/manipulator_control/test/square_horizontal.csv'
)
const autoSpeedPercent = ref(30)
const manualTargetMm = ref({ x: null, y: null, z: null })
const hasAutoSyncedCoords = ref(false)

const isValidManualCoords = computed(() => {
  const { x, y, z } = manualTargetMm.value
  return (
    x !== '' && y !== '' && z !== '' &&
    Number.isFinite(Number(x)) &&
    Number.isFinite(Number(y)) &&
    Number.isFinite(Number(z))
  )
})

const SQUARE_HORIZONTAL_POINTS = [
  { x: 0.225, y: -0.075, z: 0.1 }, { x: 0.225, y: -0.0536, z: 0.1 }, { x: 0.225, y: -0.0321, z: 0.1 },
  { x: 0.225, y: -0.0107, z: 0.1 }, { x: 0.225, y: 0.0107, z: 0.1 }, { x: 0.225, y: 0.0321, z: 0.1 },
  { x: 0.225, y: 0.0536, z: 0.1 }, { x: 0.225, y: 0.075, z: 0.1 }, { x: 0.2464, y: 0.075, z: 0.1 },
  { x: 0.2679, y: 0.075, z: 0.1 }, { x: 0.2893, y: 0.075, z: 0.1 }, { x: 0.3107, y: 0.075, z: 0.1 },
  { x: 0.3321, y: 0.075, z: 0.1 }, { x: 0.3536, y: 0.075, z: 0.1 }, { x: 0.375, y: 0.075, z: 0.1 },
  { x: 0.375, y: 0.0536, z: 0.1 }, { x: 0.375, y: 0.0321, z: 0.1 }, { x: 0.375, y: 0.0107, z: 0.1 },
  { x: 0.375, y: -0.0107, z: 0.1 }, { x: 0.375, y: -0.0321, z: 0.1 }, { x: 0.375, y: -0.0536, z: 0.1 },
  { x: 0.375, y: -0.075, z: 0.1 }, { x: 0.3536, y: -0.075, z: 0.1 }, { x: 0.3321, y: -0.075, z: 0.1 },
  { x: 0.3107, y: -0.075, z: 0.1 }, { x: 0.2893, y: -0.075, z: 0.1 }, { x: 0.2679, y: -0.075, z: 0.1 },
  { x: 0.2464, y: -0.075, z: 0.1 }, { x: 0.225, y: -0.075, z: 0.1 }
]

const SQUARE_VERTICAL_POINTS = [
  { x: 0.3, y: -0.075, z: 0.325 }, { x: 0.3, y: -0.0536, z: 0.325 }, { x: 0.3, y: -0.0321, z: 0.325 },
  { x: 0.3, y: -0.0107, z: 0.325 }, { x: 0.3, y: 0.0107, z: 0.325 }, { x: 0.3, y: 0.0321, z: 0.325 },
  { x: 0.3, y: 0.0536, z: 0.325 }, { x: 0.3, y: 0.075, z: 0.325 }, { x: 0.3, y: 0.075, z: 0.3036 },
  { x: 0.3, y: 0.075, z: 0.2821 }, { x: 0.3, y: 0.075, z: 0.2607 }, { x: 0.3, y: 0.075, z: 0.2393 },
  { x: 0.3, y: 0.075, z: 0.2179 }, { x: 0.3, y: 0.075, z: 0.1964 }, { x: 0.3, y: 0.075, z: 0.175 },
  { x: 0.3, y: 0.0536, z: 0.175 }, { x: 0.3, y: 0.0321, z: 0.175 }, { x: 0.3, y: 0.0107, z: 0.175 },
  { x: 0.3, y: -0.0107, z: 0.175 }, { x: 0.3, y: -0.0321, z: 0.175 }, { x: 0.3, y: -0.0536, z: 0.175 },
  { x: 0.3, y: -0.075, z: 0.175 }, { x: 0.3, y: -0.075, z: 0.1964 }, { x: 0.3, y: -0.075, z: 0.2179 },
  { x: 0.3, y: -0.075, z: 0.2393 }, { x: 0.3, y: -0.075, z: 0.2607 }, { x: 0.3, y: -0.075, z: 0.2821 },
  { x: 0.3, y: -0.075, z: 0.3036 }, { x: 0.3, y: -0.075, z: 0.325 }
]

const updatePlannedPath = (taskPath) => {
  if (taskPath && taskPath.includes('square_vertical')) {
    store.setPlannedArmPath(SQUARE_VERTICAL_POINTS)
  } else if (taskPath && taskPath.includes('square_horizontal')) {
    store.setPlannedArmPath(SQUARE_HORIZONTAL_POINTS)
  } else {
    store.setPlannedArmPath(null)
  }
}

watch(selectedHubTask, (newPath) => {
  if (props.active) updatePlannedPath(newPath)
})

watch(() => props.active, (isActive) => {
  if (isActive) {
    updatePlannedPath(selectedHubTask.value)
  } else {
    store.setPlannedArmPath(null)
  }
})

const syncManualTargetFromPose = () => {
  if (!hasToolPoseData.value) return
  manualTargetMm.value = {
    x: Math.round(toolPose.value.x * 10) / 10,
    y: Math.round(toolPose.value.y * 10) / 10,
    z: Math.round(toolPose.value.z * 10) / 10
  }
}

watch(hasToolPoseData, (hasData) => {
  if (hasData && !hasAutoSyncedCoords.value) {
    syncManualTargetFromPose()
    hasAutoSyncedCoords.value = true
  }
})

const handleStartTask = () => {
  stopAllMotion()
  startHubCsvTask(selectedHubTask.value, autoSpeedPercent.value / 100.0)
}

const handleStartGoto = () => {
  if (!isValidManualCoords.value || hubExecuting.value) return
  stopAllMotion()
  const xM = Number(manualTargetMm.value.x) / 1000.0
  const yM = Number(manualTargetMm.value.y) / 1000.0
  const zM = Number(manualTargetMm.value.z) / 1000.0
  startHubGotoXyz(xM, yM, zM, Math.max(0.05, autoSpeedPercent.value / 100.0))
}
</script>

<style scoped>
.hub-select-row {
  margin-bottom: 10px;
}

.hub-select {
  width: 100%;
}

.hub-btn-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 8px;
  margin-top: 10px;
  margin-bottom: 12px;
}

.hub-run-btn,
.hub-reset-btn {
  width: 100%;
  padding: 8px 10px !important;
  font-size: 11px !important;
  margin-bottom: 0 !important;
}

.progress-wrap {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.progress-bar-bg {
  width: 100%;
  height: 8px;
  background: var(--bg-item);
  border: 1px solid var(--border);
  border-radius: 3px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  transition: width 0.3s ease, background-color 0.3s ease;
}

.hub-status-text {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--muted);
}

.goto-xyz-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 6px;
}

.goto-input-wrap {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.goto-lbl {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  font-weight: 700;
  color: var(--muted);
}

.goto-input {
  width: 100%;
  box-sizing: border-box;
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  text-align: center;
}

.goto-btn-row {
  display: grid;
  grid-template-columns: 72px 1fr 78px;
  gap: 6px;
  margin-top: 8px;
}

.goto-status {
  margin-top: 6px;
  font-size: 10px;
  padding: 4px 6px;
  border-radius: 3px;
  background: var(--bg-item);
  border: 1px solid var(--border-subtle);
  color: var(--muted);
}

.goto-status.success {
  color: var(--green);
  border-color: rgba(34, 197, 94, 0.35);
}

.goto-status.error {
  color: var(--red);
  border-color: rgba(239, 68, 68, 0.35);
}

.goto-status.warning {
  color: var(--orange);
}

.clear-log-btn {
  background: transparent;
  border: none;
  color: var(--muted);
  font-size: 10px;
  cursor: pointer;
}

.clear-log-btn:hover {
  color: var(--text);
}

.hub-log-box {
  background: var(--console-bg);
  border: 1px solid var(--border-subtle);
  border-radius: 3px;
  padding: 8px;
  height: 120px;
  overflow-y: auto;
  font-size: 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.log-placeholder {
  color: var(--muted);
  font-style: italic;
}

.log-entry {
  color: var(--console-text);
  word-break: break-all;
}

.log-entry.success {
  color: var(--green);
}

.log-entry.error {
  color: var(--red);
}

.log-entry.warning {
  color: var(--orange);
}

.log-time {
  color: var(--muted);
}
</style>
