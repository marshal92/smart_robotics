<template>
  <div class="log-container">
    <div class="log-box" ref="logBox">
      <div v-for="(msg, index) in store.logs" :key="index" :style="{ color: getLogColor(msg.level) }">
        {{ getLogPrefix(msg.level) }} [{{ msg.name }}]: {{ msg.msg }}
      </div>
      <div v-if="store.logs.length === 0" class="log-empty">
        ROS logs will appear here when topics receive messages...
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
  if (level === 30) return "var(--orange)" // WARN
  if (level === 40 || level === 50) return "var(--red)" // ERROR/FATAL
  return "var(--console-text)" // INFO
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
  background: var(--console-bg); 
  height: 100%;
  padding: 6px 10px; 
  box-sizing: border-box;
}

.log-box {
  height: 100%; 
  overflow-y: auto; 
  font-family: 'JetBrains Mono', monospace; 
  font-variant-numeric: tabular-nums;
  font-size: 11px; 
  line-height: 1.45;
  white-space: pre-wrap;
  color: var(--console-text);
}

.log-empty {
  color: var(--muted);
  opacity: 0.6;
  font-style: italic;
  padding: 4px 0;
}
</style>
