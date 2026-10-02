import { ref } from 'vue'
import * as THREE from 'three'
import { STLLoader } from 'three/addons/loaders/STLLoader.js'

export function useSdfWorlds(viewerRef) {
  const show3DWorld = ref(false)
  const sdfOpacity = ref(0.7)
  let sdfWorldGroup = null

  function loadSDFWorld(worldName) {
    const viewer = viewerRef.value
    if (!viewer) return
    
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
              
              const loader = new STLLoader()
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
                  transparent: true,
                  opacity: sdfOpacity.value,
                  depthWrite: sdfOpacity.value > 0.99,
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
  }

  function updateSDFOpacity() {
    if (sdfWorldGroup) {
      sdfWorldGroup.traverse((child) => {
        if (child.isMesh && child.material) {
          child.material.transparent = true
          child.material.opacity = sdfOpacity.value
          child.material.depthWrite = sdfOpacity.value > 0.99
        }
      })
    }
  }

  function toggle3DWorld() {
    show3DWorld.value = !show3DWorld.value
    if (sdfWorldGroup) {
      sdfWorldGroup.visible = show3DWorld.value
    }
  }
  
  function disposeSDFWorld() {
    const viewer = viewerRef.value
    if (sdfWorldGroup && viewer) {
      viewer.scene.remove(sdfWorldGroup)
      // Recursive dispose could go here, but this is simple cleanup
      sdfWorldGroup = null
    }
  }

  return {
    show3DWorld,
    sdfOpacity,
    loadSDFWorld,
    updateSDFOpacity,
    toggle3DWorld,
    disposeSDFWorld
  }
}
