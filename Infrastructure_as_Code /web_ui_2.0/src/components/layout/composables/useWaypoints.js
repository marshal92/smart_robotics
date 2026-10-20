import { ref } from 'vue'
import * as THREE from 'three'
import * as ROSLIB from 'roslib'

export function useWaypoints(viewerRef) {
  const showWaypoints = ref(false)
  const waypointMeshes = {}
  let activeTopics = []

  function setupWaypoints(ros) {
    const viewer = viewerRef.value
    if (!viewer || !ros) return

    const waypointSub = new ROSLIB.Topic({
      ros: ros,
      name: '/smart_waypoints_markers',
      messageType: 'visualization_msgs/msg/MarkerArray'
    })
    activeTopics.push(waypointSub)

    waypointSub.subscribe((msg) => {
      const seenKeys = new Set()

      msg.markers.forEach(m => {
        const key = m.ns + m.id
        if (m.action === 2) return // DELETE
        seenKeys.add(key)

        const sig = `${m.type}|${m.pose.position.x.toFixed(3)}|${m.pose.position.y.toFixed(3)}|${m.pose.position.z.toFixed(3)}|${m.color.r.toFixed(2)}|${m.color.g.toFixed(2)}|${m.color.b.toFixed(2)}|${m.color.a.toFixed(2)}|${m.text || ''}`

        if (waypointMeshes[key]) {
          if (waypointMeshes[key].userData?.sig === sig) {
            waypointMeshes[key].visible = showWaypoints.value
            return
          }
          const oldMesh = waypointMeshes[key]
          viewer.scene.remove(oldMesh)
          if (oldMesh.geometry) oldMesh.geometry.dispose()
          if (oldMesh.material) {
            if (oldMesh.material.map) oldMesh.material.map.dispose()
            oldMesh.material.dispose()
          }
          delete waypointMeshes[key]
        }
        
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
          mMesh.userData = { sig }
          mMesh.position.set(m.pose.position.x, m.pose.position.y, m.pose.position.z)
          if (m.type !== 9) {
            mMesh.quaternion.set(m.pose.orientation.x, m.pose.orientation.y, m.pose.orientation.z, m.pose.orientation.w)
          }
          mMesh.visible = showWaypoints.value
          mMesh.castShadow = true
          mMesh.receiveShadow = true
          viewer.scene.add(mMesh)
          waypointMeshes[key] = mMesh
        }
      })

      // Remove meshes for waypoints that were deleted from the database
      for (const existingKey in waypointMeshes) {
        if (!seenKeys.has(existingKey)) {
          const oldMesh = waypointMeshes[existingKey]
          viewer.scene.remove(oldMesh)
          if (oldMesh.geometry) oldMesh.geometry.dispose()
          if (oldMesh.material) {
            if (oldMesh.material.map) oldMesh.material.map.dispose()
            oldMesh.material.dispose()
          }
          delete waypointMeshes[existingKey]
        }
      }
    })
  }

  function toggleWaypoints() {
    showWaypoints.value = !showWaypoints.value
    for (let key in waypointMeshes) {
      waypointMeshes[key].visible = showWaypoints.value
    }
  }

  function disposeWaypoints() {
    activeTopics.forEach(topic => {
      if (topic && topic.unsubscribe) {
        topic.unsubscribe()
      }
    })
    activeTopics = []
    
    if (viewerRef.value) {
      for (const key in waypointMeshes) {
        const mesh = waypointMeshes[key]
        viewerRef.value.scene.remove(mesh)
        if (mesh.geometry) mesh.geometry.dispose()
        if (mesh.material) {
          if (mesh.material.map) mesh.material.map.dispose()
          mesh.material.dispose()
        }
      }
    }
    // Clear the object
    for (const key in waypointMeshes) {
      delete waypointMeshes[key]
    }
  }

  return {
    showWaypoints,
    setupWaypoints,
    toggleWaypoints,
    disposeWaypoints
  }
}
