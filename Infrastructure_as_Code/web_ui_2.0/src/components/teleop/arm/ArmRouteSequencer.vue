<template>
  <div class="teleop-card route-card">
    <div class="telemetry-header route-header">
      <span>JOINT ROUTE SEQUENCER</span>
      <span class="live-badge" :class="{ active: routeExecuting }">
        {{ routeExecuting ? `STEP ${routeActiveIndex + 1}/${routeSteps.length}` : `${routeSteps.length} PTS` }}
      </span>
    </div>

    <!-- Single-Row Action Bar -->
    <div class="route-actions-row">
      <button
        class="cmd-btn border-btn b-blue compact-btn route-act-btn"
        @click="addCurrentRobotStep"
        :disabled="routeExecuting"
        title="Capture current robot joint angles and add to route"
      >
        + ROBOT
      </button>
      <button
        class="cmd-btn border-btn b-red compact-btn route-act-btn"
        @click="clearRouteSteps"
        :disabled="routeExecuting || routeSteps.length === 0"
        title="Clear all route steps"
      >
        CLEAR
      </button>
      <label class="route-loop-toggle" title="Repeat route continuously">
        <input type="checkbox" v-model="routeLoop" />
        <span>LOOP</span>
      </label>
      <button
        class="cmd-btn border-btn b-blue compact-btn route-act-btn route-run-btn"
        @click="runJointRoute"
        :disabled="routeExecuting || routeSteps.length === 0"
      >
        {{ routeExecuting ? `⏳ ${routeStatusText}` : '▶ RUN' }}
      </button>
      <button
        class="cmd-btn border-btn b-red compact-btn route-act-btn"
        @click="stopJointRoute(true)"
        :disabled="!routeExecuting"
      >
        ⏹ STOP
      </button>
    </div>

    <!-- Route Steps List -->
    <div v-if="routeSteps.length === 0" class="route-empty">
      No points yet. Position the arm with MANUAL controls above and click "+ ROBOT".
    </div>
    <div v-else class="route-list">
      <div
        v-for="(step, idx) in routeSteps"
        :key="step.id"
        class="route-step-row"
        :class="{ executing: routeExecuting && routeActiveIndex === idx }"
      >
        <span class="route-step-idx mono">{{ idx + 1 }}.</span>
        <input
          type="text"
          v-model="step.name"
          @change="persistActiveRoute"
          class="route-step-name-input"
          :disabled="routeExecuting"
          :title="formatStepTooltip(step)"
        />
        <div class="route-num-wrap" title="Move duration (s)">
          <input
            type="number"
            v-model.number="step.duration"
            @change="persistActiveRoute"
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
            @change="persistActiveRoute"
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

    <!-- Save / Load Route Preset Row -->
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
          <span class="select-ellipsis">{{ selectedRouteIndex === -1 ? '-- Load Route --' : savedRoutes[selectedRouteIndex]?.name }}</span>
          <span style="font-size: 9px;">▼</span>
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
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ARM_JOINT_LIMITS, useArmRos } from './useArmRos'

const emit = defineEmits(['before-run'])

const {
  store,
  currentJointAnglesRad,
  hubExecuting,
  publishJointPositionsDeg,
  resetHubTask,
  addHubLog,
  registerStopCallback
} = useArmRos()

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

const closeDropdown = () => {
  routeDropdownOpen.value = false
}

const persistActiveRoute = () => {
  localStorage.setItem('arm_active_route', JSON.stringify(routeSteps.value))
}

const snapshotRobotDeg = () => {
  const degArray = []
  for (let i = 0; i < 6; i++) {
    let deg = ((currentJointAnglesRad.value[i] || 0) * 180.0) / Math.PI
    if (deg > ARM_JOINT_LIMITS[i].max) deg = ARM_JOINT_LIMITS[i].max
    if (deg < ARM_JOINT_LIMITS[i].min) deg = ARM_JOINT_LIMITS[i].min
    degArray.push(Math.round(deg * 10) / 10)
  }
  return degArray
}

