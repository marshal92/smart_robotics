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
      <button class="compact-btn c-orange" @click="setLight(true)">Light ON</button>
      <button class="compact-btn c-gray" @click="setLight(false)">Light OFF</button>
      <button class="compact-btn c-purple" @click="mockSample">Sampling Protocol</button>
    </div>
    
    <!-- Nav Tab -->
    <div class="quick-actions-grid" v-else>
      <button class="compact-btn c-red" @click="cancelNav">🛑 CANCEL NAV</button>
      <button class="compact-btn c-gray" @click="clearCostmaps">Clear Costmaps</button>
      
      <button v-for="[name, data] in Object.entries(store.waypoints)" :key="name"
              class="compact-btn" :class="data.type === 'route' ? 'c-purple' : 'c-blue'"
              @click="goTo(name)">
        <div class="del-btn" @click.stop="deleteWaypoint(name)">✖</div>
        {{ name.toUpperCase() }}
      </button>
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
const clearCostmaps = () => pubSmartCommand('system', 'clear_costmaps')
const goTo = (name) => pubSmartCommand('nav', 'go_to_named', { name })
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
  height: 60px;
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
  gap: 10px;
  width: 100%;
}

.compact-btn {
  background: #555;
  color: white;
  border: none;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px; 
  font-weight: bold;
  transition: 0.2s;
  width: 120px; /* Fixed width */
  height: 35px; /* Fixed height for 2 rows in 80px container */
  flex: none; /* Do not stretch */
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  position: relative; /* For del-btn */
}

.compact-btn:hover {
  filter: brightness(1.2);
}

.compact-btn:active {
  transform: translateY(2px);
}

.del-btn {
  position: absolute;
  top: 2px;
  right: 2px;
  background: rgba(0,0,0,0.5);
  border: none;
  color: white;
  border-radius: 50%;
  width: 14px;
  height: 14px;
  font-size: 9px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.del-btn:hover {
  background: red;
}

/* Base Colors */
.c-red { border-bottom: 3px solid #f44336; }
.c-green { border-bottom: 3px solid #4caf50; }
.c-blue { border-bottom: 3px solid #2196f3; }
.c-orange { border-bottom: 3px solid #ff9800; }
.c-gray { border-bottom: 3px solid #9e9e9e; }
.c-purple { border-bottom: 3px solid #9c27b0; }
</style>
