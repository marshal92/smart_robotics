<template>
  <div ref="wrapper" class="dt-wrapper">
    <!-- absolute inset-0 prevents the canvas from stretching the parent -->
    <div id="viewer3d" :class="['dt-viewer', { 'is-nav-mode': isNavMode }]"></div>
    
    <!-- Center & Follow Camera on Robot Button -->
    <button
      class="center-cam-btn"
      :class="{ 'is-active': isFollowingRobot }"
      @click="toggleFollowAndCenter"
      :title="isFollowingRobot ? 'Following Robot (click to disable)' : 'Center & Follow Robot'"
      :aria-pressed="isFollowingRobot"
      aria-label="Center and Follow Robot"
    >
      <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="3"/>
        <path d="M12 2v4M12 18v4M2 12h4M18 12h4"/>
      </svg>
      <span v-if="isFollowingRobot" class="follow-label">FOLLOW</span>
    </button>

    <!-- Fullscreen Button -->
    <button class="fullscreen-btn" @click="toggleFullscreen" title="Fullscreen">⛶</button>
    
    <!-- Floating Navigation Goal Target Button (Right side over 3D canvas) -->
    <button 
      class="floating-goal-btn" 
      :class="{ 'is-active': isNavMode }"
      @click="toggleNavMode" 
      title="Set Navigation Goal (Target Mode)"
      aria-label="Set Navigation Goal"
    >
      <svg class="target-icon" viewBox="0 0 24 24" width="42" height="42" fill="currentColor">
        <path d="M12 8c-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4-1.79-4-4-4zm8.94 3A8.994 8.994 0 0 0 13 3.06V1h-2v2.06A8.994 8.994 0 0 0 3.06 11H1v2h2.06A8.994 8.994 0 0 0 11 20.94V23h2v-2.06A8.994 8.994 0 0 0 20.94 13H23v-2h-2.06zM12 19c-3.87 0-7-3.13-7-7s3.13-7 7-7 7 3.13 7 7-3.13 7-7 7z"/>
      </svg>
    </button>
    
    <!-- Camera Overlay -->
    <div v-if="showCam" class="cam-popup">
      <CameraStream />
    </div>
    
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
        <!-- CAM Toggle -->
        <button 
          @click="showCam = !showCam"
          :class="['dt-btn', showCam ? 'dt-btn-active-blue' : 'dt-btn-inactive']"
        >
          <span>camera</span>
        </button>

        <!-- NAV Popup Toggle -->
        <button 
          @click="showNavPopup = !showNavPopup"
          :class="['dt-btn', showNavPopup ? 'dt-btn-active-blue' : 'dt-btn-inactive']"
        >
          <span>NAV</span>
        </button>

        <!-- 3D World Toggle & Model Selector -->
        <div style="position: relative; display: inline-block;">
          <button 
            @click="showWorldMenu = !showWorldMenu"
            :class="['dt-btn', (show3DWorld || showWorldMenu) ? 'dt-btn-active-blue' : 'dt-btn-inactive']"
            title="3D World SDF Models"
          >
            <span>3D ▾</span>
          </button>
          
          <div v-if="showWorldMenu" class="world-menu" style="bottom: calc(100% + 6px); left: 0;">
            <div class="world-menu-header">
              <span>SDF WORLDS</span>
              <button class="btn-world-visibility" @click.stop="toggle3DWorld">
                {{ show3DWorld ? 'Hide World' : 'Show World' }}
              </button>
            </div>
            <div class="world-menu-item" @click="loadWorld('213')">213.sdf</div>
            <div class="world-menu-item" @click="loadWorld('kitchen')">kitchen.sdf</div>
            <div class="world-menu-item" @click="loadWorld('shelter_zero')">shelter_zero.sdf</div>
            <div class="world-menu-item" @click="loadWorld('shelter_zero_empty')">shelter_zero_empty.sdf</div>
            <div class="world-menu-item" @click="loadWorld('shelter_zero_map')">shelter_zero_map.sdf</div>
            <div class="world-menu-slider">
              <div style="display: flex; justify-content: space-between; margin-bottom: 4px; font-size: 11px; color: var(--muted);">
                <span>Opacity</span>
                <span>{{ Math.round(sdfOpacity * 100) }}%</span>
              </div>
              <input type="range" min="0.1" max="1.0" step="0.1" v-model.number="sdfOpacity" @input="updateSDFOpacity" @change="updateSDFOpacity" style="width: 100%;">
            </div>
          </div>
        </div>

        <!-- Waypoints Toggle -->
        <button 
          @click="toggleWaypoints"
          :class="['dt-btn', showWaypoints ? 'dt-btn-active-blue' : 'dt-btn-inactive']"
        >
          <span>WP</span>
        </button>

        <!-- Radiation Toggle -->
        <button 
          @click="toggleRadiation"
          :class="['dt-btn', showRadiation ? 'dt-btn-active-blue' : 'dt-btn-inactive']"
        >
          <span>radiation</span>
        </button>

        <!-- Shadow Toggle -->
        <button 
          @click="toggleShadow"
          :class="['dt-btn', showShadowRobot ? 'dt-btn-active-blue' : 'dt-btn-inactive']"
        >
          <span>SHADOW</span>
        </button>

        <!-- Touch Joystick Toggle -->
        <button
          @click="showJoystick = !showJoystick"
          :class="['dt-btn', showJoystick ? 'dt-btn-active-blue' : 'dt-btn-inactive']"
          title="Toggle On-Screen Touch Joystick"
        >
          <span>JOYSTICK</span>
        </button>

        <!-- Speed Limiter Toggle -->
        <div style="position: relative; display: inline-block;">
          <button 
            @click="showSpeedMenu = !showSpeedMenu"
            :class="['dt-btn', showSpeedMenu ? 'dt-btn-active-blue' : 'dt-btn-inactive']"
            title="Max Speed Limiter"
          >
            <span>velocity ▾</span>
          </button>
          
          <div v-if="showSpeedMenu" class="world-menu" style="bottom: calc(100% + 6px); right: 0;">
            <div class="world-menu-header">
              <span>MAX SPEED</span>
              <span class="mono" style="color: var(--accent); font-weight: 700;">{{ maxSpeed.toFixed(1) }} m/s</span>
            </div>
            <div class="world-menu-slider">
              <input 
                type="range" 
                min="0.1" 
                max="2.0" 
                step="0.1" 
                v-model.number="tempMaxSpeed" 
                @input="applyMaxSpeed"
                @change="applyMaxSpeed" 
                style="width: 100%;"
                :disabled="isSettingSpeed"
              >
            </div>
          </div>
        </div>
      </div>

    </div>

    <!-- Touch Virtual Joystick Overlay -->
    <TouchJoystick v-if="showJoystick" class="dt-joystick" />

    <!-- Nav Popup Overlay -->
    <NavPopup v-if="showNavPopup" @close="showNavPopup = false" />

    <!-- Nav Mode Hint overlay -->
    <div v-if="isNavMode" class="dt-nav-hint">
      Tap / click to set position, drag for orientation
    </div>
  </div>
