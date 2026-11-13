<template>
  <div class="block-container teleop-tabs-container">
    <div class="tabs">
      <button class="tab-btn" :class="{ active: activeTab === 'manager' }" @click="setTab('manager')">Manager</button>
      <button class="tab-btn" :class="{ active: activeTab === 'base' }" @click="setTab('base')">Teleop</button>
      <button class="tab-btn" :class="{ active: activeTab === 'arm' }" @click="setTab('arm')">Arm</button>
      <button class="tab-btn" :class="{ active: activeTab === 'radiation' }" @click="setTab('radiation')">Radiation</button>
    </div>

    <!-- Tab 1: Manager -->
    <div v-show="activeTab === 'manager'" class="tab-content active">
      <div class="mission-groups">
        
        <!-- Core Controls (No heading) -->
        <div class="small-grid" style="margin-bottom: 25px;">
          <button class="cmd-btn c-red" @click="pubSys('stop')">TERMINATE <span>Kill Nav/SLAM</span></button>
          <button class="cmd-btn border-btn b-orange" @click="pubOperator('RESUME')">RESUME <span>Unlock system</span></button>
          <button class="cmd-btn border-btn b-orange" @click="pubSmartCommand('nav', 'recover_localization')">Recovery <span>Recover 213</span></button>
        </div>

        <!-- Group 2: Maps & Scenarios -->
        <div class="mission-group">
          <h4 class="group-title">Maps & Scenarios</h4>
          
          <!-- Scenario Modes (Above Load Map) -->
          <div class="scenario-modes-grid">
            <button class="cmd-btn border-btn b-blue" @click="pubSys('start_freeride')">Freeride <span>Manual mode</span></button>
            <button class="cmd-btn border-btn b-purple" @click="pubSys('start:mapping:none')">GTO Mapping <span>Create clean map</span></button>
          </div>

          <!-- Dropdown Map Selector + Load Button -->
          <div class="scenario-selector-row">
            <select v-model="selectedScenarioMap" class="scenario-select" :style="{ flex: selectedScenarioMap === 'custom' ? '0 0 140px' : '1' }">
              <option value="start_213">Room 213</option>
              <option value="start_kitchen">Kitchen</option>
              <option value="start_shelter_zero">Shelter Zero</option>
              <option value="custom">Custom Map...</option>
            </select>
            <input 
              v-if="selectedScenarioMap === 'custom'" 
              type="text" 
              v-model="customMapNameLoad" 
              placeholder="Custom map name" 
              class="scenario-input" 
              @keyup.enter="loadSelectedScenario" 
            />
            <button class="cmd-btn border-btn b-blue scenario-action-btn" @click="loadSelectedScenario">
              Load Map
            </button>
          </div>

          <!-- Save Map Row (Styled identically to Load Map) -->
          <div class="scenario-selector-row">
            <input 
              type="text" 
              v-model="mapNameSave" 
              placeholder="Map name to save" 
              class="scenario-input" 
              @keyup.enter="saveCustomMap" 
            />
            <button class="cmd-btn border-btn b-blue scenario-action-btn" @click="saveCustomMap">
              Save Map
            </button>
          </div>
        </div>

        <!-- Group 3: Tools & Safety -->
        <div class="mission-group">
          <h4 class="group-title">Tools & Safety</h4>
          <div class="small-grid">
            <button 
              class="cmd-btn toggle-btn" 
              :class="isWatchdogActive ? 'b-green is-active' : 'b-muted'" 
              @click="toggleWatchdog"
              title="Toggle Safety Watchdog (Heartbeat Monitor)"
            >
              <div class="toggle-header-row">
                <span class="status-dot dot-green" :class="{ 'is-on': isWatchdogActive }"></span>
                <span class="toggle-title">WATCHDOG</span>
              </div>
              <span class="toggle-state-text">{{ isWatchdogActive ? 'ON' : 'OFF' }}</span>
            </button>
          </div>
        </div>



      </div>
    </div>

    <!-- Tab 3: Radiation -->
    <div v-show="activeTab === 'radiation'" class="tab-content active">
      <div class="mission-groups">
        <div class="mission-group">
          <h4 class="group-title">System & Sensor</h4>
          <div class="small-grid">
            <button class="cmd-btn border-btn b-orange" @click="pubSys('rad_on')">Rad Map ON <span>Enable radiation field</span></button>
            <button class="cmd-btn border-btn b-red" @click="pubSys('rad_off')">Rad Map OFF <span>Disable radiation field</span></button>
            <button 
              class="cmd-btn toggle-btn" 
              :class="isVirtGeigerActive ? 'b-orange is-active' : 'b-muted'" 
              @click="toggleVirtGeiger"
              title="Toggle Virtual Geiger Counter (Simulated Dosimeter)"
            >
              <div class="toggle-header-row">
                <span class="status-dot dot-orange" :class="{ 'is-on': isVirtGeigerActive }"></span>
                <span class="toggle-title">VIRT GEIGER</span>
              </div>
              <span class="toggle-state-text">{{ isVirtGeigerActive ? 'ON' : 'OFF' }}</span>
            </button>
          </div>
        </div>
        <div class="mission-group">
          <h4 class="group-title">Mapping Mode</h4>
          <div class="small-grid">
            <button class="cmd-btn border-btn b-orange" @click="pubSys('rad_record:explored_map.npy')">Rad Record <span>explored_map.npy</span></button>
            <button class="cmd-btn border-btn b-red" @click="pubSys('rad_stop')">Rad Stop <span>Stop & save rec</span></button>
            <button class="cmd-btn border-btn b-blue" @click="pubSys('rad_save')">Rad Save <span>Save to disk</span></button>
            <button class="cmd-btn border-btn b-red" @click="pubSys('rad_clear')">Rad Clear <span>Clear memory</span></button>
          </div>
        </div>
        <div class="mission-group">
          <h4 class="group-title">Load Map</h4>
          <div class="scenario-selector-row">
            <select v-model="selectedRadMap" class="scenario-select">
              <option value="radiation_map.npy">Radiation Map</option>
              <option value="radiation_test_1.npy">Radiation Test 1</option>
              <option value="radiation_map_complex.npy">Radiation Map Complex</option>
            </select>
            <button class="cmd-btn border-btn b-blue scenario-action-btn" @click="loadSelectedRadMap">
              Load Map
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Tab 2: Direct Teleop (Base & Shadow) -->
    <div v-show="activeTab === 'base'" class="tab-content active">
      <div class="teleop-layout-vertical">
        <div class="camera-container">
          <CameraStream />
        </div>
        <div class="controls-frame">
          <div style="position: relative;">
            <button class="mode-toggle-btn" @click="toggleShadowMode" :class="{ 'active': isShadowMode }">
              {{ isShadowMode ? 'SHADOW' : 'BASE' }}
            </button>
            <DPad :isShadow="isShadowMode" />
          </div>
          
          <div v-if="isShadowMode" class="shadow-actions-grid">
            <button class="cmd-btn border-btn b-orange" @click="pubSys('shadow_on')">ENABLE</button>
            <button class="cmd-btn border-btn b-red" @click="pubSys('shadow_off')">DISABLE</button>
            <button class="cmd-btn c-red" @click="pubOperator('clear')">CLEAR</button>
            <button class="cmd-btn c-blue" @click="pubOperator('execute')">EXEC</button>
          </div>
          <button v-else class="cmd-btn c-red stop-btn" @click="stopBase">
            🛑 STOP BASE <span>Emergency Break</span>
          </button>
          
          <SpeedSlider />
        </div>
      </div>
    </div>

    <!-- Tab 4: Arm -->
    <div v-show="activeTab === 'arm'" class="tab-content active">
      <ArmControl />
    </div>

  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { pubSmartCommand, pubTwist, pubBool } from '../../services/rosConnection'
