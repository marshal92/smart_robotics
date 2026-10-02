<template>
  <div ref="wrapper" class="dt-wrapper">
    <!-- absolute inset-0 prevents the canvas from stretching the parent -->
    <div id="viewer3d" class="dt-viewer"></div>
    
    <!-- Fullscreen Button -->
    <button class="fullscreen-btn" @click="toggleFullscreen" title="Fullscreen">⛶</button>
    
    <!-- Bottom Control Panel -->
    <div class="dt-bottom-panel">
      
      <!-- Left: Coordinates -->
      <div class="dt-coords">
        <div v-if="hoverCoords" class="coord-line">
          <span class="coord-lbl">Cur:</span> X: {{ hoverCoords.x.toFixed(2) }} <span>|</span> Y: {{ hoverCoords.y.toFixed(2) }}
        </div>
        <div v-else class="dt-coords-empty">
          Hover map...
        </div>
        <div v-if="robotCoords" class="coord-line" style="color: var(--accent); margin-top: 2px;">
          <span class="coord-lbl">Rob:</span> X: {{ robotCoords.x.toFixed(2) }} <span>|</span> Y: {{ robotCoords.y.toFixed(2) }}
        </div>
      </div>

      <!-- Center/Right: Action Buttons -->
      <div class="dt-actions">
        <!-- 3D World Toggle with Context Menu for Worlds -->
        <div style="position: relative; display: inline-block;">
          <button 
            @click="toggle3DWorld"
            @contextmenu.prevent="showWorldMenu = !showWorldMenu"
            :class="['dt-btn', show3DWorld ? 'dt-btn-active-blue' : 'dt-btn-inactive']"
          >
            <span>3D View</span>
          </button>
          
          <div v-if="showWorldMenu" class="world-menu">
            <div class="world-menu-item" @click="loadWorld('213')">213.sdf</div>
            <div class="world-menu-item" @click="loadWorld('kitchen')">kitchen.sdf</div>
            <div class="world-menu-item" @click="loadWorld('shelter_zero')">shelter_zero.sdf</div>
            <div class="world-menu-item" @click="loadWorld('shelter_zero_empty')">shelter_zero_empty.sdf</div>
            <div class="world-menu-slider" style="padding: 10px; border-top: 1px solid #444;">
              <div style="display: flex; justify-content: space-between; margin-bottom: 5px; font-size: 12px; color: #ccc;">
                <span>Opacity</span>
                <span>{{ Math.round(sdfOpacity * 100) }}%</span>
              </div>
              <input type="range" min="0.1" max="1.0" step="0.1" v-model.number="sdfOpacity" @change="updateSDFOpacity" style="width: 100%;">
            </div>
          </div>
        </div>

        <!-- Radiation Toggle -->
        <button 
          @click="toggleRadiation"
          :class="['dt-btn', showRadiation ? 'dt-btn-active-blue' : 'dt-btn-inactive']"
        >
          <span>Radiation</span>
        </button>

        <!-- Waypoints Toggle -->
        <button 
          @click="toggleWaypoints"
          :class="['dt-btn', showWaypoints ? 'dt-btn-active-blue' : 'dt-btn-inactive']"
        >
          <span>Waypoints</span>
        </button>

        <!-- Shadow Toggle -->
        <button 
          @click="toggleShadow"
          :class="['dt-btn', showShadowRobot ? 'dt-btn-active-blue' : 'dt-btn-inactive']"
        >
          <span>Shadow</span>
        </button>

        <!-- Speed Toggle with Context Menu -->
        <div style="position: relative; display: inline-block;">
          <button 
            @click="showSpeedMenu = !showSpeedMenu"
            :class="['dt-btn', showSpeedMenu ? 'dt-btn-active-blue' : 'dt-btn-inactive']"
            style="min-width: 65px;"
          >
            <span>v: {{ maxSpeed.toFixed(1) }}</span>
          </button>
          
          <div v-if="showSpeedMenu" class="world-menu" style="bottom: 110%;">
            <div class="world-menu-slider" style="padding: 10px;">
              <div style="display: flex; justify-content: space-between; margin-bottom: 5px; font-size: 12px; color: #ccc;">
                <span>Max Speed</span>
                <span>{{ maxSpeed.toFixed(1) }} m/s</span>
              </div>
              <input 
                type="range" 
                min="0.1" 
                max="2.0" 
                step="0.1" 
                v-model.number="tempMaxSpeed" 
                @change="applyMaxSpeed"
                style="width: 100%;"
                :disabled="isSettingSpeed"
              >
            </div>
          </div>
        </div>

        <!-- Nav Goal Toggle -->
        <button 
          @click="toggleNavMode"
          :class="['dt-btn', isNavMode ? 'dt-btn-active-blue' : 'dt-btn-inactive']"
        >
          <span>{{ isNavMode ? 'Click & Drag...' : 'Nav Goal' }}</span>
        </button>
      </div>

    </div>

    <!-- Nav Mode Hint overlay -->
    <div v-if="isNavMode" class="dt-nav-hint">
      Click to set position, drag for orientation
    </div>
  </div>
