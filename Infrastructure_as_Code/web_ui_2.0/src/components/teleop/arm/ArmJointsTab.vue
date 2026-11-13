<template>
  <div class="subtab-pane">
    <div class="joint-list">
      <div v-for="(limit, index) in ARM_JOINT_LIMITS" :key="index" class="joint-row">
        <span class="joint-lbl">J{{ index }}</span>

        <button class="unified-btn arm-step-btn" @click="stepJoint(index, -5)">
          <div>-</div>
        </button>

        <input
          type="range"
          :min="limit.min"
          :max="limit.max"
          step="0.5"
          v-model.number="targetJointAnglesDeg[index]"
          class="compact-slider"
        />

        <button class="unified-btn arm-step-btn" @click="stepJoint(index, 5)">
          <div>+</div>
        </button>

        <input
          type="number"
          class="joint-val-input"
          v-model.number="targetJointAnglesDeg[index]"
          step="0.5"
          :min="limit.min"
          :max="limit.max"
        />
        <span style="font-size: 10px; color: var(--text-muted);">°</span>
      </div>
    </div>

    <div class="custom-pose-grid">
      <input type="text" v-model="newPoseName" placeholder="Pose name..." class="map-input compact-input" />
      <button class="cmd-btn compact-btn" @click="syncSlidersToRobot">SYNC</button>
      <button class="cmd-btn compact-btn" @click="savePose">SAVE</button>

      <div class="custom-select-wrapper">
        <div class="map-input compact-input custom-select-box" @click.stop="dropdownOpen = !dropdownOpen">
          <span>{{ selectedPoseIndex === -1 ? '-- Select Saved Pose --' : savedPoses[selectedPoseIndex]?.name }}</span>
          <span style="font-size: 10px;">▼</span>
        </div>
        <div class="custom-select-list" v-if="dropdownOpen">
          <div class="custom-select-item" @click="selectPose(-1)">-- Select Saved Pose --</div>
          <div class="custom-select-item" v-for="(pose, idx) in savedPoses" :key="idx" @click="selectPose(idx)">
            <span>{{ pose.name }}</span>
            <span class="del-icon" @click.stop="deletePoseIdx(idx)">✖</span>
          </div>
        </div>
      </div>

      <div class="time-wrap">
        <input
          type="number"
          v-model.number="executeDuration"
          step="0.5"
          min="0.5"
          class="map-input compact-input time-input no-arrows"
        />
        <span class="time-s">s</span>
      </div>

      <button class="cmd-btn compact-btn" @click="executeJoints(false)">RUN</button>
    </div>

    <!-- Joint Route Builder & Sequential Executor -->
    <div class="teleop-card route-card">
      <div class="telemetry-header">
        <span>JOINT ROUTE SEQUENCER</span>
        <span class="live-badge" :class="{ active: routeExecuting }">
          {{ routeExecuting ? `STEP ${routeActiveIndex + 1}/${routeSteps.length}` : `${routeSteps.length} PTS` }}
        </span>
      </div>

      <div class="route-add-row">
        <button
          class="cmd-btn border-btn b-blue compact-btn"
          @click="addStepToRoute"
          :disabled="routeExecuting"
          title="Add current slider angles (or selected pose) to route"
        >
          + ADD TO ROUTE
        </button>
        <button
          class="cmd-btn compact-btn"
          @click="syncAndAddStepToRoute"
          :disabled="routeExecuting"
          title="Sync from robot and add current position"
        >
          + FROM ROBOT
        </button>
        <button
          class="cmd-btn border-btn b-red compact-btn"
          @click="clearRouteSteps"
          :disabled="routeExecuting || routeSteps.length === 0"
        >
          CLEAR
        </button>
      </div>

      <div v-if="routeSteps.length === 0" class="route-empty">
        No points in route. Adjust sliders or select a saved pose, then click "+ ADD TO ROUTE".
      </div>
      <div v-else class="route-list">
        <div
          v-for="(step, idx) in routeSteps"
          :key="step.id"
          class="route-step-row"
          :class="{ executing: routeExecuting && routeActiveIndex === idx }"
        >
          <span class="route-step-idx mono">{{ idx + 1 }}.</span>
          <button class="route-step-name" @click="loadStepToSliders(step)" title="Load angles to sliders">
            {{ step.name }}
          </button>
          <div class="route-num-wrap" title="Move duration (s)">
            <input
              type="number"
              v-model.number="step.duration"
              step="0.5"
              min="0.3"
              class="route-num-input no-arrows"
              :disabled="routeExecuting"
            />
            <span>s</span>
          </div>
          <div class="route-num-wrap" title="Pause after point (s)">
            <input
              type="number"
              v-model.number="step.pause"
              step="0.2"
              min="0"
              class="route-num-input no-arrows"
              :disabled="routeExecuting"
            />
            <span>w</span>
          </div>
          <div class="route-step-actions">
            <button class="route-mini-btn" @click="moveRouteStep(idx, -1)" :disabled="routeExecuting || idx === 0">▲</button>
            <button class="route-mini-btn" @click="moveRouteStep(idx, 1)" :disabled="routeExecuting || idx === routeSteps.length - 1">▼</button>
            <button class="route-mini-btn del" @click="removeRouteStep(idx)" :disabled="routeExecuting">✖</button>
          </div>
        </div>
      </div>

      <div class="route-save-row">
        <input
          type="text"
          v-model="newRouteName"
          placeholder="Route name..."
          class="map-input compact-input"
          :disabled="routeExecuting"
        />
        <button class="cmd-btn compact-btn" @click="saveRoute" :disabled="routeExecuting || routeSteps.length === 0">
          SAVE
        </button>
        <div class="custom-select-wrapper">
          <div class="map-input compact-input custom-select-box" @click.stop="routeDropdownOpen = !routeDropdownOpen">
            <span>{{ selectedRouteIndex === -1 ? '-- Load Route --' : savedRoutes[selectedRouteIndex]?.name }}</span>
            <span style="font-size: 10px;">▼</span>
          </div>
          <div class="custom-select-list" v-if="routeDropdownOpen">
            <div class="custom-select-item" @click="selectRoute(-1)">-- Load Route --</div>
            <div class="custom-select-item" v-for="(rt, rIdx) in savedRoutes" :key="rIdx" @click="selectRoute(rIdx)">
              <span>{{ rt.name }} ({{ rt.steps?.length || 0 }})</span>
              <span class="del-icon" @click.stop="deleteRouteIdx(rIdx)">✖</span>
            </div>
          </div>
        </div>
      </div>

      <div class="route-exec-row">
        <label class="route-loop-toggle">
          <input type="checkbox" v-model="routeLoop" />
          <span>LOOP</span>
        </label>
        <button
          class="cmd-btn border-btn b-blue compact-btn"
          @click="runJointRoute"
          :disabled="routeExecuting || routeSteps.length === 0"
        >
          {{ routeExecuting ? `⏳ ${routeStatusText}` : '▶ RUN ROUTE' }}
        </button>
        <button
          class="cmd-btn border-btn b-red compact-btn"
          @click="stopJointRoute(true)"
          :disabled="!routeExecuting"
        >
          ⏹ STOP
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ARM_JOINT_LIMITS, useArmRos } from './useArmRos'

