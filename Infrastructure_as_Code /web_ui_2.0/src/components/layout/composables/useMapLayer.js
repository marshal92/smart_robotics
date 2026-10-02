import * as THREE from 'three'
import * as ROSLIB from 'roslib'

export function useMapLayer(viewerRef) {
  let mapPlane = null
  let mapResolution = 0.05
  let mapOrigin = { x: 0, y: 0, z: 0 }
  let mapOrientation = { x: 0, y: 0, z: 0, w: 1 }
  let activeTopics = []

  function setupMap(ros) {
    const viewer = viewerRef.value
    if (!viewer || !ros) return

    const mapSub = new ROSLIB.Topic({
      ros: ros,
      name: '/map_image/compressed',
      messageType: 'sensor_msgs/msg/CompressedImage'
    })
    activeTopics.push(mapSub)
    
    mapSub.subscribe((msg) => {
      const parts = msg.header.frame_id.split('|')
      if (parts.length < 9) return
      
      const meta = {
        resolution: parseFloat(parts[1]),
        origin: {
          x: parseFloat(parts[2]),
          y: parseFloat(parts[3]),
          z: parseFloat(parts[4])
        },
        orientation: {
          x: parseFloat(parts[5]),
          y: parseFloat(parts[6]),
          z: parseFloat(parts[7]),
          w: parseFloat(parts[8])
        }
      }
      
      const img = new Image()
      img.src = 'data:image/png;base64,' + msg.data
      img.onload = () => {
        const width = img.width * meta.resolution
        const height = img.height * meta.resolution

        if (!mapPlane) {
          const texture = new THREE.Texture(img)
          texture.needsUpdate = true
          texture.magFilter = THREE.NearestFilter
          texture.minFilter = THREE.NearestFilter
        
          const geometry = new THREE.PlaneGeometry(width, height)
          geometry.translate(width / 2, height / 2, 0)
          const material = new THREE.MeshLambertMaterial({ 
            color: 0x999999,
            map: texture,
            transparent: false,
            depthWrite: true,
            side: THREE.FrontSide
          })
          mapPlane = new THREE.Mesh(geometry, material)
          mapPlane.position.set(meta.origin.x, meta.origin.y, meta.origin.z - 0.005)
          mapPlane.quaternion.set(meta.orientation.x, meta.orientation.y, meta.orientation.z, meta.orientation.w)
          mapPlane.receiveShadow = true
          viewer.scene.add(mapPlane)
        } else {
          const previousTexture = mapPlane.material.map
          const previousImage = previousTexture.image

          const sizeChanged =
            previousImage.width !== img.width ||
            previousImage.height !== img.height

          if (sizeChanged) {
            const texture = new THREE.Texture(img)
            texture.magFilter = THREE.NearestFilter
            texture.minFilter = THREE.NearestFilter
            texture.needsUpdate = true

            mapPlane.material.map = texture
            previousTexture.dispose()
          } else {
            previousTexture.image = img
            previousTexture.needsUpdate = true
          }
          
          if (Math.abs(mapPlane.geometry.parameters.width - width) > 0.01 || Math.abs(mapPlane.geometry.parameters.height - height) > 0.01) {
            mapPlane.geometry.dispose()
            const geometry = new THREE.PlaneGeometry(width, height)
            geometry.translate(width / 2, height / 2, 0)
            mapPlane.geometry = geometry
          }

          mapPlane.position.set(meta.origin.x, meta.origin.y, meta.origin.z - 0.005)
          mapPlane.quaternion.set(meta.orientation.x, meta.orientation.y, meta.orientation.z, meta.orientation.w)
        }
        
        // Update globals so radiation map and waypoints align correctly
        mapResolution = meta.resolution
        mapOrigin = meta.origin
        mapOrientation = meta.orientation
      }
    })
  }
  
  function getMapPlane() {
    return mapPlane
  }

  function getMapResolution() { return mapResolution }
  function getMapOrigin() { return mapOrigin }
  function getMapOrientation() { return mapOrientation }

  function disposeMap() {
    activeTopics.forEach(topic => {
      if (topic && topic.unsubscribe) {
        topic.unsubscribe()
      }
    })
    activeTopics = []
    
    if (mapPlane && viewerRef.value) {
      viewerRef.value.scene.remove(mapPlane)
      if (mapPlane.geometry) mapPlane.geometry.dispose()
      if (mapPlane.material) {
        if (mapPlane.material.map) mapPlane.material.map.dispose()
        mapPlane.material.dispose()
      }
      mapPlane = null
    }
  }

  return {
    setupMap,
    getMapPlane,
    getMapResolution,
    getMapOrigin,
    getMapOrientation,
    disposeMap
  }
}