</template>

<script setup>
import { onMounted, watch, ref, onBeforeUnmount } from 'vue'
import { useRosStore } from '../../stores/rosStore'
import { getRosInstance } from '../../services/rosConnection'
import * as ROSLIB from 'roslib'
import * as THREE from 'three'
import { STLLoader } from 'three/addons/loaders/STLLoader.js'
import { createViewer } from '../../three/createViewer'
import { SimpleTFClient } from '../../services/simpleTfClient'
import { createURDFRobot } from '../../three/robotModel'
import { useSdfWorlds } from './composables/useSdfWorlds'
import { useMapLayer } from './composables/useMapLayer'
import { useRadiationMap } from './composables/useRadiationMap'
import { useWaypoints } from './composables/useWaypoints'
import { useNavSpeed } from './composables/useNavSpeed'

const store = useRosStore()
const viewerInitialized = ref(false)
const hoverCoords = ref(null)
const isNavMode = ref(false)
const showShadowRobot = ref(false)
const showWorldMenu = ref(false)
const showSpeedMenu = ref(false)
const wrapper = ref(null)
const robotCoords = ref(null)

const toggleFullscreen = () => {
  if (!document.fullscreenElement) {
    if (wrapper.value.requestFullscreen) {
      wrapper.value.requestFullscreen()
    }
  } else {
    if (document.exitFullscreen) {
      document.exitFullscreen()
    }
  }
}

let viewer = null
let tfClient = null
let navGoalArrow = null 

let urdfModel = null

let robotGroup = new THREE.Group()
let shadowGroup = new THREE.Group()

const viewerRef = ref(null)
const {
  show3DWorld,
  sdfOpacity,
  loadSDFWorld,
  updateSDFOpacity,
  toggle3DWorld,
  disposeSDFWorld
} = useSdfWorlds(viewerRef)

const {
  setupMap,
  getMapPlane,
  getMapResolution,
  getMapOrigin,
  getMapOrientation,
  disposeMap
} = useMapLayer(viewerRef)

const {
  showRadiation,
  setupRadiation,
  toggleRadiation,
  disposeRadiation
} = useRadiationMap(viewerRef, getMapResolution, getMapOrigin, getMapOrientation)

const {
  showWaypoints,
  setupWaypoints,
  toggleWaypoints,
  disposeWaypoints
} = useWaypoints(viewerRef)

const {
  maxSpeed,
  isSettingSpeed,
  setMaxSpeed
} = useNavSpeed()

const tempMaxSpeed = ref(maxSpeed.value)

function applyMaxSpeed() {
  const ros = getRosInstance()
  if (ros) {
    setMaxSpeed(ros, tempMaxSpeed.value)
  }
}

function loadWorld(name) {
  showWorldMenu.value = false
  loadSDFWorld(name)
}


function toggleNavMode() {
  isNavMode.value = !isNavMode.value
}


function toggleShadow() {
  showShadowRobot.value = !showShadowRobot.value
  if (viewer && viewer.shadowGroup) {
    viewer.shadowGroup.visible = showShadowRobot.value
  }
}

onMounted(() => {
  createScene()
  if (store.isConnected) {
    connectSceneData()
  }
})

watch(() => store.isConnected, (newVal) => {
  if (newVal && !viewerInitialized.value) {
    connectSceneData()
  } else if (!newVal && viewerInitialized.value) {
    disconnectSceneData()
  }
})

// Track active topic subscriptions so we can unsubscribe on disconnect
let activeTopics = []

// Event handlers for navigation
let mouseMoveHandler = null
let touchStartHandler = null
let touchEndHandler = null
let themeChangedHandler = null