import { stopTeleopLoop } from '../../services/teleopCore'
import { useRosStore } from '../../stores/rosStore'
import CameraStream from './CameraStream.vue'
import DPad from './DPad.vue'
import SpeedSlider from './SpeedSlider.vue'
import ArmControl from './ArmControl.vue'

const store = useRosStore()
const activeTab = ref('manager')

const isWatchdogOn = ref(false)

const isWatchdogActive = computed(() => {
  if (store.telemetry?.fsm_state && store.telemetry.fsm_state !== 'UNKNOWN') {
    return store.telemetry.fsm_state !== 'DISABLED'
  }
  return isWatchdogOn.value
})

const toggleWatchdog = () => {
  const next = !isWatchdogActive.value
  isWatchdogOn.value = next
  pubSys(next ? 'watchdog_on' : 'watchdog_off')
}

const isVirtGeigerOn = ref(false)

const isVirtGeigerActive = computed(() => {
  if (store.radiationStatus?.geiger_active !== undefined) {
    return store.radiationStatus.geiger_active
  }
  return isVirtGeigerOn.value
})

const toggleVirtGeiger = () => {
  const next = !isVirtGeigerActive.value
  isVirtGeigerOn.value = next
  pubSys(next ? 'rad_geiger_on' : 'rad_geiger_off')
}

