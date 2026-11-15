import URDFLoader from 'urdf-loader'
import * as ROSLIB from 'roslib'
import * as THREE from 'three'
import { STLLoader } from 'three/addons/loaders/STLLoader.js'
import { ArmTrailManager } from './armTrail'
import { useRosStore } from '../stores/rosStore'
import { subscribeJointStates } from '../services/rosConnection'

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
    let changed = false
    if (state.armTrailEnabled !== lastTrailEnabled) {
      lastTrailEnabled = state.armTrailEnabled
      armTrail.setEnabled(state.armTrailEnabled)
      changed = true
    }
    if (state.armTrailClearTrigger !== lastClearTrigger) {
      lastClearTrigger = state.armTrailClearTrigger
      armTrail.clear()
      changed = true
    }
    if (state.plannedArmPath !== lastPlannedPath) {
      lastPlannedPath = state.plannedArmPath
      if (state.plannedArmPath) {
        armTrail.setPlannedPath(state.plannedArmPath, armBaseLink)
      } else {
        armTrail.clearPlannedPath()
      }
      changed = true
    }
    if (changed) {
      viewer.requestRender?.()
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
  let unsubJointStates = null

  paramClient.callService(request, (result) => {
    if (isDisposed) return
    if (result.values && result.values.length > 0) {
      const urdfString = result.values[0].string_value
      const urdfLoader = new URDFLoader(new THREE.LoadingManager())
      urdfLoader.packages = `http://${window.location.hostname}:8080/packages`
      
      const lightBlueMaterial = new THREE.MeshStandardMaterial({
        color: 0x2196f3,          // Lighter blue for manipulator & primitives
        emissive: 0x051020,
        roughness: 0.5,
        metalness: 0.3,
        depthWrite: true,
        depthTest: true
      })
      
      const darkBlueMaterial = new THREE.MeshStandardMaterial({
        color: 0x1565c0,          // Darker blue for UGV chassis
        emissive: 0x051020,
        roughness: 0.5,
        metalness: 0.4,
        depthWrite: true,
        depthTest: true
      })

      const blackTracksMaterial = new THREE.MeshStandardMaterial({
        color: 0x1c1f24,          // Matte dark charcoal rubber for UGV tracks
        emissive: 0x050507,
        roughness: 0.78,
        metalness: 0.15,
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
              
              // Chassis (base.STL) uses dark blue, tracks (tracks.STL) use dark rubber, manipulator uses light blue
              const lowerUrl = cleanUrl.toLowerCase()
              const isTracks = lowerUrl.endsWith('/tracks.stl') || lowerUrl === 'tracks.stl'
              const isChassis = lowerUrl.endsWith('/base.stl') || lowerUrl === 'base.stl'
              const isLidar = lowerUrl.includes('lidar') || lowerUrl.includes('laser') || lowerUrl.includes('velodyne')
              
              const selectedMaterial = isTracks
                ? blackTracksMaterial
                : (isChassis ? darkBlueMaterial : lightBlueMaterial)
              const mesh = new THREE.Mesh(geometry, selectedMaterial)
              mesh.userData.keepMaterial = true
              
              if (isLidar) {
                mesh.visible = false
              }
              
              mesh.castShadow = true
              mesh.receiveShadow = true
              done(mesh)
              if (!isDisposed) {
                viewer.requestRender?.()
              }
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
      viewer.requestRender?.()

      // Share single /joint_states subscription via rosConnection bus to avoid duplicate ROSLIB topics
      let lastRenderUpdate = 0
      const lastJointValues = Object.create(null)
      let hasAppliedInitialJoints = false
      const JOINT_RENDER_EPS = 1e-4
      unsubJointStates = subscribeJointStates(ros, (msg) => {
        if (!urdfRobot || isDisposed) return
        const now = performance.now()
        if (now - lastRenderUpdate < 33) return // ~30Hz max
        lastRenderUpdate = now

        let changed = !hasAppliedInitialJoints
        const names = msg.name || []
        const positions = msg.position || []
        for (let i = 0; i < names.length; i++) {
          const jointName = names[i]
          const jointAngle = positions[i]
          if (urdfRobot.joints[jointName] && Number.isFinite(jointAngle)) {
            const prevAngle = lastJointValues[jointName]
            if (prevAngle === undefined || Math.abs(jointAngle - prevAngle) > JOINT_RENDER_EPS) {
              lastJointValues[jointName] = jointAngle
              urdfRobot.setJointValue(jointName, jointAngle)
              changed = true
            }
          }
        }

        if (changed) {
          hasAppliedInitialJoints = true
          // Live TCP trail update
          if (armTrail && toolLink) {
            armTrail.update(toolLink, armBaseLink)
          }
          viewer.requestRender?.()
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
      let lastRootPose = null
      const ROOT_POS_EPS = 1e-5
      const ROOT_ROT_EPS = 1e-5
      tfClient.subscribe(rootLink, (tf) => {
        if (isDisposed || !urdfRobot) return
        const t = tf.translation
        const r = tf.rotation
        if (lastRootPose &&
            Math.abs(t.x - lastRootPose.px) <= ROOT_POS_EPS &&
            Math.abs(t.y - lastRootPose.py) <= ROOT_POS_EPS &&
            Math.abs(t.z - lastRootPose.pz) <= ROOT_POS_EPS &&
            Math.abs(r.x - lastRootPose.rx) <= ROOT_ROT_EPS &&
            Math.abs(r.y - lastRootPose.ry) <= ROOT_ROT_EPS &&
            Math.abs(r.z - lastRootPose.rz) <= ROOT_ROT_EPS &&
            Math.abs(r.w - lastRootPose.rw) <= ROOT_ROT_EPS) {
          return
        }
        lastRootPose = { px: t.x, py: t.y, pz: t.z, rx: r.x, ry: r.y, rz: r.z, rw: r.w }
        urdfRobot.position.set(t.x, t.y, t.z)
        urdfRobot.quaternion.set(r.x, r.y, r.z, r.w)
        if (armTrail && toolLink) {
          armTrail.update(toolLink, armBaseLink)
        }
        viewer.requestRender?.()
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
      if (unsubJointStates) {
        unsubJointStates()
        unsubJointStates = null
      }
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
        viewer.requestRender?.()
      }
    }
  }
}