function disconnectSceneData() {
  console.log("Disconnecting Scene Data and cleaning up...")
  
  // Unsubscribe from all ROS topics
  activeTopics.forEach(topic => {
    if (topic && topic.unsubscribe) {
      topic.unsubscribe()
    }
  })
  activeTopics = []
  
  if (tfClient) {
    if (tfClient.dispose) tfClient.dispose()
    tfClient = null
  }
  
  if (urdfModel) {
    if (urdfModel.dispose) urdfModel.dispose()
    viewer.scene.remove(urdfModel)
    urdfModel = null
  }
  
  disposeWaypoints()
  disposeRadiation()
  disposeMap()
  disposeSDFWorld()
  
  // Remove phantom event listeners
  const container = document.getElementById('viewer3d')
  if (container) {
    if (mouseMoveHandler) container.removeEventListener('mousemove', mouseMoveHandler)
    container.removeEventListener('mousedown', handleDragStart, true)
    if (touchStartHandler) container.removeEventListener('touchstart', touchStartHandler, { passive: false })
  }
  window.removeEventListener('mouseup', handleDragEnd, true)
  if (touchEndHandler) window.removeEventListener('touchend', touchEndHandler, { passive: false })

  viewerInitialized.value = false
}

function createScene() {
  const container = document.getElementById('viewer3d')
  if (!container || !wrapper.value) return
  
  const rect = wrapper.value.getBoundingClientRect()
  const initWidth = rect.width || 800
  const initHeight = rect.height || 500

  const isLight = document.documentElement.classList.contains('light-theme')
  viewer = createViewer(container, {
    background: isLight ? 0x555555 : 0x111111
  })
  viewerRef.value = viewer

  window.addEventListener('theme-changed', (e) => {
    if (viewer) {
      viewer.setBackground(e.detail ? 0x555555 : 0x111111)
    }
  })
  
  // Enable shadows
  viewer.renderer.shadowMap.enabled = true
  viewer.renderer.shadowMap.type = THREE.PCFSoftShadowMap

  viewer.scene.add(robotGroup)
  
  shadowGroup.visible = showShadowRobot.value
  viewer.scene.add(shadowGroup)
  viewer.shadowGroup = shadowGroup // Store in viewer to access in loader
  
  const loader = new STLLoader()
  const meshUrl = 'http://' + window.location.hostname + ':8080/install/ugv_tracked_description/share/ugv_tracked_description/meshes/base.STL'
  
  loader.load(meshUrl, (geometry) => {
    // Fix missing normals from raw STL
    geometry.computeVertexNormals()
    
    // Removed manual robotMesh because urdfRobot now successfully loads the chassis via intercepted file:// paths!
    
    // === SHADOW ROBOT MESH ===
    const shadowMaterial = new THREE.MeshStandardMaterial({
      color: 0x00ffff,
      roughness: 0.8,
      metalness: 0.1,
      transparent: true,
      opacity: 0.5,
      depthWrite: false
    })
    const shadowMesh = new THREE.Mesh(geometry, shadowMaterial)
    shadowMesh.scale.set(0.001, 0.001, 0.001)
    shadowMesh.rotation.set(0, 0, 0)
    // Save reference to shadowMesh to update color later
    viewer.shadowRobotMesh = shadowMesh
    viewer.shadowGroup.add(shadowMesh)

  }, undefined, (error) => {
    console.error("Error loading STL:", error)
  })
}