const {
  store,
  currentJointAnglesRad,
  hubExecuting,
  publishJointPositionsDeg,
  resetHubTask,
  addHubLog,
  registerStopCallback
} = useArmRos()

const targetJointAnglesDeg = ref([0, 0, 0, 0, 0, 0])
const executeDuration = ref(3.0)
const newPoseName = ref('')
const selectedPoseIndex = ref(-1)
const savedPoses = ref([])
const dropdownOpen = ref(false)

const routeSteps = ref([])
const savedRoutes = ref([])
const newRouteName = ref('')
const selectedRouteIndex = ref(-1)
const routeDropdownOpen = ref(false)
const routeExecuting = ref(false)
const routeActiveIndex = ref(-1)
const routeLoop = ref(false)
const routeStatusText = ref('Idle')
let routeStopRequested = false
let unregisterStop = null

const closeDropdowns = () => {
  dropdownOpen.value = false
  routeDropdownOpen.value = false
}

const setTargetAnglesDeg = (degArray) => {
  for (let i = 0; i < 6; i++) {
    targetJointAnglesDeg.value[i] = Number(degArray[i]) || 0
  }
}

const syncSlidersToRobot = () => {
  for (let i = 0; i < 6; i++) {
    let deg = (currentJointAnglesRad.value[i] * 180.0) / Math.PI
    if (deg > ARM_JOINT_LIMITS[i].max) deg = ARM_JOINT_LIMITS[i].max
    if (deg < ARM_JOINT_LIMITS[i].min) deg = ARM_JOINT_LIMITS[i].min
    targetJointAnglesDeg.value[i] = Math.round(deg * 10) / 10
  }
}

