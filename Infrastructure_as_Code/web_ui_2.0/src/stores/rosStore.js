import { defineStore } from 'pinia'

export const useRosStore = defineStore('ros', {
  state: () => ({
    status: 'Disconnected 🔴',
    isConnected: false,
    telemetry: {
      fsm_state: 'UNKNOWN',
      linear_speed: 0.0,
      dose_rate: 0.0,
      nav_status: 'IDLE'
    },
    cameraStream: '',
    logs: [],
    waypoints: {},
    routeQueue: [],
    commandQueue: [],
    queueMode: false,
    lapsCount: 1,
    activeRobotType: null, // 'base' or 'shadow'
    lightOn: false,
    radiationStatus: {
      geiger_active: false,
      field_active: false
    },
    armTrailEnabled: false,
    armTrailClearTrigger: 0,
    plannedArmPath: null
  }),
  actions: {
    setConnectionStatus(status, connected) {
      this.status = status
      this.isConnected = connected
    },
    setRadiationStatus(status) {
      this.radiationStatus = status
    },
    updateTelemetry(msg) {
      this.telemetry.fsm_state = msg.fsm_state ?? 'UNKNOWN'
      const rawLinear = Number(msg.linear_speed ?? 0.0)
      this.telemetry.linear_speed = Math.abs(rawLinear) < 0.005 ? 0.0 : rawLinear
      const rawAngular = Number(msg.angular_speed ?? 0.0)
      this.telemetry.angular_speed = Math.abs(rawAngular) < 0.005 ? 0.0 : rawAngular
      const rawDose = Number(msg.dose_rate ?? 0.0)
      this.telemetry.dose_rate = Math.abs(rawDose) < 0.005 ? 0.0 : rawDose
      this.telemetry.nav_status = msg.nav_status ?? 'IDLE'
    },
    setFsmState(stateStr) {
      this.telemetry.fsm_state = stateStr
    },
    updateCameraStream(data) {
      this.cameraStream = "data:image/jpeg;base64," + data
    },
    addLog(msg) {
      this.logs.push(msg)
      if (this.logs.length > 50) this.logs.shift()
    },
    updateWaypoints(waypointsDB) {
      this.waypoints = waypointsDB
    },
    addToRouteQueue(point) {
      this.routeQueue.push(point)
    },
    clearRouteQueue() {
      this.routeQueue = []
    },
    addCommandToQueue(name, type, laps = 1) {
      this.commandQueue.push({
        id: Date.now() + Math.random(),
        name,
        type,
        laps: Math.max(1, parseInt(laps) || 1)
      })
    },
    removeCommandFromQueue(index) {
      this.commandQueue.splice(index, 1)
    },
    clearCommandQueue() {
      this.commandQueue = []
    },
    setActiveRobotType(type) {
      this.activeRobotType = type
    },
    setLightState(state) {
      this.lightOn = state
    },
    toggleArmTrail() {
      this.armTrailEnabled = !this.armTrailEnabled
    },
    clearArmTrail() {
      this.armTrailClearTrigger++
    },
    setPlannedArmPath(pathArray) {
      this.plannedArmPath = pathArray
    }
  }
})
