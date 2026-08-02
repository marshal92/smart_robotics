<template>
  <div class="conn-box">
    <input type="text" v-model="wsUrl" />
    <button class="btn-connect" @click="handleConnect">Connect</button>
    <div id="status" :style="{ background: statusBg }">{{ store.status }}</div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRosStore } from '../../stores/rosStore'
import { connectROS } from '../../services/rosConnection'

const store = useRosStore()
const wsUrl = ref('ws://127.0.0.1:9090')

const statusBg = computed(() => {
  if (store.status.includes('Connected')) return '#1b5e20'
  if (store.status.includes('Error')) return '#f57f17'
  return '#b71c1c' // Disconnected
})

const handleConnect = () => {
  connectROS(wsUrl.value)
}
</script>

<style scoped>
.conn-box { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.btn-connect { background: var(--accent); color: white; border: none; padding: 8px 15px; border-radius: 4px; cursor: pointer; font-weight: bold; }
#status { font-weight: bold; padding: 5px 10px; border-radius: 4px; background: #424242; }
</style>
