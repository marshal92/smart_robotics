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
    this.rate = options.rate || 10.0
    
    this.transforms = {} 
    this.callbacks = {} 
    
    // Shared pre-allocated objects for GC optimization
    this._pos = new THREE.Vector3()
    this._rot = new THREE.Quaternion()
    this._p = new THREE.Vector3()
    this._q = new THREE.Quaternion()
    
    this._needsUpdate = false
    this._updateLoop = this._updateLoop.bind(this)
    requestAnimationFrame(this._updateLoop)
    
    // Subscribe to /tf
    this.tfSub = new ROSLIB.Topic({
      ros: this.ros,
      name: '/tf',
      messageType: 'tf2_msgs/msg/TFMessage',
      throttle_rate: 33 // ~30Hz max rate for Web UI TF updates
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
    msg.transforms.forEach(t => {
      const child = t.child_frame_id.replace(/^\//, '')
      const parent = t.header.frame_id.replace(/^\//, '')
      
      this.transforms[child] = {
        parent: parent,
        transform: t.transform
      }
    })
    this._needsUpdate = true
  }

  _updateLoop() {
    if (this._needsUpdate) {
      this.notifyCallbacks()
      this._needsUpdate = false
    }
    requestAnimationFrame(this._updateLoop)
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
    this._pos.set(0, 0, 0)
    this._rot.identity()
    
    const path = []
    
    // Trace back to fixed frame
    while (currentFrame !== cleanFixedFrame) {
      const node = this.transforms[currentFrame]
      if (!node) return null
      
      path.push(node.transform)
      currentFrame = node.parent
      if (path.length > 20) return null
    }
    
    // Apply transforms from fixedFrame (top) down to requested frameId (bottom)
    for (let i = path.length - 1; i >= 0; i--) {
      const tf = path[i]
      this._p.set(tf.translation.x, tf.translation.y, tf.translation.z)
      this._q.set(tf.rotation.x, tf.rotation.y, tf.rotation.z, tf.rotation.w)
      
      this._p.applyQuaternion(this._rot)
      this._pos.add(this._p)
      this._rot.multiply(this._q)
    }
    
    return {
      translation: { x: this._pos.x, y: this._pos.y, z: this._pos.z },
      rotation: { x: this._rot.x, y: this._rot.y, z: this._rot.z, w: this._rot.w }
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