</template>

<script setup>
import { onMounted, watch, ref, onBeforeUnmount } from 'vue'
import { useRosStore } from '../../stores/rosStore'
import { getRosInstance, pubSmartCommand } from '../../services/rosConnection'
import NavPopup from './NavPopup.vue'
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
import CameraStream from '../teleop/CameraStream.vue'
import TouchJoystick from '../teleop/TouchJoystick.vue'

const store = useRosStore()
const viewerInitialized = ref(false)
const hoverCoords = ref(null)
const isNavMode = ref(false)
const isFollowingRobot = ref(false)
const showShadowRobot = ref(false)
const showJoystick = ref(false)
const showWorldMenu = ref(false)
const showSpeedMenu = ref(false)
const showNavPopup = ref(false)
const showCam = ref(false)
const wrapper = ref(null)
const robotCoords = ref(null)
let lastFollowedTarget = null

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

const centerCameraOnRobot = () => {
  if (!viewer || !viewer.controls || !viewer.camera) return
  const targetPos = new THREE.Vector3(
    robotGroup.position.x,
    robotGroup.position.y,
    robotGroup.position.z + 0.3
  )
  const offset = viewer.camera.position.clone().sub(viewer.controls.target)
  if (offset.lengthSq() < 0.01) {
    offset.set(3, -4, 3)
  }
  viewer.controls.target.copy(targetPos)
  viewer.camera.position.copy(targetPos).add(offset)
  viewer.controls.update()
  lastFollowedTarget = targetPos.clone()
}

const toggleFollowAndCenter = () => {
  isFollowingRobot.value = !isFollowingRobot.value
  if (isFollowingRobot.value) {
    centerCameraOnRobot()
  } else {
    lastFollowedTarget = null
  }
}

const goTo = (name) => {
  pubSmartCommand('nav', 'go_to_named', { name })
}

