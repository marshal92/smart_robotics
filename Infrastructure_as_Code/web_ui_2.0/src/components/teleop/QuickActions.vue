<template>
  <div class="dock-actions-container">
    <!-- Subsystem Actions -->
    <div class="section-group actions-group">
      <div class="group-header">ACTIONS</div>
      <div class="actions-row">
        <button 
          class="unified-btn" 
          :class="store.lightOn ? 'c-orange is-active' : 'c-gray'" 
          @click="toggleLight" 
          title="Toggle Robot Flashlight"
        >
          <div class="toggle-header-row">
            <span class="status-dot dot-orange" :class="{ 'is-on': store.lightOn }"></span>
            <div class="waypoint-name">LIGHT</div>
          </div>
          <div class="toggle-state-text">{{ store.lightOn ? 'ON' : 'OFF' }}</div>
        </button>
        <button class="unified-btn c-blue" @click="mockSample">
          <div class="waypoint-name">Sampling</div>
        </button>
      </div>
    </div>

    <div class="v-divider"></div>

    <!-- Navigation & Waypoints -->
    <div class="section-group nav-group">
      <div class="group-header">NAVIGATION & WAYPOINTS</div>
      <div class="nav-content-wrap">
        <div class="nav-buttons-row">
          <!-- Resume & Clear -->
          <button class="unified-btn c-green" @click="resumeNav" title="Resume navigation">
            <div class="waypoint-name">▶ RESUME</div>
          </button>
          <button class="unified-btn c-gray" @click="clearCostmaps" title="Clear Nav2 costmaps">
            <div class="waypoint-name">CLEAR</div>
          </button>

          <!-- LAPS -->
          <div class="laps-box" title="Number of laps / repetitions">
            <label>LAPS</label>
            <input type="number" v-model.number="store.lapsCount" min="1" max="100" />
          </div>

          <!-- Queue Mode Toggle -->
          <button class="unified-btn" :class="store.queueMode ? 'c-orange' : 'c-gray'" @click="store.queueMode = !store.queueMode" title="When ON, clicking waypoints adds them to the execution queue">
            <div class="waypoint-name">{{ store.queueMode ? 'QUEUE: ON' : 'QUEUE: OFF' }}</div>
            <div class="waypoint-coords">{{ store.queueMode ? 'Click to add' : 'Direct run' }}</div>
          </button>

          <!-- Waypoint & Route Buttons -->
          <button v-for="(data, name) in store.waypoints" :key="name"
                  class="unified-btn" :class="data.type === 'route' ? 'c-purple' : 'c-blue'"
                  @click="handleWaypointClick(name, data)">
            <div class="del-btn" @click.stop="deleteWaypoint(name)" title="Delete waypoint">✖</div>
            <div class="waypoint-name">{{ name.toUpperCase() }}</div>
            <div class="waypoint-coords" v-if="data.x !== undefined">{{ data.x.toFixed(1) }}, {{ data.y.toFixed(1) }}</div>
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
            Click any point or route button above to add it to the execution queue.
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
  </div>
</template>

<script setup>
import { pubBool, pubSmartCommand } from '../../services/rosConnection'
import { useRosStore } from '../../stores/rosStore'

const store = useRosStore()

const toggleLight = () => {
  const next = !store.lightOn
  store.setLightState(next)
  pubBool(next)
}

const mockSample = () => pubSmartCommand('payload', 'mock_sample')

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
.dock-actions-container {
  height: 100%;
  padding: 8px 12px;
  background: var(--bg-panel);
  display: flex;
  gap: 12px;
  box-sizing: border-box;
  overflow-y: auto;
  overflow-x: auto;
}

.section-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.actions-group {
  flex: 0 0 auto;
}

.nav-group {
  flex: 1 1 auto;
  min-width: 0;
}

.group-header {
  font-size: 9px;
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.actions-row, .nav-buttons-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.v-divider {
  width: 1px;
  background: var(--border);
  align-self: stretch;
  flex-shrink: 0;
  margin: 0 2px;
}

.laps-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: var(--bg-item);
  border: 1px solid var(--border);
  border-radius: 3px;
  width: 65px;
  height: 36px;
  padding: 1px 4px;
  box-sizing: border-box;
}

.laps-box label {
  font-size: 8px;
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
  margin-bottom: 1px;
}

.laps-box input {
  width: 45px;
  height: 18px;
  padding: 0 2px;
  font-size: 11px;
  font-weight: 700;
  text-align: center;
  border: none;
  background: transparent;
  color: var(--text);
  font-family: 'JetBrains Mono', monospace;
}

.cmd-queue-window {
  margin-top: 6px;
  background: var(--bg-item);
  border: 1px dashed var(--border);
  border-radius: 3px;
  padding: 6px 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.cmd-queue-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.cmd-queue-title {
  font-size: 11px;
  font-weight: 700;
  color: var(--text);
}

.cmd-queue-actions {
  display: flex;
  gap: 6px;
}

.queue-btn {
  height: 24px !important;
  width: auto !important;
  padding: 0 8px !important;
}

.cmd-queue-empty {
  font-size: 10px;
  color: var(--muted);
  padding: 2px 0;
}

.cmd-queue-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.cmd-queue-item {
  display: flex;
  align-items: center;
  gap: 5px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-left: 3px solid var(--accent);
  border-radius: 3px;
  padding: 3px 6px;
  font-size: 11px;
}

.cmd-queue-item.q-route {
  border-left-color: var(--purple);
}

.q-idx {
  color: var(--muted);
  font-size: 10px;
}

.q-name {
  font-weight: 700;
}

.q-laps {
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 10px;
  color: var(--muted);
}

.q-laps-input {
  width: 32px !important;
  padding: 1px 3px !important;
  font-size: 10px !important;
  text-align: center;
}

.q-remove {
  background: transparent;
  border: none;
  color: var(--red);
  cursor: pointer;
  font-size: 11px;
  padding: 0 2px;
}

.toggle-header-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
}

.toggle-state-text {
  font-size: 10px;
  font-weight: 600;
  color: var(--muted);
  line-height: 1;
  letter-spacing: 0.5px;
  margin-top: 2px;
}

.unified-btn.is-active .toggle-state-text {
  color: var(--text);
  font-weight: 700;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--muted);
  opacity: 0.35;
  transition: all 0.2s ease;
  display: inline-block;
  flex-shrink: 0;
}

.status-dot.dot-orange.is-on {
  background: var(--orange);
  opacity: 1;
  box-shadow: 0 0 6px var(--orange);
}
</style>
