import { reactive, ref } from 'vue'
import { pubTwist } from './rosConnection'
import { useRosStore } from '../stores/rosStore'

export const moveState = reactive({ up: false, down: false, left: false, right: false })
export const analogState = reactive({ active: false, linear: 0, angular: 0 })
export const teleopSpeed = ref(0.5)

let teleopInterval = null
let currentSpeed = 0.5 // Default speed

function clamp(val, min, max) {
  return Math.max(min, Math.min(max, val))
}

export function setTeleopSpeed(speed) {
  const parsed = parseFloat(speed)
  if (!Number.isFinite(parsed)) return
  // Round to 2 decimals to prevent binary float drift on 0.1 step increments
  const normalized = Math.round(clamp(parsed, 0.1, 2.0) * 100) / 100
  currentSpeed = normalized
  teleopSpeed.value = normalized
}

function publishCurrentTwist() {
  const store = useRosStore()
  const activeRobotType = store.activeRobotType
  if (!activeRobotType || !store.isConnected) return

  let linear = 0.0
  let angular = 0.0

  if (moveState.up) linear += currentSpeed
  if (moveState.down) linear -= currentSpeed
  if (moveState.left) angular += currentSpeed
  if (moveState.right) angular -= currentSpeed

  if (analogState.active) {
    linear = clamp(linear + analogState.linear * currentSpeed, -currentSpeed, currentSpeed)
    angular = clamp(angular + analogState.angular * currentSpeed, -currentSpeed, currentSpeed)
  }

  pubTwist(activeRobotType, linear, angular)
}

export function setAnalogTeleop(linearNorm, angularNorm) {
  const store = useRosStore()
  if (!store.activeRobotType) {
    store.setActiveRobotType('base')
  }

  analogState.linear = clamp(Number(linearNorm) || 0, -1, 1)
  analogState.angular = clamp(Number(angularNorm) || 0, -1, 1)
  analogState.active = true

  if (!teleopInterval) {
    startTeleopLoop()
  }
}

export function clearAnalogTeleop() {
  analogState.active = false
  analogState.linear = 0
  analogState.angular = 0

  if (!moveState.up && !moveState.down && !moveState.left && !moveState.right) {
    stopTeleopLoop()
  }
}

export function startTeleopLoop() {
  if (teleopInterval) return

  publishCurrentTwist()
  teleopInterval = setInterval(publishCurrentTwist, 100)
}

export function stopTeleopLoop() {
  if (teleopInterval) {
    clearInterval(teleopInterval)
    teleopInterval = null
  }

  analogState.active = false
  analogState.linear = 0
  analogState.angular = 0

  const store = useRosStore()
  if (store.activeRobotType) {
    pubTwist(store.activeRobotType, 0, 0)
  }
}
