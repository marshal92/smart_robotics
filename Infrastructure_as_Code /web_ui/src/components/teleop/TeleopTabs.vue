<template>
  <div class="block-container">
    <h3 class="block-title">Block 1: Core Systems & Teleop</h3>
    <div class="tabs">
      <button class="tab-btn" :class="{ active: activeTab === 'manager' }" @click="setTab('manager')">Mission Manager</button>
      <button class="tab-btn" :class="{ active: activeTab === 'base' }" @click="setTab('base')">Direct Teleop (Base)</button>
      <button class="tab-btn" :class="{ active: activeTab === 'shadow' }" @click="setTab('shadow')">Shadow Control</button>
    </div>

    <!-- Tab 1: Mission Manager -->
    <div v-show="activeTab === 'manager'" class="tab-content active">
      <div class="mission-groups">
        
        <!-- Core Controls (No heading) -->
        <div class="small-grid" style="margin-bottom: 25px;">
          <button class="cmd-btn c-red" @click="pubSys('stop')">🛑 STOP <span>Halt everything</span></button>
          <button class="cmd-btn c-orange" @click="pubOperator('RESUME')">RESUME <span>Unlock system</span></button>
        </div>

        <!-- Group 2: Maps & Scenarios -->
        <div class="mission-group">
          <h4 class="group-title">Maps & Scenarios</h4>
          <div class="small-grid">
            <button class="cmd-btn c-green" @click="pubSys('start_213')">Room 213 <span>Load 213 config</span></button>
            <button class="cmd-btn c-green" @click="pubSys('start_kitchen')">Kitchen <span>Load kitchen config</span></button>
            <button class="cmd-btn c-green" @click="pubSys('start_shelter_zero')">Shelter Zero <span>Launch default seq</span></button>
            <button class="cmd-btn c-green" @click="pubSys('start_freeride')">Freeride <span>Manual mode</span></button>
          </div>
        </div>

        <!-- Group 3: Tools -->
        <div class="mission-group">
          <h4 class="group-title">Tools & Safety</h4>
          <div class="small-grid">
            <button class="cmd-btn border-btn b-orange" @click="pubSys('rad_on')">Rad Map ON <span>Enable radiation sim</span></button>
            <button class="cmd-btn border-btn b-gray" @click="pubSys('rad_off')">Rad Map OFF <span>Disable radiation sim</span></button>
            <button class="cmd-btn border-btn b-green" @click="pubSys('watchdog_on')">Watchdog ON <span>Enable safety</span></button>
            <button class="cmd-btn border-btn b-red" @click="pubSys('watchdog_off')">Watchdog OFF <span>Disable safety</span></button>
          </div>
        </div>

        <!-- Group 4: Custom Maps -->
        <div class="mission-group">
          <h4 class="group-title">Custom Maps</h4>
          <div class="custom-map-controls">
            <div class="map-input-group">
              <input type="text" v-model="mapNameSave" placeholder="Map name to save" class="map-input" />
              <button class="cmd-btn c-blue small-btn" @click="saveCustomMap">Save Map <span>(creates map)</span></button>
            </div>
            <div class="map-input-group">
              <input type="text" v-model="mapNameLoad" placeholder="Map name to load" class="map-input" />
              <button class="cmd-btn c-purple small-btn" @click="loadCustomMap">Load Map <span>(starts lifelong)</span></button>
            </div>
          </div>
        </div>

      </div>
    </div>

    <!-- Tab 2: Direct Teleop (Base) -->
    <div v-show="activeTab === 'base'" class="tab-content active">
      <div class="teleop-layout-vertical">
        <div class="camera-container">
          <CameraStream />
        </div>
        <div class="controls-frame">
          <DPad :isShadow="false" />
          <button class="cmd-btn c-red stop-btn" @click="stopBase">
            🛑 STOP BASE <span>Emergency Break</span>
          </button>
          <SpeedSlider />
        </div>
      </div>
    </div>
    
    <!-- Tab 3: Shadow Control -->
    <div v-show="activeTab === 'shadow'" class="tab-content active">
      <div class="teleop-layout-vertical">
        <div class="controls-frame">
          <DPad :isShadow="true" />
          <div class="shadow-actions">
            <button class="cmd-btn c-red" @click="pubOperator('clear')">
              CLEAR <span>Stop shadow & robot</span>
            </button>
            <button class="cmd-btn c-blue" @click="pubOperator('execute')">
              EXECUTE <span>Execute route</span>
            </button>
          </div>
          <SpeedSlider />
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref } from 'vue'
import { pubSmartCommand, pubTwist } from '../../services/rosConnection'
import { stopTeleopLoop } from '../../services/teleopCore'
import { useRosStore } from '../../stores/rosStore'
import CameraStream from './CameraStream.vue'
import DPad from './DPad.vue'
import SpeedSlider from './SpeedSlider.vue'

