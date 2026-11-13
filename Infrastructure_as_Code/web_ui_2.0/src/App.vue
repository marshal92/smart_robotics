<template>
  <div id="app-container">
    <AppHeader />

    <!-- Responsive View Mode Bar (Visible when screen width <= 1024px) -->
    <div v-if="isCompact" class="responsive-view-bar">
      <button 
        class="resp-btn" 
        :class="{ active: compactTab === 'split' }" 
        @click="setCompactTab('split')"
      >
        <span>◫ Split View</span>
      </button>
      <button 
        class="resp-btn" 
        :class="{ active: compactTab === '3d' }" 
        @click="setCompactTab('3d')"
      >
        <span>🗺 3D View</span>
      </button>
      <button 
        class="resp-btn" 
        :class="{ active: compactTab === 'controls' }" 
        @click="setCompactTab('controls')"
      >
        <span>🎛 Controls</span>
      </button>
    </div>
    
    <div class="main-layout" :class="[`view-${compactTab}`, { 'is-compact': isCompact }]">
      <div v-show="!isCompact || compactTab !== 'controls'" class="left-panel">
        <DigitalTwin3D />
      </div>
      <div v-show="!isCompact || compactTab !== '3d'" class="right-panel">
        <TeleopTabs />
      </div>
    </div>

    <!-- Bottom Collapsible Dock -->
    <div class="bottom-dock" :class="{ 'is-collapsed': isBottomCollapsed }">
      <div class="dock-header">
        <div class="dock-tabs">
          <button 
            class="dock-tab-btn" 
            :class="{ active: activeDockTab === 'nav' }"
            @click="selectDockTab('nav')"
          >
            <span>Actions & Navigation</span>
          </button>
          <button 
            class="dock-tab-btn" 
            :class="{ active: activeDockTab === 'creator' }"
            @click="selectDockTab('creator')"
          >
            <span>Waypoint Creator</span>
          </button>
          <button 
            class="dock-tab-btn" 
            :class="{ active: activeDockTab === 'console' }"
            @click="selectDockTab('console')"
          >
            <span>ROS Console</span>
            <span v-if="store.logs.length" class="dock-badge">{{ store.logs.length }}</span>
          </button>
        </div>

        <button 
          class="dock-toggle-btn" 
          @click="isBottomCollapsed = !isBottomCollapsed" 
          :title="isBottomCollapsed ? 'Expand Dock' : 'Collapse Dock'"
        >
          {{ isBottomCollapsed ? '▲' : '▼' }}
        </button>
      </div>

      <div v-show="!isBottomCollapsed" class="dock-body">
        <div v-show="activeDockTab === 'nav'" class="dock-view">
          <QuickActions />
        </div>
        <div v-show="activeDockTab === 'creator'" class="dock-view">
          <MissionManager />
        </div>
        <div v-show="activeDockTab === 'console'" class="dock-view">
          <RosConsole />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRosStore } from './stores/rosStore'
import AppHeader from './components/layout/AppHeader.vue'
import DigitalTwin3D from './components/layout/DigitalTwin3D.vue'
import TeleopTabs from './components/teleop/TeleopTabs.vue'
import QuickActions from './components/teleop/QuickActions.vue'
import MissionManager from './components/mission/MissionManager.vue'
import RosConsole from './components/console/RosConsole.vue'

const store = useRosStore()
const isBottomCollapsed = ref(false)
const activeDockTab = ref('nav')

// Responsive mode for small/narrow windows (<= 1024px)
const isCompact = ref(typeof window !== 'undefined' ? window.innerWidth <= 1024 : false)
const compactTab = ref('split') // 'split' | '3d' | 'controls'

const handleWindowResize = () => {
  isCompact.value = window.innerWidth <= 1024
}

const setCompactTab = (tab) => {
  compactTab.value = tab
  nextTick(() => {
    // Notify Three.js viewer and map layers to recalculate sizes immediately
    window.dispatchEvent(new Event('resize'))
  })
}

