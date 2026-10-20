<template>
  <div class="block-container quick-actions-container">
    <button class="qa-toggle-btn" :class="{'nav-mode': activeTab === 'nav'}" @click="toggleTab">
      <span>{{ activeTab === 'action' ? 'ACTION' : 'NAV' }}</span>
      <div class="mini-track">
        <div class="mini-knob" :class="{'is-right': activeTab === 'nav'}"></div>
      </div>
    </button>
    
    <!-- Action Tab -->
    <div class="quick-actions-grid" v-if="activeTab === 'action'">
      <button class="unified-btn c-orange" @click="setLight(true)">
        <div class="waypoint-name">Light ON</div>
      </button>
      <button class="unified-btn c-gray" @click="setLight(false)">
        <div class="waypoint-name">Light OFF</div>
      </button>
      <button class="unified-btn c-blue" @click="mockSample">
        <div class="waypoint-name">Sampling</div>
      </button>
    </div>
    
    <!-- Nav Tab -->
    <div class="nav-tab-wrapper" v-else>
      <div class="quick-actions-grid">
        <button class="unified-btn c-red" @click="cancelNav">
          <div class="waypoint-name">CANCEL</div>
        </button>
        <button class="unified-btn c-green" @click="resumeNav" title="Resume aborted or paused route from current waypoint">
          <div class="waypoint-name">▶ RESUME</div>
        </button>
        <button class="unified-btn c-gray" @click="clearCostmaps">
          <div class="waypoint-name">CLEAR</div>
        </button>

        <!-- Laps & Queue Controls -->
        <div class="laps-box" title="Number of laps / repetitions">
          <label>LAPS</label>
          <input type="number" v-model.number="store.lapsCount" min="1" max="100" />
        </div>

        <button class="unified-btn" :class="store.queueMode ? 'c-orange' : 'c-gray'" @click="store.queueMode = !store.queueMode" title="When ON, clicking waypoints adds them to the Command Queue">
          <div class="waypoint-name">{{ store.queueMode ? 'QUEUE: ON' : 'QUEUE: OFF' }}</div>
          <div class="waypoint-coords">{{ store.queueMode ? 'Click to add' : 'Direct run' }}</div>
        </button>
        
        <button v-for="(data, name) in store.waypoints" :key="name"
                class="unified-btn" :class="data.type === 'route' ? 'c-purple' : 'c-blue'"
                @click="handleWaypointClick(name, data)">
          <div class="del-btn" @click.stop="deleteWaypoint(name)">✖</div>
          <div class="waypoint-name">{{ name.toUpperCase() }}</div>
          <div class="waypoint-coords" v-if="data.x !== undefined">{{ data.x.toFixed(1) }}, {{ data.y.toFixed(1) }}, {{ data.yaw.toFixed(1) }}</div>
          <div class="waypoint-coords" v-else-if="data.points">pts: {{ data.points.length }}</div>
        </button>
      </div>

      <!-- Command Queue Window -->
      <div v-if="store.queueMode || store.commandQueue.length > 0" class="cmd-queue-window">
        <div class="cmd-queue-header">
          <span class="cmd-queue-title">📋 Command Queue ({{ store.commandQueue.length }})</span>
          <div class="cmd-queue-actions">
            <button class="unified-btn c-green queue-btn" :disabled="store.commandQueue.length === 0" @click="runCommandQueue">
              <div class="waypoint-name">▶ RUN QUEUE</div>
            </button>
            <button class="unified-btn c-red queue-btn" :disabled="store.commandQueue.length === 0" @click="store.clearCommandQueue">
              <div class="waypoint-name">✖ CLEAR</div>
            </button>
          </div>
        </div>
        <div v-if="store.commandQueue.length === 0" class="cmd-queue-empty">
          Click any point or route button above to add it to the execution queue (with LAPS count).
        </div>
        <div v-else class="cmd-queue-list">
          <div v-for="(item, idx) in store.commandQueue" :key="item.id" class="cmd-queue-item" :class="item.type === 'route' ? 'q-route' : 'q-point'">
            <span class="q-idx">{{ idx + 1 }}.</span>
            <span class="q-name">{{ item.name.toUpperCase() }}</span>
            <div class="q-laps">
              <span>×</span>
              <input type="number" v-model.number="item.laps" min="1" max="100" class="q-laps-input" />
              <span>laps</span>
            </div>
            <button class="q-remove" @click="store.removeCommandFromQueue(idx)">✖</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { pubBool, pubSmartCommand } from '../../services/rosConnection'
import { useRosStore } from '../../stores/rosStore'

const store = useRosStore()
const activeTab = ref('action')

const toggleTab = () => {
  activeTab.value = activeTab.value === 'action' ? 'nav' : 'action'
}