const mapNameSave = ref('')
const selectedScenarioMap = ref('start_213')
const customMapNameLoad = ref('')
const selectedRadMap = ref('radiation_map.npy')

const loadSelectedScenario = () => {
  if (selectedScenarioMap.value === 'custom') {
    if (customMapNameLoad.value.trim()) {
      pubSmartCommand('system', `start:lifelong:${customMapNameLoad.value.trim()}`)
    }
  } else if (selectedScenarioMap.value) {
    pubSys(selectedScenarioMap.value)
  }
}

const saveCustomMap = () => {
  if (mapNameSave.value.trim()) {
    pubSmartCommand('system', `save_map:${mapNameSave.value.trim()}`)
    mapNameSave.value = ''
  }
}

const loadSelectedRadMap = () => {
  if (selectedRadMap.value) {
    pubSys(`rad_load:${selectedRadMap.value}`)
  }
}

const isShadowMode = ref(false)

const toggleShadowMode = () => {
  isShadowMode.value = !isShadowMode.value
  if (activeTab.value === 'base') {
    store.setActiveRobotType(isShadowMode.value ? 'shadow' : 'base')
  }
}

const setTab = (tab) => {
  activeTab.value = tab
  stopTeleopLoop() // Reset movement when changing tabs
  
  if (tab === 'base') {
    store.setActiveRobotType(isShadowMode.value ? 'shadow' : 'base')
  } else {
    store.setActiveRobotType(null)
  }
}

const pubSys = (cmd) => pubSmartCommand('system', cmd)
const pubOperator = (cmd) => pubSmartCommand('operator', cmd)

const stopBase = () => {
  pubTwist('base', 0, 0)
}
</script>

<style scoped>
.teleop-tabs-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 10px;
  background: transparent;
  border: none;
  border-radius: 0;
  box-sizing: border-box;
}

.tabs { 
  display: flex; 
  gap: 3px; 
  margin-bottom: 12px; 
  padding: 2px;
  background: var(--bg-item);
  border: 1px solid var(--border);
  border-radius: 3px;
  flex-shrink: 0;
}

.tab-btn { 
  flex: 1;
  background: transparent; 
  color: var(--muted); 
  border: none; 
  padding: 6px 4px; 
  border-radius: 3px; 
  cursor: pointer; 
  font-size: 11px; 
  font-weight: 700; 
  text-transform: uppercase;
  letter-spacing: 0.3px;
  transition: all 0.15s; 
  white-space: nowrap; 
  text-align: center;
}

.tab-btn.active { 
  background: var(--accent); 
  color: #ffffff; 
  box-shadow: none;
}

.tab-btn:hover:not(.active) { 
  color: var(--text);
  background: var(--bg-item-hover);
}

