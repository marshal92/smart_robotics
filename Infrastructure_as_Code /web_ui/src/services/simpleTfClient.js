import * as ROSLIB from 'roslib'
import * as THREE from 'three'

/**
 * A lightweight alternative to ROSLIB.TFClient that does not require tf2_web_republisher.
 * It subscribes directly to /tf and /tf_static and computes transforms on the client side.
 */
export class SimpleTFClient {
  constructor(options) {
    this.ros = options.ros
    this.fixedFrame = options.fixedFrame || 'map'
    this.angularThres = options.angularThres || 0.01
    this.transThres = options.transThres || 0.01
    this.rate = options.rate || 10.0
    
    this.transforms = {} // child_frame_id -> { parent, transform: ROSLIB.Transform }
    this.callbacks = {} // frame_id -> array of callbacks
    
    // Subscribe to /tf
    this.tfSub = new ROSLIB.Topic({
      ros: this.ros,
      name: '/tf',
      messageType: 'tf2_msgs/msg/TFMessage'
    })
    this.tfSub.subscribe(this.processTFMessage.bind(this))
    
    // Subscribe to /tf_static
    this.tfStaticSub = new ROSLIB.Topic({
      ros: this.ros,
      name: '/tf_static',
      messageType: 'tf2_msgs/msg/TFMessage'
    })
    this.tfStaticSub.subscribe(this.processTFMessage.bind(this))
  }

  processTFMessage(msg) {
    let changed = false
    msg.transforms.forEach(t => {
      // Clean up frame names (remove leading slashes if any)
      const child = t.child_frame_id.replace(/^\//, '')
      const parent = t.header.frame_id.replace(/^\//, '')
      
      this.transforms[child] = {
        parent: parent,
        transform: t.transform
      }
      changed = true
    })
    
    if (changed) {
      this.notifyCallbacks()
    }
  }

  notifyCallbacks() {
    Object.keys(this.callbacks).forEach(frameId => {
      if (this.callbacks[frameId].length === 0) return
      
      const tf = this.computeTransform(frameId)
      if (tf) {
        this.callbacks[frameId].forEach(cb => cb(tf))
      }
    })
  }

  computeTransform(frameId) {
    const cleanFrameId = frameId.replace(/^\//, '')
    const cleanFixedFrame = this.fixedFrame.replace(/^\//, '')
    
    if (cleanFrameId === cleanFixedFrame) {
      return {
        translation: { x: 0, y: 0, z: 0 },
        rotation: { x: 0, y: 0, z: 0, w: 1 }
      }
    }
    
    let currentFrame = cleanFrameId
    let pos = new THREE.Vector3()
    let rot = new THREE.Quaternion()
    
    const path = []
    
    // Trace back to fixed frame (or highest available frame)
    while (currentFrame !== cleanFixedFrame) {
      const node = this.transforms[currentFrame]
      if (!node) {
        // Transform tree is incomplete. Stop here and just use what we have!
        console.warn(`SimpleTFClient: Tree incomplete. Missing parent for ${currentFrame}. Using it as root.`)
        break
      }
      path.push(node.transform)
      currentFrame = node.parent
      if (path.length > 20) {
        console.warn(`SimpleTFClient: TF loop or tree too deep for ${cleanFrameId}`)
        break
      }
    }
    
    // Apply transforms from fixedFrame (top) down to requested frameId (bottom)
    path.reverse().forEach(tf => {
      const p = new THREE.Vector3(tf.translation.x, tf.translation.y, tf.translation.z)
      const q = new THREE.Quaternion(tf.rotation.x, tf.rotation.y, tf.rotation.z, tf.rotation.w)
      
      p.applyQuaternion(rot)
      pos.add(p)
      rot.multiply(q)
    })
    
    return {
      translation: { x: pos.x, y: pos.y, z: pos.z },
      rotation: { x: rot.x, y: rot.y, z: rot.z, w: rot.w }
    }
  }

  subscribe(frameId, callback) {
    const cleanFrameId = frameId.replace(/^\//, '')
    if (!this.callbacks[cleanFrameId]) {
      this.callbacks[cleanFrameId] = []
    }
    this.callbacks[cleanFrameId].push(callback)
    
    // Try to trigger immediately if we already have the transform
    const tf = this.computeTransform(cleanFrameId)
    if (tf) {
      callback(tf)
    }
  }

  unsubscribe(frameId, callback) {
    const cleanFrameId = frameId.replace(/^\//, '')
    if (this.callbacks[cleanFrameId]) {
      this.callbacks[cleanFrameId] = this.callbacks[cleanFrameId].filter(cb => cb !== callback)
    }
  }
}