const cancelNav = () => {
  pubSmartCommand('nav', 'cancel', { x: 0, y: 0, yaw: 0 })
}

let viewer = null
let tfClient = null
let navGoalArrow = null
let pathLine = null
let shadowPathLine = null

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
  show3DWorld.value = true
  loadSDFWorld(name)
}


function toggleNavMode() {
  isNavMode.value = !isNavMode.value
  if (!isNavMode.value && abortActiveNavDrag) {
    abortActiveNavDrag()
  }
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
let hoverMoveHandler = null
let dragStartHandler = null
let dragMoveHandler = null
let dragEndHandler = null
let dragCancelHandler = null
let abortActiveNavDrag = null
let themeChangedHandler = null

function disposeThreeObject(obj) {
  if (!obj) return
  if (viewer && viewer.scene) {
    viewer.scene.remove(obj)
  }
  obj.traverse((child) => {
    if (child.geometry) child.geometry.dispose()
    if (child.material) {
      if (Array.isArray(child.material)) {
        child.material.forEach(m => m.dispose())
      } else {
        child.material.dispose()
      }
    }
  })
}

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
    urdfModel = null
  }

  disposeThreeObject(navGoalArrow)
  navGoalArrow = null
  disposeThreeObject(pathLine)
  pathLine = null
  disposeThreeObject(shadowPathLine)
  shadowPathLine = null
  
  disposeWaypoints()
  disposeRadiation()
  disposeMap()
  disposeSDFWorld()
  
  abortActiveNavDrag?.()
  abortActiveNavDrag = null

  // Remove event listeners safely using stored references
  const container = document.getElementById('viewer3d')
  if (container) {
    if (hoverMoveHandler) container.removeEventListener('pointermove', hoverMoveHandler)
    if (dragStartHandler) container.removeEventListener('pointerdown', dragStartHandler, true)
  }
  if (dragMoveHandler) window.removeEventListener('pointermove', dragMoveHandler, true)
  if (dragEndHandler) window.removeEventListener('pointerup', dragEndHandler, true)
  if (dragCancelHandler) window.removeEventListener('pointercancel', dragCancelHandler, true)

  hoverMoveHandler = null
  dragStartHandler = null
  dragMoveHandler = null
  dragEndHandler = null
  dragCancelHandler = null

  if (viewer && viewer.controls) {
    viewer.controls.enabled = true
  }
  isFollowingRobot.value = false
  lastFollowedTarget = null
  isNavMode.value = false
  hoverCoords.value = null
  robotCoords.value = null
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
    background: isLight ? 0xe2e8f0 : 0x0f1115
  })
  viewerRef.value = viewer

  themeChangedHandler = (e) => {
    if (viewer) {
      viewer.setBackground(e.detail ? 0xe2e8f0 : 0x0f1115)
    }
  }
  window.addEventListener('theme-changed', themeChangedHandler)
  
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
    if (!viewer || !viewer.shadowGroup) {
      geometry.dispose()
      return
    }
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

    if (isFollowingRobot.value && viewer && viewer.controls && viewer.camera) {
      const currentTarget = new THREE.Vector3(
        tf.translation.x,
        tf.translation.y,
        tf.translation.z + 0.3
      )
      if (lastFollowedTarget) {
        const delta = currentTarget.clone().sub(lastFollowedTarget)
        if (delta.lengthSq() > 1e-8) {
          viewer.controls.target.add(delta)
          viewer.camera.position.add(delta)
        }
      } else {
        const offset = viewer.camera.position.clone().sub(viewer.controls.target)
        viewer.controls.target.copy(currentTarget)
        viewer.camera.position.copy(currentTarget).add(offset)
      }
      lastFollowedTarget = currentTarget
    }

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

  const navFallbackPlane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0)
  const navFallbackHit = new THREE.Vector3()
  let activeNavPointerId = null

  function getPointerCoords(event) {
    let clientX = event.clientX
    let clientY = event.clientY
    if ((clientX === undefined || clientY === undefined) && event.touches?.length) {
      clientX = event.touches[0].clientX
      clientY = event.touches[0].clientY
    } else if ((clientX === undefined || clientY === undefined) && event.changedTouches?.length) {
      clientX = event.changedTouches[0].clientX
      clientY = event.changedTouches[0].clientY
    }
    return { clientX, clientY }
  }

  function getMapIntersection(event, allowGroundFallback = false, fallbackZ = null) {
    if (!viewer || !viewer.camera) return null
    const rect = container.getBoundingClientRect()
    if (!rect.width || !rect.height) return null

    const { clientX, clientY } = getPointerCoords(event)
    if (clientX === undefined || clientY === undefined) return null

    mouse.x = ((clientX - rect.left) / rect.width) * 2 - 1
    mouse.y = -((clientY - rect.top) / rect.height) * 2 + 1
    raycaster.setFromCamera(mouse, viewer.camera)

    const mapPlane = getMapPlane()
    if (mapPlane) {
      const intersects = raycaster.intersectObject(mapPlane)
      if (intersects.length > 0) {
        return intersects[0].point
      }
    }

    if (allowGroundFallback) {
      const planeZ = fallbackZ !== null ? fallbackZ : (mapPlane?.position?.z || 0)
      navFallbackPlane.constant = -planeZ
      const hit = raycaster.ray.intersectPlane(navFallbackPlane, navFallbackHit)
      return hit ? hit.clone() : null
    }

    return null
  }

  function releaseNavPointerCapture(pointerId) {
    if (pointerId === null || pointerId === undefined) return
    try {
      if (container.hasPointerCapture?.(pointerId)) {
        container.releasePointerCapture(pointerId)
      }
    } catch {
      // Ignore release failures when capture is already released
    }
  }

  function resetNavDragState() {
    releaseNavPointerCapture(activeNavPointerId)
    activeNavPointerId = null
    dragStartPoint = null
    navGoalArrow.visible = false
    if (viewer && viewer.controls) viewer.controls.enabled = true
  }

  abortActiveNavDrag = resetNavDragState

  let lastHoverUpdate = 0
  hoverMoveHandler = (event) => {
    if (activeNavPointerId !== null) return
    if (event.pointerType === 'touch' && !isNavMode.value) return

    const now = performance.now()
    if (now - lastHoverUpdate < 50) return // Throttle hover raycast to 20Hz
    lastHoverUpdate = now

    const point = getMapIntersection(event, false)
    hoverCoords.value = point ? { x: point.x, y: point.y } : null
  }
  container.addEventListener('pointermove', hoverMoveHandler, { passive: true })

  dragStartHandler = (event) => {
    if (!isNavMode.value) return
    if (event.pointerType === 'mouse' && event.button !== 0) return

    // Block extra fingers / OrbitControls from stealing gesture during active drag
    if (activeNavPointerId !== null) {
      event.stopPropagation()
      event.preventDefault()
      return
    }

    const point = getMapIntersection(event, true)
    if (!point) return

    event.stopPropagation()
    event.preventDefault()

    activeNavPointerId = event.pointerId
    try {
      container.setPointerCapture?.(event.pointerId)
    } catch {
      // Window capture listeners remain active if pointer capture is unsupported
    }

    dragStartPoint = point
    const robotRot = new THREE.Euler().setFromQuaternion(robotGroup.quaternion)
    navGoalArrow.position.copy(dragStartPoint)
    navGoalArrow.position.z += 0.05
    navGoalArrow.rotation.set(0, 0, robotRot.z)
    arrowMesh.scale.set(0.35, 1, 1)
    navGoalArrow.visible = true

    hoverCoords.value = { x: point.x, y: point.y }
    if (viewer && viewer.controls) viewer.controls.enabled = false
  }
  container.addEventListener('pointerdown', dragStartHandler, { capture: true, passive: false })

  dragMoveHandler = (event) => {
    if (!isNavMode.value || !dragStartPoint || event.pointerId !== activeNavPointerId) return

    event.stopPropagation()
    event.preventDefault()

    const point = getMapIntersection(event, true, dragStartPoint.z)
    if (!point) return

    hoverCoords.value = { x: point.x, y: point.y }
    const dx = point.x - dragStartPoint.x
    const dy = point.y - dragStartPoint.y
    const length = Math.hypot(dx, dy)

    if (length > 0.08) {
      const angle = Math.atan2(dy, dx)
      navGoalArrow.rotation.set(0, 0, angle)
      const totalLength = Math.max(length, 0.5)
      // Arrow geometry is length 1 (shaft) + 0.3 (head), so scale X by totalLength / 1.3
      arrowMesh.scale.set(totalLength / 1.3, 1, 1)
    } else {
      const robotRot = new THREE.Euler().setFromQuaternion(robotGroup.quaternion)
      navGoalArrow.rotation.set(0, 0, robotRot.z)
      arrowMesh.scale.set(0.35, 1, 1)
    }
    navGoalArrow.visible = true
  }
  window.addEventListener('pointermove', dragMoveHandler, { capture: true, passive: false })

  dragEndHandler = (event) => {
    if (!isNavMode.value || !dragStartPoint || event.pointerId !== activeNavPointerId) return

    event.stopPropagation()
    event.preventDefault()

    const dragEndPoint = getMapIntersection(event, true, dragStartPoint.z) || dragStartPoint
    const dx = dragEndPoint.x - dragStartPoint.x
    const dy = dragEndPoint.y - dragStartPoint.y

    let yaw = 0
    if (Math.hypot(dx, dy) > 0.08) {
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
    console.log(`Sent Nav Goal: X=${dragStartPoint.x.toFixed(2)}, Y=${dragStartPoint.y.toFixed(2)}, Yaw=${(yaw * 180 / Math.PI).toFixed(1)}°`)

    resetNavDragState()
    isNavMode.value = false
  }
  window.addEventListener('pointerup', dragEndHandler, { capture: true, passive: false })

  dragCancelHandler = (event) => {
    if (event.pointerId !== activeNavPointerId) return
    resetNavDragState()
  }
  window.addEventListener('pointercancel', dragCancelHandler, { capture: true, passive: false })

  // 7. Parse Smart Waypoints Markers
  setupWaypoints(ros)

  // 8. Custom Navigation Path Visualization (Fixes ROS3D deprecated Geometry)
  if (pathLine) {
    disposeThreeObject(pathLine)
    pathLine = null
  }

  const pathSub = new ROSLIB.Topic({
    ros: ros,
    name: '/plan',
    messageType: 'nav_msgs/msg/Path'
  })
  activeTopics.push(pathSub)

  pathSub.subscribe((message) => {
    if (pathLine) {
      disposeThreeObject(pathLine)
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
    if (viewer && viewer.shadowRobotMesh) {
      const mat = viewer.shadowRobotMesh.material
      mat.color.setRGB(msg.color.r, msg.color.g, msg.color.b)
      mat.opacity = msg.color.a
      viewer.shadowRobotMesh.visible = (msg.color.a > 0.0 && msg.pose.position.z > -1.0)
    }
  })

  // 10. Shadow Path Visualization
  if (shadowPathLine) {
    disposeThreeObject(shadowPathLine)
    shadowPathLine = null
  }
  const shadowPathSub = new ROSLIB.Topic({
    ros: ros,
    name: '/shadow_path',
    messageType: 'nav_msgs/msg/Path'
  })
  activeTopics.push(shadowPathSub)

  shadowPathSub.subscribe((message) => {
    if (shadowPathLine) {
      disposeThreeObject(shadowPathLine)
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
  if (themeChangedHandler) {
    window.removeEventListener('theme-changed', themeChangedHandler)
    themeChangedHandler = null
  }
  disconnectSceneData()
  if (urdfModel) {
    urdfModel.dispose()
    urdfModel = null
  }
  viewerRef.value = null
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
  height: 100%;
  flex-grow: 1;
  min-height: 240px;
  background-color: var(--dt-3d-bg);
  border-radius: 0;
  overflow: hidden;
  border: none;
}

.center-cam-btn,
.fullscreen-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  background: var(--bg-item);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 3px;
  width: 28px;
  height: 28px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  transition: 0.15s;
  z-index: 100;
}
.center-cam-btn {
  right: 42px;
  width: auto;
  min-width: 28px;
  padding: 0 7px;
  gap: 5px;
}
.center-cam-btn.is-active {
  background: rgba(37, 99, 235, 0.28);
  border-color: var(--accent);
  color: #ffffff;
  box-shadow: 0 0 8px rgba(59, 130, 246, 0.35);
}
.follow-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.5px;
  line-height: 1;
}
.center-cam-btn:hover,
.fullscreen-btn:hover {
  background: var(--bg-item-hover);
  border-color: var(--border-focus);
}
.center-cam-btn.is-active:hover {
  background: rgba(37, 99, 235, 0.42);
  border-color: var(--accent);
}

.dt-viewer {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  width: 100%;
  height: 100%;
  background-color: var(--dt-3d-bg);
  isolation: isolate;
}
.dt-viewer.is-nav-mode {
  touch-action: none;
  cursor: crosshair;
}
.dt-viewer canvas {
  display: block;
  background-color: var(--dt-3d-bg) !important;
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
  border-top: 1px solid var(--border);
  padding: 6px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  z-index: 30;
  overflow: visible;
  transition: background 0.2s, border-color 0.2s;
}

.dt-coords {
  font-family: 'JetBrains Mono', monospace;
  font-variant-numeric: tabular-nums;
  color: var(--green);
  font-size: 11px;
  font-weight: 600;
  min-width: 150px;
}
.dt-coords span {
  color: var(--muted);
  margin: 0 4px;
}
.dt-coords-empty {
  color: var(--muted);
}

.dt-actions {
  display: flex;
  gap: 4px;
  overflow: visible;
}

.dt-btn {
  padding: 4px 10px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s ease;
  border: 1px solid var(--border);
  text-transform: uppercase;
}

.dt-btn-inactive {
  background: var(--bg-item);
  color: var(--text);
  border-color: var(--border);
}
.dt-btn-inactive:hover {
  background: var(--bg-item-hover);
  border-color: var(--border-focus);
}

.dt-btn-active-blue { 
  background: var(--accent); 
  color: #ffffff; 
  border-color: var(--accent); 
  box-shadow: none; 
}

.coord-line { font-size: 11px; }
.coord-lbl { opacity: 0.7; font-size: 10px; }

.dt-nav-hint {
  position: absolute;
  top: 12px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(15, 23, 42, 0.9);
  color: #38bdf8;
  padding: 5px 14px;
  border-radius: 3px;
  border: 1px solid #0284c7;
  font-weight: 600;
  font-size: 12px;
  z-index: 10;
  pointer-events: none;
}

.world-menu {
  position: absolute;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: 3px;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.45);
  z-index: 1000;
  min-width: 170px;
  overflow: hidden;
}

.world-menu-header {
  padding: 5px 10px;
  font-size: 10px;
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  border-bottom: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--bg-item);
}