const executeJoints = (isImmediate = false, immediateDuration = 0.5) => {
  const d = isImmediate ? immediateDuration : executeDuration.value
  const safeD = Number.isFinite(Number(d)) && Number(d) >= 0.2 ? Number(d) : 3.0
  publishJointPositionsDeg(targetJointAnglesDeg.value, safeD)
}

const stepJoint = (index, degStep) => {
  for (let i = 0; i < 6; i++) {
    const deg = (currentJointAnglesRad.value[i] * 180.0) / Math.PI
    targetJointAnglesDeg.value[i] = Math.round(deg * 10) / 10
  }

  let targetDeg = targetJointAnglesDeg.value[index] + degStep
  if (targetDeg > ARM_JOINT_LIMITS[index].max) targetDeg = ARM_JOINT_LIMITS[index].max
  if (targetDeg < ARM_JOINT_LIMITS[index].min) targetDeg = ARM_JOINT_LIMITS[index].min

  targetJointAnglesDeg.value[index] = Math.round(targetDeg * 10) / 10
  executeJoints(true, 0.5)
}

const persistActiveRoute = () => {
  localStorage.setItem('arm_active_route', JSON.stringify(routeSteps.value))
}

const getStepDuration = () => {
  const d = Number(executeDuration.value)
  return Number.isFinite(d) && d >= 0.3 ? d : 2.0
}

const addStepToRoute = () => {
  let name = newPoseName.value.trim()
  if (!name && selectedPoseIndex.value !== -1 && savedPoses.value[selectedPoseIndex.value]) {
    name = savedPoses.value[selectedPoseIndex.value].name
  }
  if (!name) {
    name = `WP ${routeSteps.value.length + 1}`
  }
  routeSteps.value.push({
    id: Date.now() + Math.random(),
    name,
    deg: [...targetJointAnglesDeg.value],
    duration: getStepDuration(),
    pause: 0.3
  })
  persistActiveRoute()
}

const syncAndAddStepToRoute = () => {
  syncSlidersToRobot()
  const name = newPoseName.value.trim() || `WP ${routeSteps.value.length + 1}`
  routeSteps.value.push({
    id: Date.now() + Math.random(),
    name,
    deg: [...targetJointAnglesDeg.value],
    duration: getStepDuration(),
    pause: 0.3
  })
  persistActiveRoute()
}

const loadStepToSliders = (step) => {
  if (!step || !Array.isArray(step.deg)) return
  setTargetAnglesDeg(step.deg)
}

const moveRouteStep = (idx, dir) => {
  const next = idx + dir
  if (next < 0 || next >= routeSteps.value.length) return
  const arr = [...routeSteps.value]
  const tmp = arr[idx]
  arr[idx] = arr[next]
  arr[next] = tmp
  routeSteps.value = arr
  persistActiveRoute()
}

const removeRouteStep = (idx) => {
  routeSteps.value.splice(idx, 1)
  persistActiveRoute()
}

const clearRouteSteps = () => {
  routeSteps.value = []
  persistActiveRoute()
}

const saveRoute = () => {
  if (routeSteps.value.length === 0) return
  let name = newRouteName.value.trim()
  if (!name) {
    name = `Route ${savedRoutes.value.length + 1}`
  }
  const clonedSteps = routeSteps.value.map((s) => ({
    id: Date.now() + Math.random(),
    name: s.name,
    deg: [...s.deg],
    duration: Number(s.duration) || 2.0,
    pause: Number.isFinite(Number(s.pause)) ? Number(s.pause) : 0.3
  }))
  savedRoutes.value.push({ name, steps: clonedSteps })
  localStorage.setItem('arm_saved_routes', JSON.stringify(savedRoutes.value))
  newRouteName.value = ''
  selectedRouteIndex.value = savedRoutes.value.length - 1
}

const selectRoute = (idx) => {
  selectedRouteIndex.value = idx
  routeDropdownOpen.value = false
  if (idx === -1 || !savedRoutes.value[idx]) return
  routeSteps.value = (savedRoutes.value[idx].steps || []).map((s) => ({
    id: Date.now() + Math.random(),
    name: s.name,
    deg: [...s.deg],
    duration: Number(s.duration) || 2.0,
    pause: Number.isFinite(Number(s.pause)) ? Number(s.pause) : 0.3
  }))
  persistActiveRoute()
}

const deleteRouteIdx = (idx) => {
  savedRoutes.value.splice(idx, 1)
  localStorage.setItem('arm_saved_routes', JSON.stringify(savedRoutes.value))
  if (selectedRouteIndex.value === idx) {
    selectedRouteIndex.value = -1
  } else if (selectedRouteIndex.value > idx) {
    selectedRouteIndex.value--
  }
}