const store = useRosStore()
const activeTab = ref('manager')

const mapNameSave = ref('')
const mapNameLoad = ref('')

const saveCustomMap = () => {
  if (mapNameSave.value.trim()) {
    pubSmartCommand('system', `save_map:${mapNameSave.value.trim()}`)
    mapNameSave.value = ''
  }
}

const loadCustomMap = () => {
  if (mapNameLoad.value.trim()) {
    pubSmartCommand('system', `start:lifelong:${mapNameLoad.value.trim()}`)
  }
}

const setTab = (tab) => {
  activeTab.value = tab
  stopTeleopLoop() // Reset movement when changing tabs
  
  if (tab === 'base') {
    store.setActiveRobotType('base')
  } else if (tab === 'shadow') {
    store.setActiveRobotType('shadow')
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
.tabs { display: flex; gap: 10px; margin-bottom: 15px; overflow-x: auto; padding-bottom: 5px;}
.tab-btn { background: #333; color: #aaa; border: none; padding: 10px 15px; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: bold; transition: 0.2s; white-space: nowrap;}
.tab-btn.active { background: var(--accent); color: white; box-shadow: 0 0 8px rgba(25, 118, 210, 0.5);}
.tab-btn:hover:not(.active) { background: #444; }
.tab-content { 
  min-height: 550px; 
}

.mission-group { margin-bottom: 25px; }
.shadow-notice p {
  font-size: 13px;
  color: #aaa;
  margin-top: 5px;
}

.custom-map-controls {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.map-input-group {
  display: flex;
  gap: 10px;
}
.map-input {
  flex: 1;
  background: #111;
  border: 1px solid #444;
  color: #fff;
  padding: 10px 15px;
  border-radius: 6px;
  font-size: 14px;
  outline: none;
  transition: border-color 0.2s;
}
.map-input:focus {
  border-color: var(--accent);
}
.small-btn {
  padding: 5px 15px !important;
  min-height: 40px !important;
  white-space: nowrap;
}

.group-title { font-size: 13px; color: #888; text-transform: uppercase; margin-bottom: 10px; border-bottom: 1px solid #333; padding-bottom: 5px; }
.small-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 8px; }
.small-grid .cmd-btn { padding: 8px; font-size: 13px; min-height: 45px; }
.small-grid .cmd-btn span { font-size: 10px; }

/* Border Buttons for Tools & Safety */
.border-btn { background: #555 !important; border-bottom: 3px solid transparent; border-radius: 6px; }
.border-btn.b-green { border-bottom-color: #4caf50 !important; }
.border-btn.b-red { border-bottom-color: #f44336 !important; }
.border-btn.b-orange { border-bottom-color: #ff9800 !important; }
.border-btn.b-gray { border-bottom-color: #9e9e9e !important; }

.teleop-layout-vertical {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
  width: 100%;
}

.camera-container {
  width: 100%;
  max-width: 800px; /* Made camera bigger */
}

.controls-frame {
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: center;
  gap: 40px;
  width: 100%;
}

.stop-btn {
  height: 100px;
  width: 160px;
}

.shadow-actions {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.shadow-actions .cmd-btn {
  height: 60px;
  width: 160px;
}
</style>
