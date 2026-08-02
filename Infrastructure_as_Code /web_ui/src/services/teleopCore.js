import { pubTwist } from './rosConnection'
import { useRosStore } from '../stores/rosStore'

export const moveState = { up: false, down: false, left: false, right: false }
let teleopInterval = null
let currentSpeed = 0.5 // Default speed

export function setTeleopSpeed(speed) {
  currentSpeed = parseFloat(speed)
}

export function startTeleopLoop() {
  if (teleopInterval) return
  
  teleopInterval = setInterval(() => {
    const store = useRosStore()
    const activeRobotType = store.activeRobotType
    
    if (!activeRobotType || !store.isConnected) return
    
    let linear = 0.0
    let angular = 0.0
    
    if (moveState.up) linear += currentSpeed
    if (moveState.down) linear -= currentSpeed
    if (moveState.left) angular += currentSpeed
    if (moveState.right) angular -= currentSpeed

    pubTwist(activeRobotType, linear, angular)
  }, 100)
}

export function stopTeleopLoop() {
  if (teleopInterval) {
    clearInterval(teleopInterval)
    teleopInterval = null
  }
  
  const store = useRosStore()
  if (store.activeRobotType) {
    pubTwist(store.activeRobotType, 0, 0)
  }
}