const waitCancelableMs = async (ms) => {
  const stepMs = 50
  let elapsed = 0
  while (elapsed < ms) {
    if (routeStopRequested) return false
    const chunk = Math.min(stepMs, ms - elapsed)
    await new Promise((resolve) => setTimeout(resolve, chunk))
    elapsed += chunk
  }
  return !routeStopRequested
}

const runJointRoute = async () => {
  if (!store.isConnected || routeExecuting.value || routeSteps.value.length === 0) return
  if (hubExecuting.value) resetHubTask()
  persistActiveRoute()

  routeStopRequested = false
  routeExecuting.value = true
  addHubLog(`Starting Joint Route (${routeSteps.value.length} points${routeLoop.value ? ', LOOP' : ''})...`, 'info')

  try {
    do {
      for (let i = 0; i < routeSteps.value.length; i++) {
        if (routeStopRequested) break
        const step = routeSteps.value[i]
        routeActiveIndex.value = i
        loadStepToSliders(step)

        const dur = Math.max(0.3, Number(step.duration) || 2.0)
        const pause = Math.max(0.0, Number(step.pause) || 0.0)
        routeStatusText.value = `${i + 1}/${routeSteps.value.length}: ${step.name}`
        publishJointPositionsDeg(step.deg, dur)

        const okMove = await waitCancelableMs(dur * 1000)
        if (!okMove) break

        if (pause > 0) {
          routeStatusText.value = `WAIT ${i + 1}/${routeSteps.value.length}`
          const okPause = await waitCancelableMs(pause * 1000)
          if (!okPause) break
        }
      }
    } while (routeLoop.value && !routeStopRequested && routeSteps.value.length > 0)

    if (!routeStopRequested) {
      addHubLog('Joint Route completed.', 'success')
    }
  } finally {
    routeExecuting.value = false
    routeActiveIndex.value = -1
    routeStatusText.value = 'Idle'
  }
}

const stopJointRoute = (holdCurrent = true) => {
  const wasRunning = routeExecuting.value
  routeStopRequested = true
  routeExecuting.value = false
  routeActiveIndex.value = -1
  routeStatusText.value = 'Idle'
  if (wasRunning && holdCurrent && store.isConnected) {
    const currDeg = currentJointAnglesRad.value.map((r) => (r * 180.0) / Math.PI)
    publishJointPositionsDeg(currDeg, 0.1)
  }
  if (wasRunning) {
    addHubLog('Joint Route stopped by user.', 'warning')
  }
}

const savePose = () => {
  let name = newPoseName.value.trim()
  if (!name) {
    name = 'Pose ' + (savedPoses.value.length + 1)
  }
  savedPoses.value.push({
    name,
    deg: [...targetJointAnglesDeg.value]
  })
  localStorage.setItem('arm_saved_poses', JSON.stringify(savedPoses.value))
  newPoseName.value = ''
  selectedPoseIndex.value = savedPoses.value.length - 1
}

const selectPose = (idx) => {
  selectedPoseIndex.value = idx
  dropdownOpen.value = false
  if (idx === -1 || !savedPoses.value[idx]) return
  setTargetAnglesDeg(savedPoses.value[idx].deg)
}

const deletePoseIdx = (idx) => {
  savedPoses.value.splice(idx, 1)
  localStorage.setItem('arm_saved_poses', JSON.stringify(savedPoses.value))
  if (selectedPoseIndex.value === idx) {
    selectedPoseIndex.value = -1
  } else if (selectedPoseIndex.value > idx) {
    selectedPoseIndex.value--
  }
}

onMounted(() => {
  const saved = localStorage.getItem('arm_saved_poses')
  if (saved) {
    try {
      savedPoses.value = JSON.parse(saved)
    } catch (e) {
      console.error('Failed to parse saved poses', e)
    }
  }
  const storedRoutes = localStorage.getItem('arm_saved_routes')
  if (storedRoutes) {
    try {
      savedRoutes.value = JSON.parse(storedRoutes)
    } catch (e) {
      console.error('Failed to parse saved routes', e)
    }
  }
  const activeRouteJson = localStorage.getItem('arm_active_route')
  if (activeRouteJson) {
    try {
      routeSteps.value = JSON.parse(activeRouteJson)
    } catch (e) {
      console.error('Failed to parse active route', e)
    }
  }
  unregisterStop = registerStopCallback(() => stopJointRoute(false))
  window.addEventListener('click', closeDropdowns)
})

