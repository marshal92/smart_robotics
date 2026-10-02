import { ref } from 'vue'
import * as THREE from 'three'
import * as ROSLIB from 'roslib'

export function useRadiationMap(viewerRef, getMapResolution, getMapOrigin, getMapOrientation) {
  const showRadiation = ref(false)
  let radiationPlane = null
  let activeTopics = []

  function setupRadiation(ros) {
    const viewer = viewerRef.value
    if (!viewer || !ros) return

    const radSub = new ROSLIB.Topic({
      ros: ros,
      name: '/radiation_image/compressed',
      messageType: 'sensor_msgs/msg/CompressedImage'
    })
    activeTopics.push(radSub)
    
    radSub.subscribe((msg) => {
      const img = new Image()
      img.src = 'data:image/png;base64,' + msg.data
      img.onload = () => {
        const mapResolution = getMapResolution()
        const mapOrigin = getMapOrigin()
        const mapOrientation = getMapOrientation()
        
        if (!mapResolution || !mapOrigin) return
        
        const width = img.width * mapResolution
        const height = img.height * mapResolution

        if (!radiationPlane) {
          const texture = new THREE.Texture(img)
          texture.needsUpdate = true
          texture.magFilter = THREE.NearestFilter
          texture.minFilter = THREE.NearestFilter

          const geometry = new THREE.PlaneGeometry(width, height)
          geometry.translate(width / 2, height / 2, 0)
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
          const previousTexture = radiationPlane.material.map
          const previousImage = previousTexture.image

          const sizeChanged =
            previousImage.width !== img.width ||
            previousImage.height !== img.height

          if (sizeChanged) {
            const texture = new THREE.Texture(img)
            texture.magFilter = THREE.NearestFilter
            texture.minFilter = THREE.NearestFilter
            texture.needsUpdate = true

            radiationPlane.material.map = texture
            previousTexture.dispose()
          } else {
            previousTexture.image = img
            previousTexture.needsUpdate = true
          }
          
          if (radiationPlane.geometry.parameters.width !== width || radiationPlane.geometry.parameters.height !== height) {
            radiationPlane.geometry.dispose()
            const geometry = new THREE.PlaneGeometry(width, height)
            geometry.translate(width / 2, height / 2, 0)
            radiationPlane.geometry = geometry
          }

          radiationPlane.position.set(mapOrigin.x, mapOrigin.y, mapOrigin.z + 0.005)
          radiationPlane.quaternion.set(mapOrientation.x, mapOrientation.y, mapOrientation.z, mapOrientation.w)
        }
      }
    })
  }

  function toggleRadiation() {
    showRadiation.value = !showRadiation.value
    if (radiationPlane) {
      radiationPlane.visible = showRadiation.value
    }
  }

  function disposeRadiation() {
    activeTopics.forEach(topic => {
      if (topic && topic.unsubscribe) {
        topic.unsubscribe()
      }
    })
    activeTopics = []
    
    if (radiationPlane && viewerRef.value) {
      viewerRef.value.scene.remove(radiationPlane)
      if (radiationPlane.geometry) radiationPlane.geometry.dispose()
      if (radiationPlane.material) {
        if (radiationPlane.material.map) radiationPlane.material.map.dispose()
        radiationPlane.material.dispose()
      }
      radiationPlane = null
    }
  }

  return {
    showRadiation,
    setupRadiation,
    toggleRadiation,
    disposeRadiation
  }
}
