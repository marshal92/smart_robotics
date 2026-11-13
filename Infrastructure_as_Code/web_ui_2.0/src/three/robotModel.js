import URDFLoader from 'urdf-loader'
import * as ROSLIB from 'roslib'
import * as THREE from 'three'
import { STLLoader } from 'three/addons/loaders/STLLoader.js'
import { ArmTrailManager } from './armTrail'
import { useRosStore } from '../stores/rosStore'

export function createURDFRobot(ros, viewer, tfClient) {
  const store = useRosStore()
  const armTrail = new ArmTrailManager(viewer.scene)
  armTrail.setEnabled(store.armTrailEnabled)

  let isDisposed = false
  let toolLink = null
  let armBaseLink = null
  let toolAxesHelper = null
  let baseAxesHelper = null
  let lastClearTrigger = store.armTrailClearTrigger
  let lastTrailEnabled = store.armTrailEnabled
  let lastPlannedPath = store.plannedArmPath

  const unsubscribeStore = store.$subscribe((mutation, state) => {
    if (!armTrail || isDisposed) return
    if (state.armTrailEnabled !== lastTrailEnabled) {
      lastTrailEnabled = state.armTrailEnabled
      armTrail.setEnabled(state.armTrailEnabled)
    }
    if (state.armTrailClearTrigger !== lastClearTrigger) {
      lastClearTrigger = state.armTrailClearTrigger
      armTrail.clear()
    }
    if (state.plannedArmPath !== lastPlannedPath) {
      lastPlannedPath = state.plannedArmPath
      if (state.plannedArmPath) {
        armTrail.setPlannedPath(state.plannedArmPath, armBaseLink)
      } else {
        armTrail.clearPlannedPath()
      }
    }
  })

  // 1. Fetch robot_description from get_parameters service
  const paramClient = new ROSLIB.Service({
    ros: ros,
    name: '/robot_state_publisher/get_parameters',
    serviceType: 'rcl_interfaces/srv/GetParameters'
  })

  const request = {
    names: ['robot_description']
  }

  let urdfRobot = null
  let jointSub = null

  paramClient.callService(request, (result) => {
    if (isDisposed) return
    if (result.values && result.values.length > 0) {
      const urdfString = result.values[0].string_value
      const urdfLoader = new URDFLoader(new THREE.LoadingManager())
      urdfLoader.packages = `http://${window.location.hostname}:8080/packages`
      
      const lightBlueMaterial = new THREE.MeshPhysicalMaterial({
        color: 0x2196f3,          // Lighter blue for manipulator & primitives
        emissive: 0x051020,
        roughness: 0.5,
        metalness: 0.3,
        clearcoat: 0.2,
        clearcoatRoughness: 0.4,
        reflectivity: 0.7,
        depthWrite: true,
        depthTest: true
      })
      
      const darkBlueMaterial = new THREE.MeshPhysicalMaterial({
        color: 0x1565c0,          // Darker blue for UGV chassis
        emissive: 0x051020,
        roughness: 0.5,
        metalness: 0.4,
        clearcoat: 0.2,
        clearcoatRoughness: 0.4,
        reflectivity: 0.7,
        depthWrite: true,
        depthTest: true
      })
      
      urdfLoader.loadMeshCb = function (path, manager, material, done) {
        let finalPath = path
        // Fallback: intercept absolute file://.../install/... paths if any external URDF uses $(find ...)
        if (finalPath.includes('/install/')) {
          const installPart = finalPath.substring(finalPath.indexOf('/install/'))
          finalPath = `http://${window.location.hostname}:8080${installPart}`
        }

        const cleanUrl = finalPath.split('?')[0]
        const ext = cleanUrl.split('.').pop().toLowerCase()
        if (ext === 'stl') {
          const stlLoader = new STLLoader(manager)
          stlLoader.load(
            finalPath,
            (geometry) => {
              if (isDisposed) {
                geometry.dispose()
                return
              }
              geometry.computeVertexNormals()
              
              // Chassis (base.STL) uses dark blue so the lighter-blue manipulator stands out
              const lowerUrl = cleanUrl.toLowerCase()
              const isChassis = lowerUrl.endsWith('/base.stl') || lowerUrl === 'base.stl'
              const isLidar = lowerUrl.includes('lidar') || lowerUrl.includes('laser') || lowerUrl.includes('velodyne')
              
              const selectedMaterial = isChassis ? darkBlueMaterial : lightBlueMaterial
              const mesh = new THREE.Mesh(geometry, selectedMaterial)
              mesh.userData.keepMaterial = true
              
              if (isLidar) {
                mesh.visible = false
              }
              
              mesh.castShadow = true
              mesh.receiveShadow = true
              done(mesh)
            },
            undefined,
            (err) => done(null, err)
          )
        } else {
          done(null, new Error('Unsupported mesh format: ' + ext))
        }
      }

      
      urdfRobot = urdfLoader.parse(urdfString)
      
      // Style synchronous primitive shapes (boxes, cylinders in URDF) without overwriting STL materials
      urdfRobot.traverse((child) => {
        if (child.name && (child.name.toLowerCase().includes('lidar') || child.name.toLowerCase().includes('laser') || child.name.toLowerCase().includes('velodyne'))) {
          child.visible = false
        }
        if (child.isMesh) {
          if (!child.userData?.keepMaterial) {
            child.material = lightBlueMaterial
          }
          child.castShadow = true
          child.receiveShadow = true
        }
      })
      
      viewer.scene.add(urdfRobot)
      console.log('URDF Robot Loaded', urdfRobot)

      // Detect tool and arm base links for live trajectory visualization
      toolLink = (urdfRobot.links && urdfRobot.links['arm_tool0']) || 
                 (urdfRobot.links && urdfRobot.links['arm_gripper_base']) || 
                 urdfRobot.getObjectByName('arm_tool0') || 
                 urdfRobot.getObjectByName('arm_gripper_base')
      armBaseLink = (urdfRobot.links && urdfRobot.links['arm_base_link']) || 
                    urdfRobot.getObjectByName('arm_base_link')

      // Visual triad helpers matching Three.js/ROS convention (R=X, G=Y, B=Z)
      if (toolLink) {
        toolAxesHelper = new THREE.AxesHelper(0.15)
        toolLink.add(toolAxesHelper)
      }
      if (armBaseLink) {
        baseAxesHelper = new THREE.AxesHelper(0.15)
        armBaseLink.add(baseAxesHelper)
      }
      
      if (store.plannedArmPath && armTrail) {
        armTrail.setPlannedPath(store.plannedArmPath, armBaseLink)
      }

      // Subscribe to joint states to update the arm with throttle to prevent freezing
      jointSub = new ROSLIB.Topic({
        ros: ros,
        name: '/joint_states',
        messageType: 'sensor_msgs/msg/JointState'
      })

      let lastRenderUpdate = 0
      jointSub.subscribe((msg) => {
        if (!urdfRobot) return
        const now = performance.now()
        if (now - lastRenderUpdate < 33) return // ~30Hz max
        lastRenderUpdate = now
        
        for (let i = 0; i < msg.name.length; i++) {
          const jointName = msg.name[i]
          const jointAngle = msg.position[i]
          if (urdfRobot.joints[jointName]) {
            urdfRobot.setJointValue(jointName, jointAngle)
          }
        }

        // Live TCP trail update
        if (armTrail && toolLink) {
          armTrail.update(toolLink, armBaseLink)
        }
      })
      // Dynamically find the root link of the URDF
      let rootLink = 'base_footprint'
      if (urdfRobot.joints && urdfRobot.links) {
        const childLinks = Object.values(urdfRobot.joints).map(j => j.child ? j.child.name : '')
        const allLinks = Object.keys(urdfRobot.links)
        const foundRoot = allLinks.find(l => !childLinks.includes(l))
        if (foundRoot) {
          rootLink = foundRoot
          console.log('Detected URDF Root Link:', rootLink)
        }
      }

      // Link the root of the URDF to its ACTUAL TF frame
      tfClient.subscribe(rootLink, (tf) => {
        if (isDisposed || !urdfRobot) return
        urdfRobot.position.set(tf.translation.x, tf.translation.y, tf.translation.z)
        urdfRobot.quaternion.set(tf.rotation.x, tf.rotation.y, tf.rotation.z, tf.rotation.w)
        if (armTrail && toolLink) {
          armTrail.update(toolLink, armBaseLink)
        }
      })

    } else {
      console.error('Failed to get robot_description from robot_state_publisher')
    }
  })
  
  return {
    dispose: () => {
      isDisposed = true
      if (unsubscribeStore) unsubscribeStore()
      if (armTrail) armTrail.dispose()
      if (jointSub) jointSub.unsubscribe()
      // tfClient base_footprint unsubscription is handled globally in DigitalTwin3D.vue on disconnect
      
      if (toolAxesHelper) {
        toolAxesHelper.parent?.remove(toolAxesHelper)
        toolAxesHelper.dispose()
        toolAxesHelper = null
      }
      if (baseAxesHelper) {
        baseAxesHelper.parent?.remove(baseAxesHelper)
        baseAxesHelper.dispose()
        baseAxesHelper = null
      }

      if (urdfRobot) {
        viewer.scene.remove(urdfRobot)
        
        // Traverse and dispose all geometries and unique materials to free GPU memory
        const disposedMaterials = new Set()
        urdfRobot.traverse((child) => {
          if (child.isMesh) {
            if (child.geometry) child.geometry.dispose()
            if (child.material) {
              const mats = Array.isArray(child.material) ? child.material : [child.material]
              mats.forEach((m) => {
                if (m && !disposedMaterials.has(m)) {
                  disposedMaterials.add(m)
                  if (m.map) m.map.dispose()
                  m.dispose()
                }
              })
            }
          }
        })
      }
    }
  }
}
