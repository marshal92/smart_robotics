<template>
  <div class="arm-control">
    <div class="arm-inner">
      <!-- Top Common Bar (Shared across all 4 Arm tabs; independent of MoveIt/Servo) -->
      <div class="arm-top-row">
        <button class="cmd-btn border-btn b-blue compact-btn" @click="unfoldRobot">
          Unfold
        </button>
        <button class="cmd-btn border-btn b-purple compact-btn" @click="foldRobot">
          Fold
        </button>
        <button
          class="trail-toggle-btn"
          :class="{ active: store.armTrailEnabled }"
          @click="store.toggleArmTrail()"
          title="Toggle Real-Time End-Effector 3D Trail (local URDF/TF)"
        >
          <span class="neon-indicator" :class="{ on: store.armTrailEnabled }"></span>
          <span>TRAIL: {{ store.armTrailEnabled ? 'ON' : 'OFF' }}</span>
        </button>
        <button
          class="trail-clear-btn"
          @click="store.clearArmTrail()"
          title="Clear Trail Geometry"
        >
          CLEAR
        </button>
      </div>

      <!-- Folder Binder Sub-Tabs + Content Sheet -->
      <div class="arm-folder-layout">
        <div class="arm-folder-tabs" role="tablist" aria-label="Manipulator control modes">
          <button
            v-for="tab in subTabs"
            :key="tab.id"
            role="tab"
            :aria-selected="activeSubTab === tab.id"
            class="arm-folder-tab"
            :class="{ active: activeSubTab === tab.id }"
            @click="setSubTab(tab.id)"
          >
            <span class="arm-folder-tab-label">{{ tab.label }}</span>
          </button>
        </div>

        <div class="arm-folder-body">
          <!-- TAB 1: JOINTS -->
          <ArmJointsTab
            v-show="activeSubTab === 'joints'"
            ref="jointsTabRef"
          />

          <!-- TAB 2: MANUAL (Cylindrical 2.5D Planar Kinematics) -->
          <ArmManualTab
            v-show="activeSubTab === 'manual'"
            ref="manualTabRef"
            @unfold="unfoldRobot"
            @fold="foldRobot"
          />

          <!-- TAB 3: AUTO (MoveIt + Control Hub + GoTo XYZ) -->
          <ArmAutoTab
            v-show="activeSubTab === 'auto'"
            :active="activeSubTab === 'auto'"
          />

          <!-- TAB 4: SERVO (MoveIt Servo + Cartesian IK Teleop) -->
          <ArmServoTab
            v-show="activeSubTab === 'servo'"
            ref="servoTabRef"
            @stop-other-motion="manualTabRef?.stopJointRoute(false)"
          />
        </div>
      </div>

      <!-- Shared Tool Pose Telemetry Card (Compact Single Row) -->
      <div class="telemetry-card">
        <div class="telemetry-header">
          <span>TOOL POSE TELEMETRY (BASE · mm / °)</span>
          <span class="live-badge" :class="{ active: hasToolPoseData }">
            {{ hasToolPoseData ? (telemetrySource === 'tf' ? 'LIVE 5Hz' : 'LIVE FK') : 'WAITING' }}
          </span>
        </div>
        <div class="telemetry-grid">
          <div class="telemetry-item">
            <span class="t-lbl">X</span>
            <span class="t-val mono">{{ toolPose.x !== null ? toolPose.x.toFixed(1) : '--' }}</span>
          </div>
          <div class="telemetry-item">
            <span class="t-lbl">Y</span>
            <span class="t-val mono">{{ toolPose.y !== null ? toolPose.y.toFixed(1) : '--' }}</span>
          </div>
          <div class="telemetry-item">
            <span class="t-lbl">Z</span>
            <span class="t-val mono">{{ toolPose.z !== null ? toolPose.z.toFixed(1) : '--' }}</span>
          </div>
          <div class="telemetry-item">
            <span class="t-lbl">R</span>
            <span class="t-val mono">{{ toolPose.roll !== null ? toolPose.roll.toFixed(1) : '--' }}°</span>
          </div>
          <div class="telemetry-item">
            <span class="t-lbl">P</span>
            <span class="t-val mono">{{ toolPose.pitch !== null ? toolPose.pitch.toFixed(1) : '--' }}°</span>
          </div>
          <div class="telemetry-item">
            <span class="t-lbl">YAW</span>
            <span class="t-val mono">{{ toolPose.yaw !== null ? toolPose.yaw.toFixed(1) : '--' }}°</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import './arm/armPanel.css'
import ArmJointsTab from './arm/ArmJointsTab.vue'
import ArmManualTab from './arm/ArmManualTab.vue'
import ArmAutoTab from './arm/ArmAutoTab.vue'
import ArmServoTab from './arm/ArmServoTab.vue'
import {
  FOLD_POSE_DEG,
  UNFOLD_POSE_DEG,
  provideArmRosContext
} from './arm/useArmRos'

const subTabs = [
  { id: 'joints', label: 'JOINTS' },
  { id: 'manual', label: 'MANUAL' },
  { id: 'auto', label: 'AUTO' },
  { id: 'servo', label: 'SERVO' }
]

const activeSubTab = ref('joints')
const jointsTabRef = ref(null)
const manualTabRef = ref(null)
const servoTabRef = ref(null)

const {
  store,
  hasToolPoseData,
  telemetrySource,
  toolPose,
  hubExecuting,
  addHubLog,
  publishJointPositionsDeg,
  publishMode,
  publishUnfoldSignal,
  publishFoldSignal,
  resetHubTask
} = provideArmRosContext()

