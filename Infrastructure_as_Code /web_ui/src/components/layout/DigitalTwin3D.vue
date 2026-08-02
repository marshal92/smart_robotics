<template>
  <div ref="wrapper" class="dt-wrapper">
    <!-- absolute inset-0 prevents the canvas from stretching the parent -->
    <div id="viewer3d" class="dt-viewer"></div>
    
    <!-- Bottom Control Panel -->
    <div class="dt-bottom-panel">
      
      <!-- Left: Coordinates -->
      <div class="dt-coords">
        <div v-if="hoverCoords">
          X: {{ hoverCoords.x.toFixed(2) }} <span>|</span> Y: {{ hoverCoords.y.toFixed(2) }}
        </div>
        <div v-else class="dt-coords-empty">
          Hover map...
        </div>
      </div>

      <!-- Center/Right: Action Buttons -->
      <div class="dt-actions">
        <!-- 3D World Toggle with Context Menu for Worlds -->
        <div style="position: relative; display: inline-block;">
          <button 
            @click="toggle3DWorld"
            @contextmenu.prevent="showWorldMenu = !showWorldMenu"
            :class="['dt-btn', show3DWorld ? 'dt-btn-active-purple' : 'dt-btn-inactive']"
          >
            <span>3D View</span>
          </button>
          
          <div v-if="showWorldMenu" class="world-menu">
            <div class="world-menu-item" @click="loadWorld('213')">213.sdf</div>
            <div class="world-menu-item" @click="loadWorld('kitchen')">kitchen.sdf</div>
            <div class="world-menu-item" @click="loadWorld('shelter_zero')">shelter_zero.sdf</div>
          </div>
        </div>

        <!-- Radiation Toggle -->
        <button 
          @click="toggleRadiation"
          :class="['dt-btn', showRadiation ? 'dt-btn-active-orange' : 'dt-btn-inactive']"
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
          :class="['dt-btn', showShadowRobot ? 'dt-btn-active-purple' : 'dt-btn-inactive']"
        >
          <span>Shadow</span>
        </button>

        <!-- Nav Goal Toggle -->
        <button 
          @click="toggleNavMode"
          :class="['dt-btn', isNavMode ? 'dt-btn-active-green' : 'dt-btn-inactive']"
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
import { onMounted, watch, ref } from 'vue'
import { useRosStore } from '../../stores/rosStore'
import { getRosInstance } from '../../services/rosConnection'
import * as ROS3D from 'ros3d'
import * as ROSLIB from 'roslib'
import * as THREE from 'three'
import { SimpleTFClient } from '../../services/simpleTfClient'

const store = useRosStore()
const viewerInitialized = ref(false)
const hoverCoords = ref(null)
const isNavMode = ref(false)
const showWaypoints = ref(true)
const showRadiation = ref(false)
const show3DWorld = ref(true)
const showShadowRobot = ref(true)
const showWorldMenu = ref(false)
const wrapper = ref(null)

let viewer = null
let tfClient = null
let navGoalArrow = null 
const waypointMeshes = {}
let radiationPlane = null
let sdfWorldGroup = null