onBeforeUnmount(() => {
  window.removeEventListener('click', closeDropdowns)
  unregisterStop?.()
  stopJointRoute(false)
})

defineExpose({
  setTargetAnglesDeg,
  stopJointRoute
})
</script>

<style scoped>
.joint-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.joint-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.joint-lbl {
  font-weight: bold;
  color: var(--accent);
  width: 18px;
  font-size: 0.85em;
}

.arm-step-btn {
  width: 24px !important;
  height: 24px !important;
  min-height: 24px !important;
  padding: 0 !important;
  font-size: 0.9em;
  font-weight: bold;
  border-radius: 4px;
}

.joint-val-input {
  width: 45px;
  text-align: center;
  font-family: monospace;
  font-size: 0.85em;
  padding: 2px 4px;
  background: transparent;
  border: 1px solid var(--input-border);
  color: var(--text);
  border-radius: 4px;
  -moz-appearance: textfield;
}

.joint-val-input::-webkit-outer-spin-button,
.joint-val-input::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}

.custom-pose-grid {
  display: grid;
  grid-template-columns: 1fr 65px 65px;
  gap: 8px;
  align-items: center;
}

.time-wrap {
  position: relative;
  display: flex;
  align-items: center;
}

.time-input {
  width: 100%;
  text-align: center;
  background: transparent !important;
  padding-right: 15px !important;
}

.time-s {
  position: absolute;
  right: 8px;
  color: var(--text-muted);
  font-size: 10px;
  pointer-events: none;
}

.custom-select-wrapper {
  position: relative;
  width: 100%;
}

.custom-select-box {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  user-select: none;
}

.custom-select-list {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: var(--dark-bg);
  border: 1px solid var(--input-border);
  border-radius: 4px;
  max-height: 150px;
  overflow-y: auto;
  z-index: 1000;
  margin-top: 2px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
}

.custom-select-item {
  padding: 6px 10px;
  font-size: 12px;
  color: var(--text);
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.custom-select-item:hover {
  background: var(--bg-item-hover);
}

.del-icon {
  color: var(--red);
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
}

.del-icon:hover {
  background: rgba(255, 0, 0, 0.2);
}

.route-card {
  gap: 8px;
}

.route-add-row {
  display: grid;
  grid-template-columns: 1fr 1fr 68px;
  gap: 6px;
}

.route-empty {
  font-size: 11px;
  color: var(--muted);
  padding: 8px;
  text-align: center;
  background: var(--bg-item);
  border: 1px dashed var(--border-subtle);
  border-radius: 3px;
}

.route-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 170px;
  overflow-y: auto;
}

.route-step-row {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--bg-item);
  border: 1px solid var(--border-subtle);
  border-radius: 3px;
  padding: 4px 6px;
}

.route-step-row.executing {
  border-color: var(--accent);
  background: rgba(59, 130, 246, 0.14);
}

.route-step-idx {
  font-size: 10px;
  color: var(--muted);
  width: 18px;
  flex-shrink: 0;
}

.route-step-name {
  flex: 1;
  min-width: 0;
  text-align: left;
  background: transparent;
  border: none;
  color: var(--text);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 0;
}

.route-step-name:hover {
  color: var(--accent);
}

.route-num-wrap {
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 10px;
  color: var(--muted);
}

.route-num-input {
  width: 34px;
  text-align: center;
  font-family: monospace;
  font-size: 10px;
  padding: 2px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 3px;
  color: var(--text);
}

.route-step-actions {
  display: flex;
  gap: 2px;
}

.route-mini-btn {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  color: var(--muted);
  border-radius: 3px;
  font-size: 9px;
  width: 20px;
  height: 20px;
  padding: 0;
  cursor: pointer;
}

.route-mini-btn:hover:not(:disabled) {
  color: var(--text);
  border-color: var(--border-focus);
}

.route-mini-btn.del:hover:not(:disabled) {
  color: var(--red);
  border-color: var(--red);
}

.route-mini-btn:disabled {
  opacity: 0.35;
  cursor: default;
}

.route-save-row {
  display: grid;
  grid-template-columns: 1fr 60px 1fr;
  gap: 6px;
  align-items: center;
}

.route-exec-row {
  display: grid;
  grid-template-columns: 64px 1fr 78px;
  gap: 6px;
  align-items: center;
}

.route-loop-toggle {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  font-weight: 700;
  color: var(--muted);
  cursor: pointer;
  user-select: none;
}
</style>