const setSubTab = (tab) => {
  if (tab !== 'manual') {
    manualTabRef.value?.stopManualJog()
    manualTabRef.value?.stopJointRoute(true)
  }
  if (tab !== 'servo') {
    servoTabRef.value?.endTwist()
  }

  activeSubTab.value = tab
  if (tab === 'auto') {
    publishMode('AUTO')
    addHubLog('Mode switched to AUTO. Control Hub unlocked.', 'info')
  } else {
    publishMode('MANUAL')
    if (tab === 'servo') {
      addHubLog('Mode switched to SERVO (IK Teleop).', 'info')
    } else if (tab === 'manual') {
      addHubLog('Mode switched to MANUAL (Simple Planar).', 'info')
    } else {
      addHubLog('Mode switched to JOINTS.', 'info')
    }
  }
}

const unfoldRobot = () => {
  manualTabRef.value?.stopJointRoute(false)
  manualTabRef.value?.stopManualJog()
  servoTabRef.value?.endTwist()
  if (hubExecuting.value) resetHubTask()
  jointsTabRef.value?.setTargetAnglesDeg(UNFOLD_POSE_DEG)
  publishJointPositionsDeg(UNFOLD_POSE_DEG, 3.0)
  publishUnfoldSignal()
  addHubLog('Unfold command dispatched (Stand Pose: J4=-45°).', 'info')
}

const foldRobot = () => {
  manualTabRef.value?.stopJointRoute(false)
  manualTabRef.value?.stopManualJog()
  servoTabRef.value?.endTwist()
  if (hubExecuting.value) resetHubTask()
  jointsTabRef.value?.setTargetAnglesDeg(FOLD_POSE_DEG)
  publishJointPositionsDeg(FOLD_POSE_DEG, 3.0)
  publishFoldSignal()
  addHubLog('Fold command dispatched (Home Pose: all 0°).', 'info')
}
</script>

<style scoped>
.arm-control {
  display: flex;
  justify-content: flex-start;
  width: 100%;
}

.arm-inner {
  width: 100%;
  max-width: 504px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.arm-top-row {
  display: grid;
  grid-template-columns: 1fr 1fr 1.55fr auto;
  gap: 6px;
  align-items: stretch;
}

.trail-toggle-btn {
  background: var(--bg-item);
  border: 1px solid var(--border);
  color: var(--muted);
  border-radius: 3px;
  padding: 5px 8px;
  font-size: 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
}

.trail-toggle-btn.active {
  background: rgba(0, 240, 255, 0.12);
  border-color: #00f0ff;
  color: var(--text);
}

.neon-indicator {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #64748b;
  flex-shrink: 0;
  transition: all 0.2s;
}

.neon-indicator.on {
  background: #00f0ff;
  box-shadow: 0 0 8px #00f0ff;
}

.trail-clear-btn {
  background: var(--bg-item);
  border: 1px solid var(--border);
  color: var(--muted);
  border-radius: 3px;
  padding: 5px 10px;
  font-size: 10px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s;
}

.trail-clear-btn:hover {
  background: var(--bg-item-hover);
  color: var(--text);
  border-color: var(--border-focus);
}

.arm-folder-layout {
  display: flex;
  align-items: stretch;
  width: 100%;
}

.arm-folder-tabs {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 3px;
  flex-shrink: 0;
  width: 24px;
}

.arm-folder-tab {
  position: relative;
  z-index: 1;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 9px 3px;
  background: var(--bg-item);
  color: var(--muted);
  border: 1px solid var(--border);
  border-left: 3px solid transparent;
  border-right: none;
  border-radius: 4px 0 0 4px;
  cursor: pointer;
  opacity: 0.82;
  transition: background 0.15s, color 0.15s, border-color 0.15s, opacity 0.15s;
}

.arm-folder-tab-label {
  writing-mode: vertical-rl;
  transform: rotate(180deg);
  font-size: 9.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.7px;
  line-height: 1;
  white-space: nowrap;
  user-select: none;
}

.arm-folder-tab.active {
  z-index: 3;
  margin-right: -1px;
  background: var(--bg-main);
  color: var(--text);
  border-color: var(--border);
  border-left: 3px solid var(--accent);
  border-right: none;
  box-shadow: inset 3px 0 8px rgba(37, 99, 235, 0.16);
  opacity: 1;
}

.arm-folder-tab:hover:not(.active) {
  background: var(--bg-item-hover);
  color: var(--text);
  opacity: 1;
}

.arm-folder-body {
  position: relative;
  z-index: 2;
  box-sizing: border-box;
  flex: 1;
  min-width: 0;
  min-height: 240px;
  background: var(--bg-main);
  border: 1px solid var(--border);
  border-radius: 0 3px 3px 3px;
  padding: 7px;
}

.telemetry-card {
  padding: 6px 8px;
}

.telemetry-card .telemetry-header {
  margin-bottom: 5px;
}

.telemetry-grid {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 4px;
}

.telemetry-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
  background: var(--bg-item);
  padding: 3px 3px;
  border-radius: 3px;
  border: 1px solid var(--border-subtle);
  min-width: 0;
}

.t-lbl {
  font-size: 9px;
  font-weight: 700;
  color: var(--muted);
  line-height: 1;
}

.t-val {
  font-size: 10.5px;
  font-weight: 600;
  color: var(--text);
  line-height: 1.15;
  white-space: nowrap;
}

@media (max-width: 480px) {
  .arm-top-row {
    grid-template-columns: 1fr 1fr;
  }

  .arm-folder-tabs {
    width: 22px;
  }

  .arm-folder-body {
    padding: 5px;
  }

  .telemetry-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
