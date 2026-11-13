import * as THREE from 'three'

export class ArmTrailManager {
  constructor(scene) {
    this.scene = scene
    this.enabled = true
    this.hasTipPosition = false
    this.maxPoints = 1500
    this.pointCount = 0
    this.lastPos = new THREE.Vector3(Infinity, Infinity, Infinity)
    this.tempVec = new THREE.Vector3()

    this.trailGroup = new THREE.Group()
    this.trailGroup.name = 'ArmTrailGroup'

    // 1. Live TCP Trail Line
    this.positions = new Float32Array(this.maxPoints * 3)
    this.geometry = new THREE.BufferGeometry()
    this.geometry.setAttribute('position', new THREE.BufferAttribute(this.positions, 3))
    this.geometry.setDrawRange(0, 0)

    this.material = new THREE.LineBasicMaterial({
      color: 0x00f0ff, // Vibrant neon cyan
      linewidth: 2,
      transparent: true,
      opacity: 0.95,
      depthWrite: false
    })

    this.lineMesh = new THREE.Line(this.geometry, this.material)
    this.lineMesh.renderOrder = 998
    this.trailGroup.add(this.lineMesh)

    // 2. Glowing TCP Tip Marker (Small neon bead at tool center)
    const tipGeo = new THREE.SphereGeometry(0.012, 16, 16)
    const tipMat = new THREE.MeshBasicMaterial({
      color: 0x00f0ff,
      wireframe: false,
      transparent: true,
      opacity: 0.9
    })
    this.tipMesh = new THREE.Mesh(tipGeo, tipMat)
    this.tipMesh.renderOrder = 999
    this.tipMesh.visible = false
    this.trailGroup.add(this.tipMesh)

    // 3. Planned Trajectory Path (Yellow/Amber line for target tasks)
    this.plannedGeometry = new THREE.BufferGeometry()
    this.plannedMaterial = new THREE.LineDashedMaterial({
      color: 0xffb703, // Amber/Gold target path
      linewidth: 2,
      scale: 1,
      dashSize: 0.015,
      gapSize: 0.008,
      transparent: true,
      opacity: 0.9
    })
    this.plannedLine = new THREE.Line(this.plannedGeometry, this.plannedMaterial)
    this.plannedLine.renderOrder = 997
    this.plannedLine.visible = false
    this.trailGroup.add(this.plannedLine)

    this.scene.add(this.trailGroup)
  }

  update(toolObject, baseObject = null) {
    if (!toolObject) return

    // Get current world position of TCP
    toolObject.getWorldPosition(this.tempVec)
    this.hasTipPosition = true

    // Update marker bead
    this.tipMesh.position.copy(this.tempVec)
    this.tipMesh.visible = this.enabled

    if (!this.enabled) return

    // Check if tool has moved at least 3 mm from last recorded spot
    const dist = this.tempVec.distanceTo(this.lastPos)
    if (dist > 0.003) {
      if (this.pointCount < this.maxPoints) {
        const idx = this.pointCount * 3
        this.positions[idx] = this.tempVec.x
        this.positions[idx + 1] = this.tempVec.y
        this.positions[idx + 2] = this.tempVec.z
        this.pointCount++
      } else {
        // Shift buffer left by 1 point (copyWithin uses C++ memmove)
        this.positions.copyWithin(0, 3)
        const lastIdx = (this.maxPoints - 1) * 3
        this.positions[lastIdx] = this.tempVec.x
        this.positions[lastIdx + 1] = this.tempVec.y
        this.positions[lastIdx + 2] = this.tempVec.z
      }

      this.lastPos.copy(this.tempVec)
      this.geometry.attributes.position.needsUpdate = true
      this.geometry.setDrawRange(0, this.pointCount)
      this.geometry.computeBoundingSphere()
    }
  }

  clear() {
    this.pointCount = 0
    this.lastPos.set(Infinity, Infinity, Infinity)
    this.geometry.setDrawRange(0, 0)
    this.geometry.attributes.position.needsUpdate = true
  }

  setEnabled(val) {
    this.enabled = !!val
    this.lineMesh.visible = this.enabled
    this.tipMesh.visible = this.enabled && this.hasTipPosition
  }

  setPlannedPath(pointsArray, baseObject = null) {
    if (!pointsArray || pointsArray.length === 0) {
      this.plannedLine.visible = false
      return
    }

    const flatCoords = []
    const baseWorldPos = new THREE.Vector3()
    const baseWorldQuat = new THREE.Quaternion()

    if (baseObject) {
      baseObject.getWorldPosition(baseWorldPos)
      baseObject.getWorldQuaternion(baseWorldQuat)
    }

    const pVec = new THREE.Vector3()
    for (let i = 0; i < pointsArray.length; i++) {
      const pt = pointsArray[i]
      pVec.set(pt.x, pt.y, pt.z)

      // If coordinates are in base frame and baseObject is provided, transform to world
      if (baseObject) {
        pVec.applyQuaternion(baseWorldQuat).add(baseWorldPos)
      }

      flatCoords.push(pVec.x, pVec.y, pVec.z)
    }

    this.plannedGeometry.setAttribute(
      'position',
      new THREE.Float32BufferAttribute(flatCoords, 3)
    )
    this.plannedGeometry.computeBoundingSphere()
    this.plannedLine.computeLineDistances()
    this.plannedLine.visible = true
  }

  clearPlannedPath() {
    this.plannedLine.visible = false
  }

  dispose() {
    this.clear()
    this.clearPlannedPath()
    if (this.geometry) this.geometry.dispose()
    if (this.material) this.material.dispose()
    if (this.plannedGeometry) this.plannedGeometry.dispose()
    if (this.plannedMaterial) this.plannedMaterial.dispose()
    if (this.tipMesh.geometry) this.tipMesh.geometry.dispose()
    if (this.tipMesh.material) this.tipMesh.material.dispose()
    this.scene.remove(this.trailGroup)
  }
}