const selectDockTab = (tab) => {
  activeDockTab.value = tab
  if (isBottomCollapsed.value) {
    isBottomCollapsed.value = false
  }
}

onMounted(() => {
  window.addEventListener('resize', handleWindowResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleWindowResize)
})
</script>

<style>
#app-container {
  height: 100vh;
  width: 100vw;
  max-width: 100vw;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg-main);
  color: var(--text);
}

.main-layout {
  flex: 1 1 0;
  min-height: 0;
  display: flex;
  overflow: hidden;
  background: var(--bg-main);
}

.left-panel {
  flex: 1 1 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.right-panel {
  flex: 0 0 504px;
  width: 504px;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-panel);
  border-left: 1px solid var(--border);
  overflow-y: auto;
}

/* ==========================================================================
   Responsive View Bar (Active when <= 1024px)
   ========================================================================== */
.responsive-view-bar {
  height: 28px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 8px;
  flex-shrink: 0;
  user-select: none;
  z-index: 12;
}

.resp-btn {
  background: transparent;
  color: var(--muted);
  border: 1px solid transparent;
  border-radius: 3px;
  padding: 2px 10px;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s;
}

.resp-btn:hover {
  color: var(--text);
  background: var(--bg-item);
}

.resp-btn.active {
  background: var(--bg-item);
  color: var(--accent);
  border-color: var(--border);
}

/* ==========================================================================
   Compact / Small Window Layout Modes (<= 1024px)
   ========================================================================== */
@media (max-width: 1024px) {
  /* Mode 1: Split View (Default stacked with vertical scroll) */
  .main-layout.view-split {
    flex-direction: column;
    overflow-y: auto;
    overflow-x: hidden;
    -webkit-overflow-scrolling: touch;
  }
  .main-layout.view-split .left-panel {
    flex: 0 0 auto;
    height: 48vh;
    min-height: 340px;
    border-bottom: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .main-layout.view-split .right-panel {
    width: 100%;
    flex: 0 0 auto;
    border-left: none;
    border-top: none;
    overflow-y: visible;
  }

  /* Mode 2: 3D View Only (Full space for map & navigation) */
  .main-layout.view-3d {
    flex-direction: column;
    overflow: hidden;
  }
  .main-layout.view-3d .left-panel {
    flex: 1 1 auto;
    height: 100%;
    min-height: 0;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* Mode 3: Controls Only (Full space for Teleop / Arm / Manager) */
  .main-layout.view-controls {
    flex-direction: column;
    overflow: hidden;
  }
  .main-layout.view-controls .right-panel {
    width: 100%;
    flex: 1 1 auto;
    height: 100%;
    border-left: none;
    overflow-y: auto;
  }
}

/* ==========================================================================
   Bottom Dock
   ========================================================================== */
.bottom-dock {
  flex: 0 0 auto;
  background: var(--bg-panel);
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  transition: all 0.2s ease;
  z-index: 15;
}

.dock-header {
  height: 26px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 8px;
  user-select: none;
}

.dock-tabs {
  display: flex;
  gap: 4px;
  height: 100%;
  align-items: center;
}

.dock-tab-btn {
  background: transparent;
  color: var(--muted);
  border: none;
  border-bottom: 2px solid transparent;
  padding: 0 10px;
  height: 26px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: color 0.15s;
}

.dock-tab-btn:hover {
  color: var(--text);
}

.dock-tab-btn.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
  background: var(--bg-item);
}

.dock-badge {
  background: var(--bg-item-hover);
  color: var(--muted);
  font-size: 9px;
  padding: 1px 5px;
  border-radius: 3px;
  font-family: 'JetBrains Mono', monospace;
}

.dock-toggle-btn {
  background: transparent;
  border: none;
  color: var(--muted);
  font-size: 10px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 3px;
}

.dock-toggle-btn:hover {
  background: var(--bg-item);
  color: var(--text);
}

.dock-body {
  height: 125px;
  overflow: hidden;
  background: var(--bg-main);
}

.dock-view {
  height: 100%;
  overflow: auto;
}
</style>
