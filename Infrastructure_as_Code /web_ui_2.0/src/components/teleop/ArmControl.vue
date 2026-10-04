<template>
  <div class="arm-control">
    <div class="arm-inner">
      
      <div class="joint-list">
        <div v-for="(limit, index) in jointLimits" :key="index" class="joint-row">
          <span class="joint-lbl">J{{ index }}</span>
          
          <button class="unified-btn arm-step-btn" @click="stepJoint(index, -5)">
            <div>-</div>
          </button>
          
          <input 
            type="range" 
            :min="limit.min" 
            :max="limit.max" 
            step="0.5" 
            v-model.number="targetJointAnglesDeg[index]" 
            class="compact-slider"
          />
          
          <button class="unified-btn arm-step-btn" @click="stepJoint(index, 5)">
            <div>+</div>
          </button>
          
          <input 
            type="number"
            class="joint-val-input"
            v-model.number="targetJointAnglesDeg[index]"
            step="0.5"
            :min="limit.min"
            :max="limit.max"
          />
          <span style="font-size: 10px; color: var(--text-muted);">°</span>
        </div>
      </div>

      <div class="custom-pose-grid">
        <input type="text" v-model="newPoseName" placeholder="Pose name..." class="map-input compact-input" />
        <button class="cmd-btn compact-btn" @click="syncSlidersToRobot">SYNC</button>
        <button class="cmd-btn compact-btn" @click="savePose">SAVE</button>
        
        <div class="custom-select-wrapper">
          <div class="map-input compact-input custom-select-box" @click="dropdownOpen = !dropdownOpen">
            <span>{{ selectedPoseIndex === -1 ? '-- Select Saved Pose --' : savedPoses[selectedPoseIndex]?.name }}</span>
            <span style="font-size: 10px;">▼</span>
          </div>
          <div class="custom-select-list" v-if="dropdownOpen">
            <div class="custom-select-item" @click="selectPose(-1)">-- Select Saved Pose --</div>
            <div class="custom-select-item" v-for="(pose, idx) in savedPoses" :key="idx" @click="selectPose(idx)">
              <span>{{ pose.name }}</span>
              <span class="del-icon" @click.stop="deletePoseIdx(idx)">✖</span>
            </div>
          </div>
        </div>
        
        <div class="time-wrap">
          <input type="number" v-model.number="executeDuration" step="0.5" min="0.5" class="map-input compact-input time-input no-arrows" />
          <span class="time-s">s</span>
        </div>
        
        <button class="cmd-btn compact-btn" @click="executeJoints(false)">RUN</button>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import * as ROSLIB from 'roslib'
import { getRosInstance } from '../../services/rosConnection'
import { useRosStore } from '../../stores/rosStore'

const store = useRosStore()

const jointLimits = [
  {min: -90, max: 90},
  {min: -5.0, max: 180},
  {min: -180, max: 5.0},
  {min: -90, max: 90},
  {min: -90, max: 90},
  {min: -90, max: 90}
]

const currentJointAnglesRad = ref([0, 0, 0, 0, 0, 0])
const targetJointAnglesDeg = ref([0, 0, 0, 0, 0, 0])

const executeDuration = ref(3.0)
const newPoseName = ref('')
const selectedPoseIndex = ref(-1)
const savedPoses = ref([])
const dropdownOpen = ref(false)

let jointSub = null
let trajPub = null
let tfClient = null

const setupRos = () => {
  const ros = getRosInstance()
  if (!ros) return

  if (!jointSub) {
    jointSub = new ROSLIB.Topic({
      ros: ros,
      name: '/joint_states',
      messageType: 'sensor_msgs/JointState'
    })
    let lastJointUpdate = 0
    jointSub.subscribe((msg) => {
      const now = performance.now()
      if (now - lastJointUpdate < 100) return // 10Hz max
      lastJointUpdate = now
      
      const names = msg.name
      const positions = msg.position
      
      let updated = false
      const newAngles = [...currentJointAnglesRad.value]
      for (let i = 0; i < 6; i++) {
        const idx = names.indexOf(`arm_joint_${i}`)
        if (idx !== -1) {
          newAngles[i] = positions[idx]
          updated = true
        }
      }
      if (updated) currentJointAnglesRad.value = newAngles
    })
  }

  if (!trajPub) {
    trajPub = new ROSLIB.Topic({
      ros: ros,
      name: '/arm_controller/joint_trajectory',
      messageType: 'trajectory_msgs/JointTrajectory'
    })
  }
}

const cleanupRos = () => {
  if (jointSub) {
    jointSub.unsubscribe()
    jointSub = null
  }
  trajPub = null
}

onMounted(() => {
  if (store.isConnected) {
    setupRos()
  }
  const saved = localStorage.getItem('arm_saved_poses')
  if (saved) {
    try {
      savedPoses.value = JSON.parse(saved)
    } catch (e) {
      console.error('Failed to parse saved poses', e)
    }
  }
})

watch(() => store.isConnected, (newVal) => {
  if (newVal) {
    setupRos()
  } else {
    cleanupRos()
  }
})

onBeforeUnmount(() => {
  cleanupRos()
})

const syncSlidersToRobot = () => {
  for (let i = 0; i < 6; i++) {
    let deg = currentJointAnglesRad.value[i] * 180.0 / Math.PI
    if (deg > jointLimits[i].max) deg = jointLimits[i].max
    if (deg < jointLimits[i].min) deg = jointLimits[i].min
    targetJointAnglesDeg.value[i] = Math.round(deg * 10) / 10
  }
}