.tab-content { 
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.mission-group { margin-bottom: 16px; }
.shadow-notice p {
  font-size: 11px;
  color: var(--muted);
  margin-top: 5px;
}

.group-title { 
  font-size: 11px; 
  font-weight: 700;
  color: var(--muted); 
  text-transform: uppercase; 
  letter-spacing: 0.5px;
  margin-bottom: 8px; 
  border-bottom: 1px solid var(--border); 
  padding-bottom: 4px; 
}

.scenario-selector-row {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}

.scenario-select,
.scenario-input {
  background: var(--bg-item);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 6px 10px;
  font-size: 11px;
  font-weight: 600;
  outline: none;
  height: 36px;
  box-sizing: border-box;
  transition: border-color 0.15s, background 0.15s;
}

.scenario-select {
  flex: 1;
  cursor: pointer;
}

.scenario-input {
  flex: 1;
}

.scenario-select:focus,
.scenario-input:focus {
  border-color: var(--border-focus);
}

.scenario-action-btn {
  flex: 0 0 90px;
  height: 36px;
  padding: 4px 10px;
  font-size: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
}

.scenario-modes-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  margin-bottom: 8px;
}

.scenario-modes-grid .cmd-btn {
  padding: 6px;
  font-size: 11px;
  min-height: 40px;
}

.scenario-modes-grid .cmd-btn span {
  font-size: 9px;
}

.small-grid { 
  display: grid; 
  grid-template-columns: repeat(4, 1fr); 
  gap: 6px; 
}
.small-grid .cmd-btn { 
  padding: 6px 4px; 
  font-size: 11px; 
  min-height: 40px; 
  width: 100%;
}
.small-grid .cmd-btn span { font-size: 9px; }

/* Toggle button styling with status LED */
.toggle-btn {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  gap: 3px;
  cursor: pointer;
  padding: 6px 4px;
  min-height: 40px;
  border-radius: 3px;
  border: 1px solid var(--border);
  background: var(--bg-item);
  transition: all 0.15s ease;
}

.toggle-header-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--muted);
  opacity: 0.35;
  transition: all 0.2s ease;
  display: inline-block;
  flex-shrink: 0;
}

.status-dot.dot-green.is-on {
  background: var(--green);
  opacity: 1;
  box-shadow: 0 0 6px var(--green);
}

.status-dot.dot-orange.is-on {
  background: var(--orange);
  opacity: 1;
  box-shadow: 0 0 6px var(--orange);
}

.toggle-title {
  font-weight: 700;
  font-size: 11px;
  letter-spacing: 0.3px;
  line-height: 1;
}

.toggle-state-text {
  font-size: 10px;
  font-weight: 600;
  color: var(--muted);
  line-height: 1;
  letter-spacing: 0.5px;
  margin-top: 2px;
}

.toggle-btn.is-active .toggle-state-text {
  color: var(--text);
  font-weight: 700;
}

.toggle-btn.b-green.is-active {
  border-left: 3px solid var(--green) !important;
}

.toggle-btn.b-orange.is-active {
  border-left: 3px solid var(--orange) !important;
}

.toggle-btn.b-muted {
  border-left: 3px solid var(--border) !important;
}

@media (max-width: 500px) {
  .small-grid { grid-template-columns: repeat(2, 1fr); gap: 4px; }
  .small-grid .cmd-btn { padding: 4px; font-size: 10px; min-height: 36px; }
  .small-grid .cmd-btn span { display: none; }
  .scenario-selector-row { flex-direction: column; }
  .scenario-action-btn { flex: 0 0 32px; width: 100%; }
}

.teleop-layout-vertical {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  width: 100%;
}

.camera-container {
  width: 100%;
  max-width: 800px;
}

.controls-frame {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  gap: 24px;
  width: 100%;
}

.stop-btn {
  height: 80px;
  width: 130px;
}

.shadow-actions-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 6px;
  width: 130px;
  height: 80px;
}

.shadow-actions-grid .cmd-btn {
  height: 100%;
  width: 100%;
  padding: 4px;
  font-size: 11px;
}

.mode-toggle-btn {
  position: absolute;
  top: -22px;
  left: 0;
  background: var(--bg-item);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 2px 8px;
  font-size: 10px;
  font-weight: 700;
  cursor: pointer;
  box-shadow: none;
  transition: 0.15s;
  z-index: 10;
}
.mode-toggle-btn.active {
  background: var(--accent);
  color: #ffffff;
  border-color: var(--accent);
}
</style>
