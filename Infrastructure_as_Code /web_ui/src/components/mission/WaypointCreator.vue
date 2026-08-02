<template>
  <div class="creator-panel">
    <div style="display:flex; gap:10px; flex-wrap: wrap; align-items: flex-end;">
      <div class="input-group">
        <label>Name</label>
        <input type="text" v-model="form.name" placeholder="Target A" />
      </div>
      <div class="input-group">
        <label>X (m)</label>
        <input type="number" v-model.number="form.x" step="0.1" style="width: 70px;" />
      </div>
      <div class="input-group">
        <label>Y (m)</label>
        <input type="number" v-model.number="form.y" step="0.1" style="width: 70px;" />
      </div>
      <div class="input-group">
        <label>Yaw (rad)</label>
        <input type="number" v-model.number="form.yaw" step="0.1" style="width: 70px;" />
      </div>
      
      <button class="btn-action" style="background: var(--accent);" @click="addSinglePoint">Point</button>
      <button class="btn-action" style="background: #555;" @click="addToQueue">Waypoints</button>
    </div>
    
    <div v-if="store.routeQueue.length > 0" class="route-ui">
      <span style="color:#aaa; font-size:13px; margin-right: 15px;">
        Points in route: <span style="color:white; font-weight:bold;">{{ store.routeQueue.length }}</span>
      </span>
      <button class="btn-action" style="background: #7b1fa2; padding:5px 10px; font-size:12px; height: auto;" @click="saveRoute">Save as Route</button>
      <button class="btn-action" style="background: transparent; border:1px solid var(--red); color:var(--red); padding:5px 10px; font-size:12px; height: auto; margin-left: 10px;" @click="store.clearRouteQueue">Reset</button>
    </div>
  </div>
</template>

<script setup>
import { reactive } from 'vue'
import { pubSmartCommand } from '../../services/rosConnection'
import { useRosStore } from '../../stores/rosStore'

const props = defineProps({
  activeMissionTab: String
})

const store = useRosStore()

const form = reactive({
  name: '',
  x: 0.0,
  y: 0.0,
  yaw: 0.0
})

const addSinglePoint = () => {
  const name = form.name.toLowerCase().replace(/\s+/g, '_') || `point_${Math.floor(Date.now() / 1000)}`
  pubSmartCommand('waypoints', 'save', {
    name: name,
    tab: props.activeMissionTab,
    x: form.x,
    y: form.y,
    yaw: form.yaw
  })
  form.name = ''
}

const addToQueue = () => {
  store.addToRouteQueue([form.x, form.y, form.yaw])
  form.name = ''
}

const saveRoute = () => {
  if (store.routeQueue.length === 0) return
  const name = form.name.toLowerCase().replace(/\s+/g, '_') || `route_${Math.floor(Date.now() / 1000)}`
  pubSmartCommand('waypoints', 'save', {
    name: name,
    tab: props.activeMissionTab,
    points: [...store.routeQueue]
  })
  store.clearRouteQueue()
}
</script>

<style scoped>
.creator-panel { padding-top: 10px; }
.input-group { display: flex; flex-direction: column; gap: 5px; }
.input-group label { font-size: 12px; color: #aaa; }
.btn-action { color: white; border: none; padding: 8px 15px; border-radius: 4px; cursor: pointer; font-weight: bold; height: 35px; }
.route-ui { margin-top:15px; padding:10px; background:#111; border-radius:4px; border: 1px dashed #555; display: flex; align-items: center; }
</style>