function connectSceneData() {
  const container = document.getElementById('viewer3d')
  if (!container) return

  const ros = getRosInstance()
  if (!ros) return

  // 2. Setup SimpleTFClient
  tfClient = new SimpleTFClient({
    ros: ros,
    fixedFrame: 'map'
  })

  // 4. Setup TF update for Robot and Shadow
  let lastCoordUpdate = 0
  const updateRobotPose = (tf) => {
    robotGroup.position.set(tf.translation.x, tf.translation.y, tf.translation.z)
    robotGroup.quaternion.set(tf.rotation.x, tf.rotation.y, tf.rotation.z, tf.rotation.w)
    
    // Throttle Vue reactivity to 10Hz to prevent layout thrashing
    const now = performance.now()
    if (now - lastCoordUpdate > 100) {
      robotCoords.value = { x: tf.translation.x, y: tf.translation.y }
      lastCoordUpdate = now
    }
  }
  
  tfClient.subscribe('base_footprint', updateRobotPose)

  const updateShadowPose = (tf) => {
    shadowGroup.position.set(tf.translation.x, tf.translation.y, tf.translation.z)
    shadowGroup.quaternion.set(tf.rotation.x, tf.rotation.y, tf.rotation.z, tf.rotation.w)
  }
  tfClient.subscribe('shadow_base_link', updateShadowPose)
  
  // 4.1 Load URDF Robot
  if (urdfModel) urdfModel.dispose()
  urdfModel = createURDFRobot(ros, viewer, tfClient)

  // 5. Custom Fast Image Map Renderer
  setupMap(ros)

  setupRadiation(ros)

  // 6. Load SDF World initially
  loadSDFWorld('213')

  // 7. Interactive Map (Hover Coordinates & 2D Nav Goal Click-and-Drag)
  const raycaster = new THREE.Raycaster()
  const mouse = new THREE.Vector2()
  let dragStartPoint = null
  
  navGoalArrow = new THREE.Group()
  const arrowMat = new THREE.MeshBasicMaterial({ color: 0x10b981, side: THREE.DoubleSide, depthTest: false })
  
  // Single flat arrow shape
  const arrowShape = new THREE.Shape()
  arrowShape.moveTo(0, -0.05) // Start bottom
  arrowShape.lineTo(1, -0.05) // Shaft bottom
  arrowShape.lineTo(1, -0.2) // Arrow head bottom
  arrowShape.lineTo(1.3, 0) // Arrow tip
  arrowShape.lineTo(1, 0.2) // Arrow head top
  arrowShape.lineTo(1, 0.05) // Shaft top
  arrowShape.lineTo(0, 0.05) // Start top
  arrowShape.lineTo(0, -0.05) // Close

  const arrowGeo = new THREE.ShapeGeometry(arrowShape)
  const arrowMesh = new THREE.Mesh(arrowGeo, arrowMat)
  navGoalArrow.add(arrowMesh)
  navGoalArrow.renderOrder = 999 // Draw on top
  navGoalArrow.visible = false
  viewer.scene.add(navGoalArrow)

  const goalPub = new ROSLIB.Topic({
    ros: ros,
    name: '/goal_pose',
    messageType: 'geometry_msgs/msg/PoseStamped'
  })

  function getMapIntersection(event) {
    const mapPlane = getMapPlane()
    if (!mapPlane) return null
    const rect = container.getBoundingClientRect()
    let clientX = event.clientX
    let clientY = event.clientY
    
    if (event.touches && event.touches.length > 0) {
      clientX = event.touches[0].clientX
      clientY = event.touches[0].clientY
    } else if (event.changedTouches && event.changedTouches.length > 0) {
      clientX = event.changedTouches[0].clientX
      clientY = event.changedTouches[0].clientY
    }

    if (clientX === undefined || clientY === undefined) return null

    mouse.x = ((clientX - rect.left) / container.clientWidth) * 2 - 1
    mouse.y = -((clientY - rect.top) / container.clientHeight) * 2 + 1
    
    raycaster.setFromCamera(mouse, viewer.camera)
    const intersects = raycaster.intersectObject(mapPlane)
    return intersects.length > 0 ? intersects[0].point : null
  }

  mouseMoveHandler = (event) => {
    const point = getMapIntersection(event)
    if (point) {
      hoverCoords.value = { x: point.x, y: point.y }
    } else {
      hoverCoords.value = null
    }

    if (isNavMode.value && dragStartPoint) {
      event.stopPropagation() // Prevent OrbitControls rotation while dragging arrow
      event.preventDefault()
      
      const point = getMapIntersection(event)
      const dx = (point ? point.x : hoverCoords.value?.x || dragStartPoint.x) - dragStartPoint.x
      const dy = (point ? point.y : hoverCoords.value?.y || dragStartPoint.y) - dragStartPoint.y
      const length = Math.sqrt(dx*dx + dy*dy)
      if (length > 0.1) {
        const angle = Math.atan2(dy, dx)
        navGoalArrow.rotation.set(0, 0, angle)
        
        const totalLength = Math.max(length, 0.5)
        // Since arrow geometry is length 1 (shaft) + 0.3 (head), we scale X by totalLength / 1.3
        arrowMesh.scale.set(totalLength / 1.3, 1, 1)
        
        navGoalArrow.visible = true
      }
    }
  }
  container.addEventListener('mousemove', mouseMoveHandler, { passive: false })

  const handleDragStart = (event) => {
    if ((event.button !== undefined && event.button !== 0) || !isNavMode.value) return 
    
    const point = getMapIntersection(event)
    if (point) {
      event.stopPropagation() // Prevent OrbitControls rotation
      dragStartPoint = point
      navGoalArrow.position.copy(dragStartPoint)
      navGoalArrow.position.z += 0.05 
      
      arrowMesh.scale.set(0.1, 1, 1)
      
      navGoalArrow.visible = true
      if (viewer && viewer.controls) viewer.controls.enabled = false
    }
  }

  container.addEventListener('mousedown', handleDragStart, true)
  touchStartHandler = (e) => {
    if (isNavMode.value) e.preventDefault()
    handleDragStart(e)
  }
  container.addEventListener('touchstart', touchStartHandler, { passive: false })

  const handleDragEnd = (event) => {
    if (isNavMode.value && dragStartPoint) {
      event.stopPropagation() // Prevent OrbitControls issues on release
      
      let dragEndPoint = getMapIntersection(event)
      if (!dragEndPoint) {
        // If mouse released outside map, try to estimate from mouse pos or just use start point
        dragEndPoint = dragStartPoint
      }

      let yaw = 0
      const dx = dragEndPoint.x - dragStartPoint.x
      const dy = dragEndPoint.y - dragStartPoint.y
      
      if (Math.sqrt(dx*dx + dy*dy) > 0.1) {
        yaw = Math.atan2(dy, dx)
      } else {
        const robotRot = new THREE.Euler().setFromQuaternion(robotGroup.quaternion)
        yaw = robotRot.z
      }
      
      const q = new THREE.Quaternion().setFromEuler(new THREE.Euler(0, 0, yaw))
      
      const pose = {
        header: {
          stamp: { sec: 0, nanosec: 0 },
          frame_id: 'map'
        },
        pose: {
          position: { x: dragStartPoint.x, y: dragStartPoint.y, z: 0.0 },
          orientation: { x: q.x, y: q.y, z: q.z, w: q.w }
        }
      }
      goalPub.publish(pose)
      console.log(`Sent Nav Goal: X=${dragStartPoint.x.toFixed(2)}, Y=${dragStartPoint.y.toFixed(2)}, Yaw=${(yaw*180/Math.PI).toFixed(1)}°`)
      
      dragStartPoint = null
      navGoalArrow.visible = false
      if (viewer && viewer.controls) viewer.controls.enabled = true
      toggleNavMode() 
    }
  }

  window.addEventListener('mouseup', handleDragEnd, true)
  touchEndHandler = (e) => {
    if (isNavMode.value) e.preventDefault()
    handleDragEnd(e)
  }
  window.addEventListener('touchend', touchEndHandler, { passive: false })

  // 7. Parse Smart Waypoints Markers
  setupWaypoints(ros)

  // 8. Custom Navigation Path Visualization (Fixes ROS3D deprecated Geometry)
  let pathLine = null

  const pathSub = new ROSLIB.Topic({
    ros: ros,
    name: '/plan',
    messageType: 'nav_msgs/msg/Path'
  })
  activeTopics.push(pathSub)

  pathSub.subscribe((message) => {
    if (pathLine) {
      viewer.scene.remove(pathLine)
      pathLine.geometry.dispose()
      pathLine.material.dispose()
      pathLine = null
    }

    if (!message.poses || message.poses.length === 0) return

    const points = []
    message.poses.forEach(p => {
      // Lift the path slightly (Z + 0.02) so it doesn't Z-fight with the floor
      points.push(new THREE.Vector3(p.pose.position.x, p.pose.position.y, p.pose.position.z + 0.02))
    })

    const geometry = new THREE.BufferGeometry().setFromPoints(points)
    const material = new THREE.LineBasicMaterial({ 
      color: 0xffa500, // Bright orange
      linewidth: 3
    })

    pathLine = new THREE.Line(geometry, material)
    viewer.scene.add(pathLine)
  })

  // 9. Shadow Robot Marker Status (Color / Visibility)
  const shadowMarkerSub = new ROSLIB.Topic({
    ros: ros,
    name: '/shadow_marker',
    messageType: 'visualization_msgs/msg/Marker'
  })
  activeTopics.push(shadowMarkerSub)

  shadowMarkerSub.subscribe((msg) => {
    if (viewer.shadowRobotMesh) {
      const mat = viewer.shadowRobotMesh.material
      mat.color.setRGB(msg.color.r, msg.color.g, msg.color.b)
      mat.opacity = msg.color.a
      viewer.shadowRobotMesh.visible = (msg.color.a > 0.0 && msg.pose.position.z > -1.0)
    }
  })

  // 10. Shadow Path Visualization
  let shadowPathLine = null
  const shadowPathSub = new ROSLIB.Topic({
    ros: ros,
    name: '/shadow_path',
    messageType: 'nav_msgs/msg/Path'
  })
  activeTopics.push(shadowPathSub)

  shadowPathSub.subscribe((message) => {
    if (shadowPathLine) {
      viewer.scene.remove(shadowPathLine)
      shadowPathLine.geometry.dispose()
      shadowPathLine.material.dispose()
      shadowPathLine = null
    }
    if (!message.poses || message.poses.length === 0) return

    const points = []
    message.poses.forEach(p => {
      points.push(new THREE.Vector3(p.pose.position.x, p.pose.position.y, p.pose.position.z + 0.03))
    })

    const geometry = new THREE.BufferGeometry().setFromPoints(points)
    const material = new THREE.LineBasicMaterial({ color: 0x00ffff, linewidth: 3 })
    shadowPathLine = new THREE.Line(geometry, material)
    viewer.scene.add(shadowPathLine)
  })
  viewerInitialized.value = true
}

