<template>
  <div class="camera-wrapper" ref="camContainer">
    <img v-if="store.cameraStream" :src="store.cameraStream" alt="Camera Stream" @dblclick="toggleFullscreen" />
    <div v-else class="no-signal">NO SIGNAL</div>
    
    <div class="camera-controls">
      <button class="topic-btn" :class="{ active: !isYolo }" @click="setTopic('raw')">RAW</button>
      <button class="topic-btn" :class="{ active: isYolo }" @click="setTopic('yolo')">YOLO</button>
      <button class="fullscreen-btn" @click="toggleFullscreen" title="Fullscreen">⛶</button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRosStore } from '../../stores/rosStore'
import { switchCameraTopic } from '../../services/rosConnection'

const store = useRosStore()
const camContainer = ref(null)
const isYolo = ref(false)

const setTopic = (mode) => {
  isYolo.value = (mode === 'yolo')
  const topic = isYolo.value ? '/yolo_overlay/compressed' : '/camera/image_raw/compressed'
  switchCameraTopic(topic)
}

const toggleFullscreen = () => {
  if (!document.fullscreenElement) {
    if (camContainer.value.requestFullscreen) {
      camContainer.value.requestFullscreen()
    }
  } else {
    if (document.exitFullscreen) {
      document.exitFullscreen()
    }
  }
}
</script>

<style scoped>
.camera-wrapper {
  position: relative;
  width: 100%; 
  aspect-ratio: 4/3; 
  background: #000; 
  border: 1px solid #333; 
  border-radius: 8px; 
  overflow: hidden; 
  display: flex; 
  align-items: center; 
  justify-content: center;
}
.camera-wrapper img {
  width: 100%; 
  height: 100%; 
  object-fit: cover;
  cursor: pointer;
}
.no-signal {
  color: red; 
  font-weight: bold; 
  font-family: monospace;
}
.fullscreen-btn {
  background: rgba(0, 0, 0, 0.5);
  color: white;
  border: none;
  border-radius: 4px;
  width: 30px;
  height: 30px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  transition: 0.2s;
}
.fullscreen-btn:hover {
  background: rgba(0, 0, 0, 0.8);
}
.camera-controls {
  position: absolute;
  top: 10px;
  right: 10px;
  display: flex;
  gap: 5px;
  background: rgba(0,0,0,0.3);
  padding: 5px;
  border-radius: 6px;
}
.topic-btn {
  background: rgba(0,0,0,0.5);
  color: #ccc;
  border: 1px solid transparent;
  padding: 5px 10px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: bold;
  cursor: pointer;
  transition: 0.2s;
}
.topic-btn.active {
  background: var(--accent);
  color: white;
  border-color: var(--accent);
}
.topic-btn:hover:not(.active) {
  background: rgba(0,0,0,0.8);
}
</style>