.btn-world-visibility {
  background: transparent;
  border: 1px solid var(--border);
  border-radius: 3px;
  color: var(--text);
  font-size: 9px;
  padding: 1px 5px;
  cursor: pointer;
}
.btn-world-visibility:hover {
  background: var(--bg-item-hover);
}

.world-menu-slider {
  padding: 8px 10px;
  border-top: 1px solid var(--border);
}

.world-menu-item {
  padding: 6px 10px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text);
  cursor: pointer;
  border-bottom: 1px solid var(--border);
}

.world-menu-item:last-child {
  border-bottom: none;
}

.world-menu-item:hover {
  background: var(--accent);
  color: #ffffff;
}

/* Floating Goal Target Button */
.floating-goal-btn {
  position: absolute;
  bottom: 55px;
  right: 16px;
  z-index: 15;
  background: transparent;
  color: var(--text);
  border: none;
  outline: none;
  border-radius: 6px;
  padding: 4px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: none;
  transition: all 0.15s ease;
  user-select: none;
  opacity: 0.85;
}
.floating-goal-btn:hover {
  opacity: 1;
  color: var(--accent);
  background: rgba(125, 125, 125, 0.15);
  transform: scale(1.05);
}
.floating-goal-btn.is-active {
  opacity: 1;
  color: var(--accent);
  background: rgba(37, 99, 235, 0.18);
  filter: drop-shadow(0 0 8px var(--accent));
}
.target-icon {
  display: block;
}