const stepJoint = (index, degStep) => {
  for (let i = 0; i < 6; i++) {
    let deg = currentJointAnglesRad.value[i] * 180.0 / Math.PI
    targetJointAnglesDeg.value[i] = Math.round(deg * 10) / 10
  }
  
  let targetDeg = targetJointAnglesDeg.value[index] + degStep
  
  if (targetDeg > jointLimits[index].max) targetDeg = jointLimits[index].max
  if (targetDeg < jointLimits[index].min) targetDeg = jointLimits[index].min
  
  targetJointAnglesDeg.value[index] = Math.round(targetDeg * 10) / 10
  
  executeJoints(true, 0.5)
}

const executeJoints = (isImmediate = false, immediateDuration = 0.5) => {
  if (!trajPub) return

  let d = isImmediate ? immediateDuration : executeDuration.value
  const targetRad = targetJointAnglesDeg.value.map(deg => deg * Math.PI / 180.0)
  
  const sec = Math.floor(d)
  const nanosec = Math.floor((d % 1) * 1000000000)
  
  const msg = {
    header: { stamp: {sec: 0, nanosec: 0}, frame_id: '' },
    joint_names: ['arm_joint_0', 'arm_joint_1', 'arm_joint_2', 'arm_joint_3', 'arm_joint_4', 'arm_joint_5'],
    points: [{
      positions: targetRad,
      velocities: [],
      accelerations: [],
      effort: [],
      time_from_start: { sec: sec, nanosec: nanosec }
    }]
  }
  
  trajPub.publish(msg)
}

const savePose = () => {
  let name = newPoseName.value.trim()
  if (!name) {
    name = "Pose " + (savedPoses.value.length + 1)
  }
  
  savedPoses.value.push({
    name: name,
    deg: [...targetJointAnglesDeg.value]
  })
  
  localStorage.setItem('arm_saved_poses', JSON.stringify(savedPoses.value))
  
  newPoseName.value = ''
  selectedPoseIndex.value = savedPoses.value.length - 1
}

const selectPose = (idx) => {
  selectedPoseIndex.value = idx
  dropdownOpen.value = false
  if (idx === -1 || !savedPoses.value[idx]) return
  const pose = savedPoses.value[idx]
  
  for (let i = 0; i < 6; i++) {
    targetJointAnglesDeg.value[i] = pose.deg[i]
  }
}

const deletePoseIdx = (idx) => {
  savedPoses.value.splice(idx, 1)
  localStorage.setItem('arm_saved_poses', JSON.stringify(savedPoses.value))
  if (selectedPoseIndex.value === idx) {
    selectedPoseIndex.value = -1
  } else if (selectedPoseIndex.value > idx) {
    selectedPoseIndex.value--
  }
}
</script>

<style scoped>
.arm-control {
  display: flex;
  justify-content: flex-start;
}

.arm-inner {
  width: 100%;
  max-width: 420px; /* Fixed width, very compact */
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.joint-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.joint-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.joint-lbl {
  font-weight: bold;
  color: var(--accent);
  width: 18px;
  font-size: 0.85em;
}

.arm-step-btn {
  width: 24px !important;
  height: 24px !important;
  min-height: 24px !important;
  padding: 0 !important;
  font-size: 0.9em;
  font-weight: bold;
  border-radius: 4px;
}

.compact-slider {
  flex-grow: 1;
  height: 4px;
  accent-color: var(--accent);
  margin: 0 4px;
}

.joint-val-input {
  width: 45px;
  text-align: center;
  font-family: monospace;
  font-size: 0.85em;
  padding: 2px 4px;
  background: transparent;
  border: 1px solid var(--input-border);
  color: var(--text);
  border-radius: 4px;
  -moz-appearance: textfield;
}
/* hide number arrows */
.joint-val-input::-webkit-outer-spin-button,
.joint-val-input::-webkit-inner-spin-button,
.no-arrows::-webkit-outer-spin-button,
.no-arrows::-webkit-inner-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
.no-arrows {
  -moz-appearance: textfield;
}

.custom-pose-grid {
  display: grid;
  grid-template-columns: 1fr 65px 65px;
  gap: 8px;
  align-items: center;
}

.time-wrap {
  position: relative;
  display: flex;
  align-items: center;
}
.time-input {
  width: 100%;
  text-align: center;
  background: transparent !important;
  padding-right: 15px !important;
}
.time-s {
  position: absolute;
  right: 8px;
  color: var(--text-muted);
  font-size: 10px;
  pointer-events: none;
}

.custom-select-wrapper {
  position: relative;
  width: 100%;
}
.custom-select-box {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  user-select: none;
}
.custom-select-list {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: var(--dark-bg);
  border: 1px solid var(--input-border);
  border-radius: 4px;
  max-height: 150px;
  overflow-y: auto;
  z-index: 1000;
  margin-top: 2px;
  box-shadow: 0 4px 6px rgba(0,0,0,0.3);
}
.custom-select-item {
  padding: 6px 10px;
  font-size: 12px;
  color: var(--text);
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.custom-select-item:hover {
  background: var(--hover-bg, #333);
}
.del-icon {
  color: var(--red);
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
}
.del-icon:hover {
  background: rgba(255, 0, 0, 0.2);
}


</style>
