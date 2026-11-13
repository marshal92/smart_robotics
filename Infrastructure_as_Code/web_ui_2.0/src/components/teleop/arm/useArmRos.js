import { inject, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
import * as ROSLIB from 'roslib'
import { getRosInstance, pubSmartCommand } from '../../../services/rosConnection'
import { useRosStore } from '../../../stores/rosStore'
import { clampJointRad, computeArmToolFrame } from './armKinematics'

export const ARM_ROS_SYMBOL = Symbol('armRosContext')

export const ARM_JOINT_NAMES = [
  'arm_joint_0',
  'arm_joint_1',
  'arm_joint_2',
  'arm_joint_3',
  'arm_joint_4',
  'arm_joint_5'
]

export const ARM_JOINT_LIMITS = [
  { min: -90, max: 90 },
  { min: -5.0, max: 180 },
  { min: -180, max: 5.0 },
  { min: -90, max: 90 },
  { min: -90, max: 90 },
  { min: -90, max: 90 }
]

export const UNFOLD_POSE_DEG = [0.0, 57.3, -57.3, 0.0, -45.0, 0.0]
export const FOLD_POSE_DEG = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

function eulerFromQuaternion(q) {
  const sinrCosp = 2 * (q.w * q.x + q.y * q.z)
  const cosrCosp = 1 - 2 * (q.x * q.x + q.y * q.y)
  const roll = Math.atan2(sinrCosp, cosrCosp)

  const sinp = 2 * (q.w * q.y - q.z * q.x)
  const pitch = Math.abs(sinp) >= 1 ? Math.sign(sinp) * Math.PI / 2 : Math.asin(sinp)

  const sinyCosp = 2 * (q.w * q.z + q.x * q.y)
  const cosyCosp = 1 - 2 * (q.y * q.y + q.z * q.z)
  const yaw = Math.atan2(sinyCosp, cosyCosp)

  return [roll, pitch, yaw]
}

export function provideArmRosContext() {
  const store = useRosStore()

  // Live feedback state shared across all arm tabs
  const currentJointAnglesRad = ref([0, 0, 0, 0, 0, 0])
  const hasToolPoseData = ref(false)
  const telemetrySource = ref('waiting') // 'waiting' | 'fk' | 'tf'
  const toolPose = ref({
    x: null,
    y: null,
    z: null,
    roll: null,
    pitch: null,
    yaw: null
  })
  let lastTfTelemetryAt = 0

  // Control Hub (AUTO + GOTO_XYZ) shared status & logs
  const hubExecuting = ref(false)
  const activeHubCmd = ref(null) // 'auto' | 'goto' | null
  const hubProgress = ref(0)
  const hubStatusState = ref('Waiting for command...')
  const hubProgressColor = ref('var(--accent)')
  const hubLogs = ref([])
  const gotoStatusText = ref('')
  const gotoStatusType = ref('info')

  // Tab motion stop callbacks registered by child tab components
  const stopCallbacks = new Set()
  const registerStopCallback = (fn) => {
    stopCallbacks.add(fn)
    return () => stopCallbacks.delete(fn)
  }
  const stopAllMotion = () => {
    for (const fn of stopCallbacks) {
      fn()
    }
  }

  let hubResetTimer = null
  let jointSub = null
  let trajPub = null
  let cmdVelPub = null
  let unfoldPub = null
  let foldPub = null
  let modePub = null
  let hubReqPub = null
  let hubStatusSub = null
  let toolPoseSub = null

  const addHubLog = (text, type = 'info') => {
    const time = new Date().toLocaleTimeString()
    hubLogs.value.unshift({ time, text, type })
    if (hubLogs.value.length > 50) {
      hubLogs.value.pop()
    }
  }

  const setupRos = () => {
    const ros = getRosInstance()
    if (!ros) return

    if (!jointSub) {
      jointSub = new ROSLIB.Topic({
        ros,
        name: '/joint_states',
        messageType: 'sensor_msgs/JointState'
      })
      let lastJointUpdate = 0
      jointSub.subscribe((msg) => {
        const now = performance.now()
        if (now - lastJointUpdate < 33) return // ~30Hz max
        lastJointUpdate = now

        const names = msg.name || []
        const positions = msg.position || []
        let updated = false
        const newAngles = [...currentJointAnglesRad.value]
        for (let i = 0; i < 6; i++) {
          const idx = names.indexOf(`arm_joint_${i}`)
          if (idx !== -1 && idx < positions.length) {
            newAngles[i] = positions[idx]
            updated = true
          }
        }
        if (updated) {
          currentJointAnglesRad.value = newAngles
          // Local FK fallback keeps TOOL POSE TELEMETRY live even when Servo/teleop_manager is off
          if (now - lastTfTelemetryAt > 600) {
            const fk = computeArmToolFrame(newAngles)
            hasToolPoseData.value = true
            telemetrySource.value = 'fk'
            toolPose.value = {
              x: fk.position[0] * 1000.0,
              y: fk.position[1] * 1000.0,
              z: fk.position[2] * 1000.0,
              roll: fk.rollDeg,
              pitch: fk.pitchDeg,
              yaw: fk.yawDeg
            }
          }
        }
      })
    }

    if (!trajPub) {
      trajPub = new ROSLIB.Topic({
        ros,
        name: '/arm_controller/joint_trajectory',
        messageType: 'trajectory_msgs/JointTrajectory'
      })
    }

    if (!cmdVelPub) {
      cmdVelPub = new ROSLIB.Topic({
        ros,
        name: '/web_teleop/cmd_vel',
        messageType: 'geometry_msgs/TwistStamped'
      })
    }

    if (!unfoldPub) {
      unfoldPub = new ROSLIB.Topic({
        ros,
        name: '/web_teleop/unfold',
        messageType: 'std_msgs/Empty'
      })
    }

    if (!foldPub) {
      foldPub = new ROSLIB.Topic({
        ros,
        name: '/web_teleop/fold',
        messageType: 'std_msgs/Empty'
      })
    }

    if (!modePub) {
      modePub = new ROSLIB.Topic({
        ros,
        name: '/web_teleop/mode',
        messageType: 'std_msgs/String'
      })
    }

    if (!hubReqPub) {
      hubReqPub = new ROSLIB.Topic({
        ros,
        name: '/web_teleop/hub_request',
        messageType: 'std_msgs/String'
      })
    }

    if (!hubStatusSub) {
      hubStatusSub = new ROSLIB.Topic({
        ros,
        name: '/web_teleop/hub_status',
        messageType: 'std_msgs/String'
      })
      hubStatusSub.subscribe((msg) => {
        try {
          const data = JSON.parse(msg.data)
          const isGotoStatus = data.command === 'GOTO_XYZ' || activeHubCmd.value === 'goto'

          if (isGotoStatus) {
            gotoStatusText.value = data.done ? (data.message || data.state) : (data.state || 'Moving...')
            gotoStatusType.value = data.done ? (data.success ? 'success' : 'error') : 'info'
            if (data.done) {
              hubExecuting.value = false
              activeHubCmd.value = null
              addHubLog(
                `${data.success ? 'GOTO OK' : 'GOTO ERROR'}: ${data.message || data.state}`,
                data.success ? 'success' : 'error'
              )
            }
            return
          }

          if (hubResetTimer) {
            clearTimeout(hubResetTimer)
            hubResetTimer = null
          }
          hubProgress.value = data.progress || 0
          hubStatusState.value = data.state || 'Running...'

          if (data.done) {
            hubExecuting.value = false
            activeHubCmd.value = null
            if (data.success) {
              hubProgressColor.value = 'var(--green)'
              addHubLog(`SUCCESS: ${data.message || 'Task completed successfully.'}`, 'success')
            } else {
              hubProgressColor.value = 'var(--red)'
              addHubLog(`ERROR: ${data.message || 'Task failed.'}`, 'error')
            }
            hubResetTimer = setTimeout(() => {
              hubResetTimer = null
              hubProgress.value = 0
              hubProgressColor.value = 'var(--accent)'
              hubStatusState.value = 'Waiting for command...'
            }, 3500)
          }
        } catch (e) {
          console.error('Failed to parse hub_status', e)
        }
      })
    }

    if (!toolPoseSub) {
      toolPoseSub = new ROSLIB.Topic({
        ros,
        name: '/web_teleop/tool_pose',
        messageType: 'geometry_msgs/PoseStamped'
      })
      toolPoseSub.subscribe((msg) => {
        if (!msg.pose) return
        lastTfTelemetryAt = performance.now()
        hasToolPoseData.value = true
        telemetrySource.value = 'tf'
        const pos = msg.pose.position
        const [r, p, y] = eulerFromQuaternion(msg.pose.orientation)
        toolPose.value = {
          x: pos.x * 1000.0,
          y: pos.y * 1000.0,
          z: pos.z * 1000.0,
          roll: (r * 180.0) / Math.PI,
          pitch: (p * 180.0) / Math.PI,
          yaw: (y * 180.0) / Math.PI
        }
      })
    }
  }

  const cleanupRos = () => {
    stopAllMotion()
    lastTfTelemetryAt = 0
    hasToolPoseData.value = false
    telemetrySource.value = 'waiting'
    if (hubResetTimer) {
      clearTimeout(hubResetTimer)
      hubResetTimer = null
    }
    if (jointSub) {
      jointSub.unsubscribe()
      jointSub = null
    }
    if (hubStatusSub) {
      hubStatusSub.unsubscribe()
      hubStatusSub = null
    }
    if (toolPoseSub) {
      toolPoseSub.unsubscribe()
      toolPoseSub = null
    }
    trajPub = null
    cmdVelPub = null
    unfoldPub = null
    foldPub = null
    modePub = null
    hubReqPub = null
  }

  const publishJointPositionsRad = (radArray, durationSec = 3.0) => {
    if (!trajPub) return

    const rawDuration = Number(durationSec)
    const d = Number.isFinite(rawDuration) && rawDuration >= 0.05 ? rawDuration : 3.0
    const targetRad = radArray.map((rad, idx) => clampJointRad(idx, Number(rad) || 0.0))

    const sec = Math.floor(d)
    const nanosec = Math.round((d - sec) * 1000000000)
    trajPub.publish({
      header: { stamp: { sec: 0, nanosec: 0 }, frame_id: '' },
      joint_names: ARM_JOINT_NAMES,
      points: [{
        positions: targetRad,
        velocities: [],
        accelerations: [],
        effort: [],
        time_from_start: { sec, nanosec }
      }]
    })
  }

  const publishJointPositionsDeg = (degArray, durationSec) => {
    const radArray = degArray.map((deg, idx) => {
      const val = Number.isFinite(Number(deg)) ? Number(deg) : 0.0
      const clampedDeg = Math.min(ARM_JOINT_LIMITS[idx].max, Math.max(ARM_JOINT_LIMITS[idx].min, val))
      return (clampedDeg * Math.PI) / 180.0
    })
    publishJointPositionsRad(radArray, durationSec)
  }

  const sendTwist = (frameId, lx, ly, lz, ax, ay, az) => {
    if (!cmdVelPub) return
    cmdVelPub.publish({
      header: { stamp: { sec: 0, nanosec: 0 }, frame_id: frameId },
      twist: {
        linear: { x: lx, y: ly, z: lz },
        angular: { x: ax, y: ay, z: az }
      }
    })
  }

  const publishMode = (mode) => {
    if (modePub) {
      modePub.publish({ data: mode })
    }
  }

  const publishUnfoldSignal = () => {
    if (unfoldPub) unfoldPub.publish({})
  }

  const publishFoldSignal = () => {
    if (foldPub) foldPub.publish({})
  }

  const resetHubTask = () => {
    if (hubResetTimer) {
      clearTimeout(hubResetTimer)
      hubResetTimer = null
    }
    hubExecuting.value = false
    activeHubCmd.value = null
    hubProgress.value = 0
    hubProgressColor.value = 'var(--accent)'
    hubStatusState.value = 'Ready (Reset)'
    if (gotoStatusText.value && gotoStatusType.value === 'info') {
      gotoStatusText.value = 'Stopped by user'
      gotoStatusType.value = 'warning'
    }
    if (hubReqPub) {
      hubReqPub.publish({ data: JSON.stringify({ command: 'RESET' }) })
    }
    addHubLog('Task execution reset / aborted by user.', 'warning')
  }

  const startHubCsvTask = (taskPath, speedRatio) => {
    if (!hubReqPub || hubExecuting.value) return false
    if (hubResetTimer) {
      clearTimeout(hubResetTimer)
      hubResetTimer = null
    }
    hubExecuting.value = true
    activeHubCmd.value = 'auto'
    hubProgress.value = 5
    hubProgressColor.value = 'var(--accent)'
    hubStatusState.value = 'Initiating task...'

    const taskName = taskPath.includes('square_vertical')
      ? 'Draw Square (Vertical)'
      : 'Draw Square (Horizontal)'
    addHubLog(`Starting Hub Task: ${taskName}`, 'info')

    hubReqPub.publish({
      data: JSON.stringify({
        command: 'EXECUTE_CSV',
        file_path: taskPath,
        speed: speedRatio
      })
    })
    return true
  }

  const startHubGotoXyz = (xM, yM, zM, speedRatio) => {
    if (!hubReqPub || hubExecuting.value) return false
    if (hubResetTimer) {
      clearTimeout(hubResetTimer)
      hubResetTimer = null
    }
    hubExecuting.value = true
    activeHubCmd.value = 'goto'
    gotoStatusType.value = 'info'
    gotoStatusText.value = `Planning move to (${(xM * 1000).toFixed(1)}, ${(yM * 1000).toFixed(1)}, ${(zM * 1000).toFixed(1)}) mm...`
    addHubLog(
      `Starting Manual GoTo XYZ: (${(xM * 1000).toFixed(1)}, ${(yM * 1000).toFixed(1)}, ${(zM * 1000).toFixed(1)}) mm`,
      'info'
    )

    hubReqPub.publish({
      data: JSON.stringify({
        command: 'GOTO_XYZ',
        x: xM,
        y: yM,
        z: zM,
        speed: speedRatio
      })
    })
    return true
  }

  onMounted(() => {
    if (store.isConnected) {
      setupRos()
    }
  })

  watch(() => store.isConnected, (connected) => {
    if (connected) {
      setupRos()
    } else {
      cleanupRos()
    }
  })

  onBeforeUnmount(() => {
    cleanupRos()
  })

  const context = {
    store,
    pubSmartCommand,
    currentJointAnglesRad,
    hasToolPoseData,
    telemetrySource,
    toolPose,
    hubExecuting,
    activeHubCmd,
    hubProgress,
    hubStatusState,
    hubProgressColor,
    hubLogs,
    gotoStatusText,
    gotoStatusType,
    addHubLog,
    publishJointPositionsRad,
    publishJointPositionsDeg,
    sendTwist,
    publishMode,
    publishUnfoldSignal,
    publishFoldSignal,
    resetHubTask,
    startHubCsvTask,
    startHubGotoXyz,
    registerStopCallback,
    stopAllMotion
  }

  provide(ARM_ROS_SYMBOL, context)
  return context
}

export function useArmRos() {
  const ctx = inject(ARM_ROS_SYMBOL)
  if (!ctx) {
    throw new Error('useArmRos() must be called inside a child of ArmControl')
  }
  return ctx
}
