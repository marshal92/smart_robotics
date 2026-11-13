<template>
  <header class="app-header">
    <div class="brand">
      <strong>SUPERVISORY HMI</strong>
      <span class="brand-version">2.0</span>
      <button class="btn-theme-cad" @click="toggleTheme" title="Toggle Academic Light / Dark Theme">
        Theme ◐
      </button>
    </div>

    <TelemetryHUD />

    <div class="header-right">
      <ConnectionBox />
      <button class="estop-btn" @click="handleNavStop" title="Cancel Navigation & Halt Movement">
        🛑 STOP
      </button>
    </div>
  </header>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import TelemetryHUD from './TelemetryHUD.vue'
import ConnectionBox from './ConnectionBox.vue'
import { pubSmartCommand, pubTwist } from '../../services/rosConnection'

const isLight = ref(false)

const toggleTheme = () => {
  isLight.value = !isLight.value
  applyTheme(isLight.value)
}

const applyTheme = (light) => {
  if (light) {
    document.documentElement.classList.add('light-theme')
    document.documentElement.dataset.theme = 'light'
    localStorage.setItem('theme', 'light')
  } else {
    document.documentElement.classList.remove('light-theme')
    document.documentElement.dataset.theme = 'dark'
    localStorage.setItem('theme', 'dark')
  }
  window.dispatchEvent(new CustomEvent('theme-changed', { detail: light }))
}

onMounted(() => {
  const savedTheme = localStorage.getItem('theme')
  if (savedTheme === 'light') {
    isLight.value = true
    applyTheme(true)
  } else {
    applyTheme(false)
  }
})

const handleNavStop = () => {
  // Cancel navigation task and immediately zero base velocity
  pubSmartCommand('nav', 'cancel', { x: 0, y: 0, yaw: 0 })
  pubTwist('base', 0, 0)
}
</script>

<style scoped>
.app-header { 
  display: flex; 
  align-items: center; 
  justify-content: space-between; 
  gap: 12px;
  height: 42px;
  min-height: 42px;
  max-height: 42px;
  background: var(--bg-panel); 
  padding: 0 12px; 
  border-bottom: 1px solid var(--border);
  user-select: none;
  z-index: 20;
}

.brand {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  letter-spacing: 0.5px;
  color: var(--text);
  white-space: nowrap;
}

.brand-version {
  font-size: 10px;
  color: var(--muted);
  font-weight: 600;
  font-family: 'JetBrains Mono', monospace;
}

.btn-theme-cad {
  background: var(--bg-item);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 3px 8px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 11px;
  font-weight: 600;
  margin-left: 6px;
  transition: background 0.15s, border-color 0.15s;
}
.btn-theme-cad:hover {
  background: var(--bg-item-hover);
  border-color: var(--border-focus);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.estop-btn {
  background: var(--red);
  color: #ffffff;
  border: 1px solid #991b1b;
  border-radius: 3px;
  padding: 4px 12px;
  font-weight: 700;
  font-size: 11px;
  cursor: pointer;
  letter-spacing: 0.5px;
  white-space: nowrap;
  transition: background 0.15s, transform 0.05s;
}

.estop-btn:hover {
  background: #b91c1c;
}

.estop-btn:active {
  transform: translateY(1px);
}

@media (max-width: 768px) {
  .app-header {
    height: auto;
    max-height: none;
    flex-wrap: wrap;
    padding: 6px 10px;
  }
}
</style>