// Load SDF World logic
const loadSDFWorld = (worldName) => {
  if (!viewer) return
  import('three/examples/js/loaders/STLLoader.js').then(() => {
    const worldUrl = 'http://' + window.location.hostname + ':8080/install/smart_sim2real/share/smart_sim2real/worlds/' + worldName + '.sdf'
    
    // Remove old world
    if (sdfWorldGroup) {
      viewer.scene.remove(sdfWorldGroup)
    }

    sdfWorldGroup = new THREE.Group()
    sdfWorldGroup.visible = show3DWorld.value
    viewer.scene.add(sdfWorldGroup)

    fetch(worldUrl)
      .then(response => response.text())
      .then(xmlString => {
        const parser = new DOMParser()
        const xmlDoc = parser.parseFromString(xmlString, 'text/xml')
        
        const models = xmlDoc.querySelectorAll('model')
        models.forEach(model => {
          const modelGroup = new THREE.Group()
          
          // Parse model pose
          const poseTags = model.querySelectorAll('pose')
          const mPoseTag = Array.from(poseTags).find(t => t.parentElement === model)
          if (mPoseTag) {
            const p = mPoseTag.textContent.trim().split(/\s+/).map(Number)
            modelGroup.position.set(p[0], p[1], p[2])
            modelGroup.rotation.set(p[3], p[4], p[5], 'ZYX')
          }
          sdfWorldGroup.add(modelGroup)
          
          // Parse links
          const links = model.querySelectorAll('link')
          links.forEach(link => {
            const linkGroup = new THREE.Group()
            
            const lPoseTag = Array.from(link.querySelectorAll('pose')).find(t => t.parentElement === link)
            if (lPoseTag) {
              const p = lPoseTag.textContent.trim().split(/\s+/).map(Number)
              linkGroup.position.set(p[0], p[1], p[2])
              linkGroup.rotation.set(p[3], p[4], p[5], 'ZYX')
            }
            modelGroup.add(linkGroup)
            
            // Parse visuals
            const visuals = link.querySelectorAll('visual')
            visuals.forEach(visual => {
              const meshTag = visual.querySelector('geometry mesh')
              if (!meshTag) return
              
              let uri = meshTag.querySelector('uri').textContent
              if (uri.includes('smart_sim2real')) {
                const parts = uri.split('smart_sim2real')
                const relativePath = parts[parts.length - 1]
                uri = 'http://' + window.location.hostname + ':8080/install/smart_sim2real/share/smart_sim2real' + relativePath
              }
              
              const loader = new window.THREE.STLLoader()
              loader.load(uri, (geometry) => {
                geometry.computeVertexNormals()
                
                let color = 0x888888
                const diffuseTag = visual.querySelector('material diffuse')
                const ambientTag = visual.querySelector('material ambient')
                const colorTag = diffuseTag || ambientTag
                if (colorTag) {
                  const rgba = colorTag.textContent.trim().split(/\s+/).map(Number)
                  color = new THREE.Color(rgba[0] * 0.6, rgba[1] * 0.6, rgba[2] * 0.6).getHex()
                }
                
                const material = new THREE.MeshStandardMaterial({
                  color: color,
                  roughness: 0.9,
                  metalness: 0.1,
                  depthWrite: true,
                  depthTest: true
                })
                
                const mesh = new THREE.Mesh(geometry, material)
                mesh.castShadow = true
                mesh.receiveShadow = true
                
                const vPoseTag = Array.from(visual.querySelectorAll('pose')).find(t => t.parentElement === visual)
                if (vPoseTag) {
                  const p = vPoseTag.textContent.trim().split(/\s+/).map(Number)
                  mesh.position.set(p[0], p[1], p[2])
                  mesh.rotation.set(p[3], p[4], p[5], 'ZYX')
                }
                
                const scaleTag = meshTag.querySelector('scale')
                if (scaleTag) {
                  const s = scaleTag.textContent.trim().split(/\s+/).map(Number)
                  mesh.scale.set(s[0], s[1], s[2])
                }
                
                linkGroup.add(mesh)
              })
            })
          })
        })
      })
      .catch(err => console.error('Failed to load SDF world:', err))
  })
}

function loadWorld(name) {
  showWorldMenu.value = false
  loadSDFWorld(name)
}

function toggleRadiation() {
  showRadiation.value = !showRadiation.value
  if (radiationPlane) {
    radiationPlane.visible = showRadiation.value
  }
}

function toggleNavMode() {
  isNavMode.value = !isNavMode.value
}

function toggleWaypoints() {
  showWaypoints.value = !showWaypoints.value
  for (let key in waypointMeshes) {
    waypointMeshes[key].visible = showWaypoints.value
  }
}

function toggleShadow() {
  showShadowRobot.value = !showShadowRobot.value
  if (viewer && viewer.shadowGroup) {
    viewer.shadowGroup.visible = showShadowRobot.value
  }
}

function toggle3DWorld() {
  show3DWorld.value = !show3DWorld.value
  if (sdfWorldGroup) {
    sdfWorldGroup.visible = show3DWorld.value
  }
}

