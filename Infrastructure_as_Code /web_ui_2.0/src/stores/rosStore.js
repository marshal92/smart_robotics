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
    activeRobotType: null, // 'base' or 'shadow'
    lightOn: false
  }),
  actions: {
    setConnectionStatus(status, connected) {
      this.status = status
      this.isConnected = connected
    },
    updateTelemetry(msg) {
      this.telemetry.fsm_state = msg.fsm_state ?? 'UNKNOWN'
      this.telemetry.linear_speed = msg.linear_speed ?? 0.0
      this.telemetry.angular_speed = msg.angular_speed ?? 0.0
      this.telemetry.dose_rate = msg.dose_rate ?? 0.0
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
    setActiveRobotType(type) {
      this.activeRobotType = type
    },
    setLightState(state) {
      this.lightOn = state
    }
  }
})
