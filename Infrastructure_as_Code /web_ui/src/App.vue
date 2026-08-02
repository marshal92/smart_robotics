<template>
  <div id="app-container">
    <AppHeader />
    
    <div class="main-layout">
      <div class="left-panel">
        <DigitalTwin3D />
        <QuickActions />
      </div>
      <div class="right-panel">
        <TeleopTabs />
      </div>
    </div>

    <MissionManager />
    <RosConsole />
  </div>
</template>

<script setup>
import AppHeader from './components/layout/AppHeader.vue'
import DigitalTwin3D from './components/layout/DigitalTwin3D.vue'
import TeleopTabs from './components/teleop/TeleopTabs.vue'
import QuickActions from './components/teleop/QuickActions.vue'
import MissionManager from './components/mission/MissionManager.vue'
import RosConsole from './components/console/RosConsole.vue'
</script>

<style>
/* Any global resets not in style.css can go here, but style.css is already imported in main.js */
#app-container {
  max-width: 100%;
  margin: 0 auto;
  padding: 0 40px;
}

.main-layout {
  display: flex;
  gap: 20px;
  margin-bottom: 20px;
}

.left-panel {
  flex: 1 1 auto;
  min-width: 0; /* allows flex items to shrink below their minimum intrinsic size */
  display: flex;
  flex-direction: column;
}

.right-panel {
  flex: 0 0 500px; /* fixed width, large enough so it doesn't jump */
}

@media (max-width: 1024px) {
  .main-layout {
    flex-direction: column;
  }
  .right-panel {
    flex: 1 1 auto;
  }
}
</style>