onMounted(() => {
  if (store.isConnected) {
    initViewer()
  }
})

watch(() => store.isConnected, (newVal) => {
  if (newVal && !viewerInitialized.value) {
    initViewer()
  }
})

function initViewer() {
  const container = document.getElementById('viewer3d')
  if (!container || !wrapper.value) return
  
  const ros = getRosInstance()
  if (!ros) return

  const rect = wrapper.value.getBoundingClientRect()
  const initWidth = rect.width || 800
  const initHeight = rect.height || 500

  viewer = new ROS3D.Viewer({
    divID: 'viewer3d',
    width: initWidth,
    height: initHeight,
    antialias: true,
    background: '#111111',
    displayPanAndZoomFrame: false
  })
  
  // Safe resize listener that reacts to flexbox stretching
  const resizeObserver = new ResizeObserver(() => {
    if (viewer && wrapper.value) {
      const wRect = wrapper.value.getBoundingClientRect()
      if (wRect.width > 0 && wRect.height > 0) {
        viewer.resize(wRect.width, wRect.height)
      }
    }
  })
  resizeObserver.observe(wrapper.value)
  
  // Enable shadows
  viewer.renderer.shadowMap.enabled = true
  viewer.renderer.shadowMap.type = THREE.PCFSoftShadowMap
  
  // 2. Setup SimpleTFClient
  tfClient = new SimpleTFClient({
    ros: ros,
    fixedFrame: 'map'
  })

  // Ensure THREE is globally available for loaders
  window.THREE = Object.assign({}, THREE)

  // Fix ROS3D lighting bug: DirectionalLight is created at position (0,0,0).
  // The draw() loop calls normalize() every frame, but normalize(0,0,0) = (0,0,0)
  // → light has NO direction → scene is lit only by ambient = flat grey.
  // Setting a proper position gives the light a direction (normalize preserves it).
  viewer.scene.traverse(child => {
    if (child.type === 'AmbientLight') {
      child.color.setHex(0x444444) // Softer ambient
    }
    if (child.type === 'DirectionalLight') {
      child.intensity = 0.6
      child.position.set(10, 10, 20) // Good angle for shadows
      
      child.castShadow = true
      child.shadow.mapSize.width = 2048
      child.shadow.mapSize.height = 2048
      child.shadow.camera.near = 0.5
      child.shadow.camera.far = 100
      child.shadow.camera.left = -20
      child.shadow.camera.right = 20
      child.shadow.camera.top = 20
      child.shadow.camera.bottom = -20
      child.shadow.bias = -0.001
    }
  })
  
  const robotGroup = new THREE.Group()
  viewer.scene.add(robotGroup)
  
  import('three/examples/js/loaders/STLLoader.js').then(() => {
    const loader = new window.THREE.STLLoader()
    const meshUrl = 'http://' + window.location.hostname + ':8080/install/ugv_tracked_description/share/ugv_tracked_description/meshes/base.STL'
    
    loader.load(meshUrl, (geometry) => {
      // Fix missing normals from raw STL
      geometry.computeVertexNormals()
      
      const material = new THREE.MeshStandardMaterial({ 
        color: 0x1144aa,
        emissive: 0x0a1840,
        roughness: 0.6,
        metalness: 0.2,
        depthWrite: true,
        depthTest: true
      })
      const robotMesh = new THREE.Mesh(geometry, material)
      
      robotMesh.castShadow = true
      robotMesh.receiveShadow = true
      
      robotMesh.scale.set(0.001, 0.001, 0.001)
      robotMesh.rotation.set(0, 0, 0)
      
      robotGroup.add(robotMesh)

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
  }).catch(e => console.error("Failed to import STLLoader", e))

  // 4. Setup TF update for Robot and Shadow
  const updateRobotPose = (tf) => {
    robotGroup.position.set(tf.translation.x, tf.translation.y, tf.translation.z)
    robotGroup.quaternion.set(tf.rotation.x, tf.rotation.y, tf.rotation.z, tf.rotation.w)
  }
  
  tfClient.subscribe('base_link', updateRobotPose)
  tfClient.subscribe('base_footprint', updateRobotPose)

  // Initialize Shadow Group (TF tracking)
  const shadowGroup = new THREE.Group()
  viewer.scene.add(shadowGroup)
  viewer.shadowGroup = shadowGroup // Store in viewer to access in loader

  const updateShadowPose = (tf) => {
    shadowGroup.position.set(tf.translation.x, tf.translation.y, tf.translation.z)
    shadowGroup.quaternion.set(tf.rotation.x, tf.rotation.y, tf.rotation.z, tf.rotation.w)
  }
  tfClient.subscribe('shadow_base_link', updateShadowPose)

  // 5. Custom Fast Image Map Renderer
  let mapPlane = null
  let mapResolution = 0.05
  let mapOrigin = { x: 0, y: 0, z: 0 }
  let mapOrientation = { x: 0, y: 0, z: 0, w: 1 }

  const metaSub = new ROSLIB.Topic({
    ros: ros,
    name: '/map_metadata',
    messageType: 'nav_msgs/msg/MapMetaData'
  })
  
  metaSub.subscribe((msg) => {
    mapResolution = msg.resolution
    mapOrigin = msg.origin.position
    mapOrientation = msg.origin.orientation
  })
  
  const mapSub = new ROSLIB.Topic({
    ros: ros,
    name: '/map_image/compressed',
    messageType: 'sensor_msgs/msg/CompressedImage'
  })
  
  mapSub.subscribe((msg) => {
    const img = new Image()
    img.src = 'data:image/png;base64,' + msg.data
    img.onload = () => {
      const texture = new THREE.Texture(img)
      texture.needsUpdate = true
      texture.magFilter = THREE.NearestFilter
      texture.minFilter = THREE.NearestFilter
      
      const width = img.width * mapResolution
      const height = img.height * mapResolution
      const geometry = new THREE.PlaneGeometry(width, height)
      geometry.translate(width / 2, height / 2, 0)

      if (!mapPlane) {
        const material = new THREE.MeshLambertMaterial({ 
          color: 0x999999, // Darkens the map by reflecting less light
          map: texture,
          transparent: false,
          depthWrite: true, // Normal depth
          side: THREE.FrontSide
        })
        mapPlane = new THREE.Mesh(geometry, material)
        
        // Push map 5mm down to stop Z-fighting without making the robot float
        mapPlane.position.set(mapOrigin.x, mapOrigin.y, mapOrigin.z - 0.005)
        mapPlane.quaternion.set(mapOrientation.x, mapOrientation.y, mapOrientation.z, mapOrientation.w)
        
        // Receive shadows if we enable them later
        mapPlane.receiveShadow = true
        
        viewer.scene.add(mapPlane)
      } else {
        mapPlane.material.map.dispose()
        mapPlane.material.map = texture
        
        mapPlane.geometry.dispose()
        mapPlane.geometry = geometry
        mapPlane.position.set(mapOrigin.x, mapOrigin.y, mapOrigin.z - 0.005)
        mapPlane.quaternion.set(mapOrientation.x, mapOrientation.y, mapOrientation.z, mapOrientation.w)
      }
    }
  })

  // Radiation Overlay Plane
  const radSub = new ROSLIB.Topic({
    ros: ros,
    name: '/radiation_image/compressed',
    messageType: 'sensor_msgs/msg/CompressedImage'
  })
  
  radSub.subscribe((msg) => {
    const img = new Image()
    img.src = 'data:image/png;base64,' + msg.data
    img.onload = () => {
      const texture = new THREE.Texture(img)
      texture.needsUpdate = true
      texture.magFilter = THREE.NearestFilter
      texture.minFilter = THREE.NearestFilter
      
      const width = img.width * mapResolution
      const height = img.height * mapResolution
      const geometry = new THREE.PlaneGeometry(width, height)
      geometry.translate(width / 2, height / 2, 0)

      if (!radiationPlane) {
        const material = new THREE.MeshBasicMaterial({ 
          map: texture,
          transparent: true,
          opacity: 0.85,
          depthWrite: false, // Don't write to depth buffer to avoid Z-fighting
          side: THREE.FrontSide
        })
        radiationPlane = new THREE.Mesh(geometry, material)
        
        // Push radiation layer slightly above the map
        radiationPlane.position.set(mapOrigin.x, mapOrigin.y, mapOrigin.z + 0.005)
        radiationPlane.quaternion.set(mapOrientation.x, mapOrientation.y, mapOrientation.z, mapOrientation.w)
        radiationPlane.visible = showRadiation.value
        
        viewer.scene.add(radiationPlane)
      } else {
        radiationPlane.material.map.dispose()
        radiationPlane.material.map = texture
        
        radiationPlane.geometry.dispose()
        radiationPlane.geometry = geometry
        radiationPlane.position.set(mapOrigin.x, mapOrigin.y, mapOrigin.z + 0.005)
        radiationPlane.quaternion.set(mapOrientation.x, mapOrientation.y, mapOrientation.z, mapOrientation.w)
      }
    }
  })

  // 6. Load SDF World initially
  loadSDFWorld('213')

  // 7. Interactive Map (Hover Coordinates & 2D Nav Goal Click-and-Drag)
  const raycaster = new THREE.Raycaster()
  const mouse = new THREE.Vector2()
  let dragStartPoint = null
  
  navGoalArrow = new THREE.ArrowHelper(new THREE.Vector3(1,0,0), new THREE.Vector3(0,0,0), 1, 0x10b981, 0.4, 0.2)
  navGoalArrow.visible = false
  viewer.scene.add(navGoalArrow)

  const goalPub = new ROSLIB.Topic({
    ros: ros,
    name: '/goal_pose',
    messageType: 'geometry_msgs/msg/PoseStamped'
  })

  function getMapIntersection(event) {
    if (!mapPlane) return null
    const rect = container.getBoundingClientRect()
    mouse.x = ((event.clientX - rect.left) / container.clientWidth) * 2 - 1
    mouse.y = -((event.clientY - rect.top) / container.clientHeight) * 2 + 1
    
    raycaster.setFromCamera(mouse, viewer.camera)
    const intersects = raycaster.intersectObject(mapPlane)
    return intersects.length > 0 ? intersects[0].point : null
  }

  container.addEventListener('mousemove', (event) => {
    const point = getMapIntersection(event)
    if (point) {
      hoverCoords.value = { x: point.x, y: point.y }
    } else {
      hoverCoords.value = null
    }

    if (isNavMode.value && dragStartPoint) {
      event.stopPropagation() // Prevent OrbitControls rotation while dragging arrow
      
      const dx = (point ? point.x : hoverCoords.value?.x || dragStartPoint.x) - dragStartPoint.x
      const dy = (point ? point.y : hoverCoords.value?.y || dragStartPoint.y) - dragStartPoint.y
      const length = Math.sqrt(dx*dx + dy*dy)
      if (length > 0.1) {
        const dir = new THREE.Vector3(dx, dy, 0).normalize()
        navGoalArrow.setDirection(dir)
        navGoalArrow.setLength(Math.max(length, 0.5), 0.4, 0.2)
        navGoalArrow.visible = true
      }
    }
  }, true)

  container.addEventListener('mousedown', (event) => {
    if (event.button !== 0 || !isNavMode.value) return 
    
    const point = getMapIntersection(event)
    if (point) {
      event.stopPropagation() // Prevent OrbitControls rotation
      dragStartPoint = point
      navGoalArrow.position.copy(dragStartPoint)
      navGoalArrow.position.z += 0.1 
      navGoalArrow.setLength(0.5, 0.4, 0.2) 
      navGoalArrow.visible = true
    }
  }, true)

  container.addEventListener('mouseup', (event) => {
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
      toggleNavMode() 
    }
  }, true)

  // 7. Parse Smart Waypoints Markers
  const waypointSub = new ROSLIB.Topic({
    ros: ros,
    name: '/smart_waypoints_markers',
    messageType: 'visualization_msgs/msg/MarkerArray'
  })

  waypointSub.subscribe((msg) => {
    msg.markers.forEach(m => {
      const key = m.ns + m.id
      if (waypointMeshes[key]) {
        viewer.scene.remove(waypointMeshes[key])
        delete waypointMeshes[key]
      }
      
      if (m.action === 2) return // DELETE
      
      let mMesh = null
      
      if (m.type === 3) { // Cylinder
        const sx = (m.scale.x || 1) / 4
        const sy = (m.scale.y || 1) / 4
        const sz = (m.scale.z || 1) / 4
        const geometry = new THREE.CylinderGeometry(sx/2, sy/2, sz, 32)
        geometry.rotateX(Math.PI / 2)
        
        const isTransparent = m.color.a < 1.0
        const material = new THREE.MeshStandardMaterial({ 
          color: new THREE.Color(m.color.r, m.color.g, m.color.b),
          transparent: isTransparent,
          opacity: m.color.a || 1.0,
          depthWrite: !isTransparent 
        })
        mMesh = new THREE.Mesh(geometry, material)
        
      } else if (m.type === 9) { // Text View-Facing (Sprite)
        const canvas = document.createElement('canvas')
        const ctx = canvas.getContext('2d')
        canvas.width = 256
        canvas.height = 64
        
        ctx.clearRect(0, 0, canvas.width, canvas.height)
        
        ctx.font = 'bold 24px Arial'
        ctx.fillStyle = `rgba(${Math.round(m.color.r*255)}, ${Math.round(m.color.g*255)}, ${Math.round(m.color.b*255)}, ${m.color.a})`
        ctx.textAlign = 'center'
        ctx.textBaseline = 'middle'
        
        ctx.shadowColor = 'transparent'
        ctx.shadowBlur = 0
        
        ctx.lineWidth = 2
        ctx.strokeStyle = 'black'
        ctx.strokeText(m.text, canvas.width/2, canvas.height/2)
        ctx.fillText(m.text, canvas.width/2, canvas.height/2)
        
        const texture = new THREE.CanvasTexture(canvas)
        // Use alphaTest to completely discard the empty canvas background, preventing black rectangles
        const material = new THREE.SpriteMaterial({ map: texture, transparent: true, alphaTest: 0.5 })
        mMesh = new THREE.Sprite(material)
        
        const scaleBase = (m.scale.z > 0 ? m.scale.z * 10 : 2) / 4
        mMesh.scale.set(scaleBase * 4, scaleBase, 1) 
      }

      if (mMesh) {
        mMesh.position.set(m.pose.position.x, m.pose.position.y, m.pose.position.z)
        if (m.type !== 9) {
          mMesh.quaternion.set(m.pose.orientation.x, m.pose.orientation.y, m.pose.orientation.z, m.pose.orientation.w)
        }
        
        mMesh.visible = showWaypoints.value 
        
        viewer.scene.add(mMesh)
        waypointMeshes[key] = mMesh
      }
    })
  })

  // 8. Custom Navigation Path Visualization (Fixes ROS3D deprecated Geometry)
  let pathLine = null

  const pathSub = new ROSLIB.Topic({
    ros: ros,
    name: '/plan',
    messageType: 'nav_msgs/msg/Path'
  })

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

.dt-viewer {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  width: 100%;
  height: 100%;
}

.dt-bottom-panel {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: rgba(20, 20, 20, 0.85);
  backdrop-filter: blur(8px);
  border-top: 1px solid #333;
  padding: 10px 15px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  z-index: 10;
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
  background: #333;
  color: #aaa;
  border-color: #444;
}
.dt-btn-inactive:hover {
  background: #444;
}

.dt-btn-active-purple { background: #5e35b1; color: white; border-color: #7e57c2; box-shadow: 0 0 8px rgba(94, 53, 177, 0.5); }
.dt-btn-active-orange { background: #e65100; color: white; border-color: #ff9800; box-shadow: 0 0 8px rgba(230, 81, 0, 0.5); }
.dt-btn-active-blue { background: #1976d2; color: white; border-color: #42a5f5; box-shadow: 0 0 8px rgba(25, 118, 210, 0.5); }
.dt-btn-active-green { background: #00796b; color: white; border-color: #26a69a; box-shadow: 0 0 8px rgba(0, 121, 107, 0.5); }

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
