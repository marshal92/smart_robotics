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
    <div class="quick-actions-grid" v-else>
      <button class="unified-btn c-red" @click="cancelNav">
        <div class="waypoint-name">CANCEL</div>
      </button>
      <button class="unified-btn c-gray" @click="clearCostmaps">
        <div class="waypoint-name">CLEAR</div>
      </button>
      
      <button v-for="(data, name) in store.waypoints" :key="name"
              class="unified-btn" :class="data.type === 'route' ? 'c-purple' : 'c-blue'"
              @click="goTo(name)">
        <div class="del-btn" @click.stop="deleteWaypoint(name)">✖</div>
        <div class="waypoint-name">{{ name.toUpperCase() }}</div>
        <div class="waypoint-coords" v-if="data.x !== undefined">{{ data.x.toFixed(1) }}, {{ data.y.toFixed(1) }}, {{ data.yaw.toFixed(1) }}</div>
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
</style>