const formatStepTooltip = (step) => {
  if (!step || !Array.isArray(step.deg)) return ''
  return `Joints (°): [${step.deg.map((v) => Number(v).toFixed(1)).join(', ')}]`
}

const addCurrentRobotStep = () => {
  const deg = snapshotRobotDeg()
  const name = `WP ${routeSteps.value.length + 1}`
  routeSteps.value.push({
    id: Date.now() + Math.random(),
    name,
    deg,
    duration: 2.0,
    pause: 0.3
  })
  persistActiveRoute()
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
  emit('before-run')
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

        const dur = Math.max(0.3, Number(step.duration) || 2.0)
        const pause = Math.max(0.0, Number(step.pause) || 0.0)
        routeStatusText.value = `${i + 1}/${routeSteps.value.length}`
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

onMounted(() => {
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
  window.addEventListener('click', closeDropdown)
})

onBeforeUnmount(() => {
  window.removeEventListener('click', closeDropdown)
  unregisterStop?.()
  stopJointRoute(false)
})

defineExpose({
  stopJointRoute
})
</script>

<style scoped>
.route-card {
  gap: 6px;
  padding: 8px 10px;
}

.route-header {
  margin-bottom: 4px;
}

.route-actions-row {
  display: grid;
  grid-template-columns: auto auto auto 1fr auto;
  gap: 4px;
  align-items: center;
}

.route-act-btn {
  padding: 4px 7px !important;
  font-size: 10px !important;
  min-height: 26px;
  white-space: nowrap;
}

.route-run-btn {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}

.route-loop-toggle {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 9.5px;
  font-weight: 700;
  color: var(--muted);
  cursor: pointer;
  user-select: none;
  padding: 0 3px;
  white-space: nowrap;
}

.route-loop-toggle input {
  width: 12px;
  height: 12px;
  accent-color: var(--accent);
  margin: 0;
}

.route-empty {
  font-size: 10px;
  color: var(--muted);
  padding: 6px;
  text-align: center;
  background: var(--bg-item);
  border: 1px dashed var(--border-subtle);
  border-radius: 3px;
}

.route-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
  max-height: 145px;
  overflow-y: auto;
}

.route-step-row {
  display: flex;
  align-items: center;
  gap: 5px;
  background: var(--bg-item);
  border: 1px solid var(--border-subtle);
  border-radius: 3px;
  padding: 3px 5px;
}

.route-step-row.executing {
  border-color: var(--accent);
  background: rgba(59, 130, 246, 0.14);
}

.route-step-idx {
  font-size: 10px;
  color: var(--muted);
  width: 16px;
  flex-shrink: 0;
}

.route-step-name-input {
  flex: 1;
  min-width: 0;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 2px;
  color: var(--text);
  font-size: 10.5px;
  font-weight: 600;
  padding: 1px 3px;
}

.route-step-name-input:focus {
  outline: none;
  background: var(--bg-panel);
  border-color: var(--accent);
}

.route-num-wrap {
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 9.5px;
  color: var(--muted);
}

.route-num-input {
  width: 30px;
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
  width: 19px;
  height: 19px;
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
  grid-template-columns: 1fr 52px 1fr;
  gap: 5px;
  align-items: center;
}

.custom-select-wrapper {
  position: relative;
  width: 100%;
  min-width: 0;
}

.custom-select-box {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  user-select: none;
}

.select-ellipsis {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.custom-select-list {
  position: absolute;
  bottom: 100%;
  left: 0;
  right: 0;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 4px;
  max-height: 140px;
  overflow-y: auto;
  z-index: 1000;
  margin-bottom: 2px;
  box-shadow: 0 -4px 8px rgba(0, 0, 0, 0.35);
}

.custom-select-item {
  padding: 5px 8px;
  font-size: 11px;
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
  padding: 2px 5px;
  border-radius: 3px;
}

.del-icon:hover {
  background: rgba(255, 0, 0, 0.2);
}
</style>
