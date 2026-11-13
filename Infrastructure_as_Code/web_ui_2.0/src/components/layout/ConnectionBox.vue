<template>
  <div class="conn-box">
    <!-- Compact connected status (Click to edit address) -->
    <div 
      v-if="isConnected && !isEditing" 
      class="connected-pill mono" 
      @click="isEditing = true"
      title="Connected. Click to change address"
    >
      <span class="dot-green">●</span>
      <span class="ws-label">{{ wsUrl }}</span>
    </div>

    <!-- Edit address or Disconnected state -->
    <div v-else class="conn-form">
      <input 
        type="text" 
        v-model="wsUrl" 
        class="mono ws-input" 
        :placeholder="defaultWsUrl" 
        @keyup.enter="handleConnect"
      />
      <button class="btn-connect" @click="handleConnect">Connect</button>
      <button v-if="isConnected && isEditing" class="btn-cancel-edit" @click="isEditing = false" title="Close edit">✕</button>
      <div v-if="!isConnected" id="status" class="mono" :style="{ background: statusBg }">
        <span class="status-dot">●</span>
        <span>{{ store.status }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRosStore } from '../../stores/rosStore'
import { connectROS } from '../../services/rosConnection'

const store = useRosStore()
const defaultWsHost =
  typeof window !== 'undefined' && window.location?.hostname
    ? window.location.hostname
    : '127.0.0.1'
const defaultWsUrl = `ws://${defaultWsHost}:9090`
const wsUrl = ref(defaultWsUrl)
const isEditing = ref(false)

const isConnected = computed(() => store.status.includes('Connected'))

const statusBg = computed(() => {
  if (store.status.includes('Connected')) return 'var(--green)'
  if (store.status.includes('Error')) return 'var(--orange)'
  return 'var(--red)' // Disconnected
})

const handleConnect = () => {
  connectROS(wsUrl.value)
  isEditing.value = false
}
</script>

<style scoped>
.conn-box { 
  display: flex; 
  align-items: center; 
  gap: 6px; 
}

.connected-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--bg-item);
  border: 1px solid var(--border);
  padding: 3px 8px;
  border-radius: 3px;
  cursor: pointer;
  font-size: 11px;
  color: var(--text);
  transition: border-color 0.15s, background 0.15s;
}

.connected-pill:hover {
  background: var(--bg-item-hover);
  border-color: var(--border-focus);
}

.dot-green {
  color: var(--green);
  font-size: 10px;
}

.ws-label {
  font-family: 'JetBrains Mono', monospace;
}

.conn-form {
  display: flex;
  align-items: center;
  gap: 4px;
}

.ws-input {
  background: var(--bg-input);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 3px 6px;
  border-radius: 3px;
  font-size: 11px;
  width: 140px;
}
.ws-input:focus {
  border-color: var(--border-focus);
}

.btn-connect { 
  background: var(--accent); 
  color: #ffffff; 
  border: 1px solid var(--accent); 
  padding: 3px 8px; 
  border-radius: 3px; 
  cursor: pointer; 
  font-weight: 600; 
  font-size: 11px;
  transition: background 0.15s;
}
.btn-connect:hover {
  background: var(--accent-hover);
}

.btn-cancel-edit {
  background: transparent;
  border: none;
  color: var(--muted);
  font-size: 11px;
  cursor: pointer;
  padding: 2px 4px;
}
.btn-cancel-edit:hover {
  color: var(--text);
}

#status { 
  font-size: 10px;
  font-weight: 600; 
  padding: 2px 6px; 
  border-radius: 3px; 
  color: #ffffff;
  display: flex;
  align-items: center;
  gap: 4px;
  font-family: 'JetBrains Mono', monospace;
  white-space: nowrap;
}

.status-dot {
  font-size: 8px;
}

@media (max-width: 900px) {
  .ws-input {
    width: 100px;
    font-size: 10px;
  }
}
</style>
