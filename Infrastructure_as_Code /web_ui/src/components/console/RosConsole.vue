<template>
  <div class="log-container">
    <h4 class="log-title">ROS Console Output</h4>
    <div class="log-box" ref="logBox">
      <div v-for="(msg, index) in store.logs" :key="index" :style="{ color: getLogColor(msg.level) }">
        {{ getLogPrefix(msg.level) }} [{{ msg.name }}]: {{ msg.msg }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { useRosStore } from '../../stores/rosStore'

const store = useRosStore()
const logBox = ref(null)

const getLogColor = (level) => {
  if (level === 30) return "#ffeb3b" // WARN
  if (level === 40 || level === 50) return "#f44336" // ERROR/FATAL
  return "#aaa" // INFO
}

const getLogPrefix = (level) => {
  if (level === 30) return "[WARN]"
  if (level === 40 || level === 50) return "[ERROR]"
  return "[INFO]"
}

watch(() => store.logs.length, async () => {
  await nextTick()
  if (logBox.value) {
    logBox.value.scrollTop = logBox.value.scrollHeight
  }
})
</script>

<style scoped>
.log-container {
  background: #111; 
  padding: 10px; 
  border-radius: 6px; 
  border: 1px solid #333; 
  margin-top: 20px;
}
.log-title {
  margin: 0 0 10px 0; 
  color: #888;
}
.log-box {
  height: 150px; 
  overflow-y: auto; 
  font-family: monospace; 
  font-size: 11px; 
  white-space: pre-wrap;
}
</style>