const setLight = (state) => {
  store.setLightState(state)
  pubBool(state)
}

const mockSample = () => pubSmartCommand('payload', 'mock_sample')
const cancelNav = () => pubSmartCommand('nav', 'cancel', { x: 0, y: 0, yaw: 0 })
const resumeNav = () => {
  pubSmartCommand('operator', 'RESUME')
  pubSmartCommand('nav', 'resume')
}
const clearCostmaps = () => pubSmartCommand('system', 'clear_costmaps')

const handleWaypointClick = (name, data) => {
  const laps = Math.max(1, parseInt(store.lapsCount) || 1)
  if (store.queueMode) {
    store.addCommandToQueue(name, data.type || 'point', laps)
  } else {
    pubSmartCommand('nav', 'go_to_named', { name, laps })
  }
}

const runCommandQueue = () => {
  for (const item of store.commandQueue) {
    const laps = Math.max(1, parseInt(item.laps) || 1)
    pubSmartCommand('nav', 'go_to_named', { name: item.name, laps })
  }
  store.clearCommandQueue()
}

const deleteWaypoint = (name) => pubSmartCommand('waypoints', 'delete', { name })
</script>

<style scoped>
.quick-actions-container {
  margin-top: 20px; /* Space from 3D window */
  margin-bottom: 20px; /* Match Block 1 bottom margin to align perfectly */
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 15px;
  min-height: 80px; /* Made 3 times taller than previous ~28px */
}

.qa-toggle-btn {
  background: var(--accent, #1976D2);
  color: white;
  border: none;
  border-radius: 6px;
  padding: 8px 15px;
  font-weight: bold;
  font-size: 14px;
  cursor: pointer;
  min-width: 90px;
  box-shadow: 0 4px 6px rgba(0,0,0,0.3);
  transition: 0.2s;
  height: 66px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  flex-shrink: 0;
}

.qa-toggle-btn.nav-mode {
  background: #9c27b0;
}

.qa-toggle-btn:hover {
  filter: brightness(1.2);
}

.qa-toggle-btn:active {
  transform: translateY(2px);
  box-shadow: 0 2px 3px rgba(0,0,0,0.3);
}

.mini-track {
  width: 32px;
  height: 14px;
  background: rgba(0,0,0,0.3);
  border-radius: 7px;
  position: relative;
  box-shadow: inset 0 1px 3px rgba(0,0,0,0.5);
}

.mini-knob {
  width: 10px;
  height: 10px;
  background: white;
  border-radius: 50%;
  position: absolute;
  top: 2px;
  left: 2px;
  transition: left 0.3s cubic-bezier(0.4, 0.0, 0.2, 1);
  box-shadow: 0 1px 2px rgba(0,0,0,0.5);
}

.mini-knob.is-right {
  left: 20px;
}

.quick-actions-grid {
  display: flex;
  flex-wrap: wrap;
  align-content: flex-start;
  gap: 8px;
  width: 100%;
}

.nav-tab-wrapper {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.laps-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-radius: 6px;
  width: 75px;
  height: 40px;
  padding: 2px 4px;
  box-sizing: border-box;
}

.laps-box label {
  font-size: 9px;
  font-weight: bold;
  opacity: 0.8;
  margin-bottom: 1px;
}

.laps-box input {
  width: 55px;
  height: 20px;
  padding: 0 4px;
  font-size: 12px;
  font-weight: bold;
  text-align: center;
  border: none;
  background: transparent;
  color: var(--text);
}

.cmd-queue-window {
  background: rgba(0, 0, 0, 0.25);
  border: 1px dashed var(--input-border);
  border-radius: 6px;
  padding: 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cmd-queue-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.cmd-queue-title {
  font-size: 12px;
  font-weight: bold;
  color: var(--text);
}

.cmd-queue-actions {
  display: flex;
  gap: 6px;
}

.queue-btn {
  height: 28px !important;
  width: auto !important;
  padding: 0 10px !important;
}

.cmd-queue-empty {
  font-size: 11px;
  opacity: 0.7;
  padding: 4px 0;
}

.cmd-queue-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.cmd-queue-item {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--input-bg);
  border: 1px solid var(--input-border);
  border-left: 4px solid var(--accent);
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 12px;
}

.cmd-queue-item.q-route {
  border-left-color: #9c27b0;
}

.q-idx {
  opacity: 0.7;
  font-size: 11px;
}

.q-name {
  font-weight: bold;
}

.q-laps {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 11px;
  opacity: 0.9;
}

.q-laps-input {
  width: 38px !important;
  padding: 2px 4px !important;
  font-size: 11px !important;
  text-align: center;
}

.q-remove {
  background: transparent;
  border: none;
  color: var(--red);
  cursor: pointer;
  font-size: 12px;
  padding: 0 2px;
}
</style>
