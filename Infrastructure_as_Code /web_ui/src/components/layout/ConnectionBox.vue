<template>
  <div class="conn-box">
    <button class="btn-theme" @click="toggleTheme" title="Toggle Theme">
      {{ isLight ? '🌙' : '☀️' }}
    </button>
    <input type="text" v-model="wsUrl" />
    <button class="btn-connect" @click="handleConnect">Connect</button>
    <div id="status" :style="{ background: statusBg }">{{ store.status }}</div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRosStore } from '../../stores/rosStore'
import { connectROS } from '../../services/rosConnection'

const store = useRosStore()
const wsUrl = ref('ws://127.0.0.1:9090')
const isLight = ref(false)

const statusBg = computed(() => {
  if (store.status.includes('Connected')) return '#1b5e20'
  if (store.status.includes('Error')) return '#f57f17'
  return '#b71c1c' // Disconnected
})

const handleConnect = () => {
  connectROS(wsUrl.value)
}

const toggleTheme = () => {
  isLight.value = !isLight.value
  if (isLight.value) {
    document.documentElement.classList.add('light-theme')
    localStorage.setItem('theme', 'light')
  } else {
    document.documentElement.classList.remove('light-theme')
    localStorage.setItem('theme', 'dark')
  }
  window.dispatchEvent(new CustomEvent('theme-changed', { detail: isLight.value }))
}

onMounted(() => {
  const savedTheme = localStorage.getItem('theme')
  if (savedTheme === 'light') {
    isLight.value = true
    document.documentElement.classList.add('light-theme')
  }
})
</script>

<style scoped>
.conn-box { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.btn-connect { background: var(--accent); color: white; border: none; padding: 8px 15px; border-radius: 4px; cursor: pointer; font-weight: bold; }
.btn-theme { background: transparent; border: 1px solid var(--input-border); color: var(--text); padding: 5px 10px; border-radius: 4px; cursor: pointer; font-size: 16px; transition: 0.3s;}
.btn-theme:hover { background: var(--dark-bg); }
#status { font-weight: bold; padding: 5px 10px; border-radius: 4px; background: #424242; color: white;}
</style>