onBeforeUnmount(() => {
  if (urdfModel) {
    urdfModel.dispose()
    urdfModel = null
  }
  if (viewer) {
    viewer.dispose()
    viewer = null
  }
})
</script>

<style scoped>
.dt-wrapper {
  position: relative;
  width: 100%;
  flex-grow: 1;
  min-height: 500px; /* Base height */
  background-color: #111;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #333;
}

.fullscreen-btn {
  position: absolute;
  top: 10px;
  right: 10px;
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
  z-index: 100;
}
.fullscreen-btn:hover {
  background: rgba(0, 0, 0, 0.8);
}

.dt-viewer {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  width: 100%;
  height: 100%;
  background-color: #111111;
  isolation: isolate;
}
.dt-viewer canvas {
  display: block;
  background-color: #111111 !important;
  opacity: 1 !important;
  mix-blend-mode: normal !important;
  will-change: transform;
  transform: translateZ(0);
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
}

.dt-bottom-panel {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: var(--dt-panel-bg);
  backdrop-filter: blur(8px);
  border-top: 1px solid var(--console-border, #333);
  padding: 10px 15px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  z-index: 10;
  transition: background 0.3s, border-color 0.3s;
}

.dt-coords {
  font-family: monospace;
  color: #10b981;
  font-size: 14px;
  font-weight: 600;
  min-width: 150px;
}
.dt-coords span {
  color: #666;
  margin: 0 5px;
}
.dt-coords-empty {
  color: #777;
}

.dt-actions {
  display: flex;
  gap: 10px;
}

.dt-btn {
  padding: 8px 16px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid transparent;
}

.dt-btn-inactive {
  background: var(--btn-bg);
  color: var(--text);
  border-color: var(--input-border);
}
.dt-btn-inactive:hover {
  background: var(--input-bg);
}

.dt-btn-active-blue { background: var(--accent); color: white; border-color: var(--accent); box-shadow: 0 0 8px rgba(25, 118, 210, 0.5); }

.coord-line { font-size: 11px; }
.coord-lbl { opacity: 0.7; font-size: 10px; }

.dt-nav-hint {
  position: absolute;
  top: 15px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0, 77, 64, 0.9);
  color: #80cbc4;
  padding: 8px 20px;
  border-radius: 30px;
  border: 1px solid #00897b;
  font-weight: bold;
  font-size: 14px;
  z-index: 10;
  pointer-events: none;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% { box-shadow: 0 0 0 0 rgba(0, 137, 123, 0.7); }
  70% { box-shadow: 0 0 0 10px rgba(0, 137, 123, 0); }
  100% { box-shadow: 0 0 0 0 rgba(0, 137, 123, 0); }
}
.world-menu {
  position: absolute;
  bottom: 100%;
  left: 0;
  background: #222;
  border: 1px solid #444;
  border-radius: 6px;
  box-shadow: 0 -4px 8px rgba(0,0,0,0.5);
  margin-bottom: 5px;
  z-index: 100;
  min-width: 120px;
  overflow: hidden;
}

.world-menu-item {
  padding: 8px 12px;
  font-size: 12px;
  font-weight: bold;
  color: #ddd;
  cursor: pointer;
  border-bottom: 1px solid #333;
}

.world-menu-item:last-child {
  border-bottom: none;
}

.world-menu-item:hover {
  background: var(--accent);
  color: white;
}
</style>