/* Virtual Touch Joystick Overlay */
.dt-joystick {
  position: absolute;
  bottom: 56px;
  left: 14px;
  z-index: 25;
}

/* Cam Popup Styles */
.cam-popup {
  position: absolute;
  top: 10px;
  left: 10px;
  width: 440px;
  max-width: calc(100% - 20px);
  border-radius: 3px;
  overflow: hidden;
  box-shadow: none;
  z-index: 50;
  border: 1px solid var(--border);
  background: var(--bg-panel);
}

@media (max-width: 768px) {
  .dt-bottom-panel {
    flex-wrap: wrap;
    gap: 5px;
    padding: 5px 8px;
  }
  .dt-coords {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
    min-width: 0;
    width: 100%;
    font-size: 10px;
  }
  .dt-coords .coord-line {
    margin-top: 0 !important;
  }
  .dt-actions {
    flex-wrap: wrap;
    gap: 4px;
  }
  .dt-btn {
    padding: 4px 7px;
    font-size: 10px;
  }
  .dt-joystick {
    bottom: 96px;
    left: 8px;
  }
  .floating-goal-btn {
    bottom: 96px;
    right: 10px;
  }
  .dt-nav-hint {
    top: 42px;
    font-size: 11px;
    padding: 4px 10px;
    max-width: calc(100% - 20px);
    text-align: center;
  }
}
</style>
