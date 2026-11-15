import { pubBool, pubTwist } from './rosConnection'
import { clearAnalogTeleop, setAnalogTeleop, setTeleopSpeed, stopTeleopLoop, teleopSpeed } from './teleopCore'
import { useRosStore } from '../stores/rosStore'

const POLL_MS = 50
const STICK_DEADZONE = 0.14
const TRIGGER_DEADZONE = 0.05

// Standard W3C Gamepad mapping (Xbox Series X over USB-C / Bluetooth)
const AXES = {
  LEFT_X: 0,
  LEFT_Y: 1,
  RIGHT_X: 2,
  RIGHT_Y: 3
}

const BTN = {
  A: 0,
  B: 1,
  X: 2,
  Y: 3,
  LB: 4,
  RB: 5,
  LT: 6,
  RT: 7,
  VIEW: 8,
  R3: 11,
  DPAD_UP: 12,
  DPAD_DOWN: 13,
  DPAD_LEFT: 14,
  DPAD_RIGHT: 15
}

let pollTimer = null
let activePadIndex = null
let initialized = false
let wasDriveActive = false
let wasArmActive = false
let prevButtons = []

// Registered by ArmManualTab (manipulator kinematics) and DigitalTwin3D (orbit camera & follow)
let armHandlers = null
let cameraHandlers = null

export function registerArmGamepadHandlers(handlers) {
  armHandlers = handlers
  return () => {
    if (armHandlers === handlers) {
      armHandlers = null
    }
  }
}

export function registerCameraGamepadHandlers(handlers) {
  cameraHandlers = handlers
  return () => {
    if (cameraHandlers === handlers) {
      cameraHandlers = null
    }
  }
}

function applyAxisDeadzone(raw, deadzone = STICK_DEADZONE) {
  const val = Number(raw) || 0
  const abs = Math.abs(val)
  if (abs <= deadzone) return 0
  const norm = Math.min(1, (abs - deadzone) / (1 - deadzone))
  // Gentle exponent improves fine positioning near center while preserving full scale at 1.0
  return Math.sign(val) * Math.pow(norm, 1.3)
}

function applyTriggerDeadzone(raw, deadzone = TRIGGER_DEADZONE) {
  const val = Number(raw) || 0
  if (val <= deadzone) return 0
  return Math.min(1, (val - deadzone) / (1 - deadzone))
}

function formatPadName(idStr) {
  if (!idStr) return 'Xbox Controller'
  const cleaned = idStr.replace(/\s*\(STANDARD GAMEPAD.*?\)/i, '').trim()
  return cleaned.length > 34 ? `${cleaned.slice(0, 31)}...` : (cleaned || 'Xbox Controller')
}

function findConnectedGamepad() {
  if (typeof navigator === 'undefined' || typeof navigator.getGamepads !== 'function') {
    return null
  }
  const pads = navigator.getGamepads()
  if (!pads) return null
  if (activePadIndex !== null && pads[activePadIndex]?.connected) {
    return pads[activePadIndex]
  }
  for (let i = 0; i < pads.length; i++) {
    if (pads[i]?.connected) {
      activePadIndex = i
      return pads[i]
    }
  }
  activePadIndex = null
  return null
}

function isPressed(gp, idx) {
  return Boolean(gp.buttons?.[idx]?.pressed || (gp.buttons?.[idx]?.value ?? 0) > 0.5)
}

function justPressed(gp, idx) {
  return isPressed(gp, idx) && !prevButtons[idx]
}

function snapshotButtons(gp) {
  prevButtons = (gp.buttons || []).map((_, i) => isPressed(gp, i))
}

function releaseAllOutputs() {
  if (wasDriveActive) {
    wasDriveActive = false
    clearAnalogTeleop()
    stopTeleopLoop()
  }
  if (wasArmActive) {
    wasArmActive = false
    armHandlers?.onStop?.()
  }
}

function triggerEmergencyStop() {
  wasDriveActive = false
  wasArmActive = false
  clearAnalogTeleop()
  stopTeleopLoop()
  pubTwist('base', 0, 0)
  pubTwist('shadow', 0, 0)
  armHandlers?.onEmergencyStop?.()
}

function pollGamepad() {
  const store = useRosStore()
  const gp = findConnectedGamepad()

  if (!gp) {
    if (store.gamepadConnected) {
      store.setGamepadState(false, '')
    }
    releaseAllOutputs()
    stopPolling()
    return
  }

  if (!store.gamepadConnected) {
    store.setGamepadState(true, formatPadName(gp.id))
  }

  if (document.hidden) {
    releaseAllOutputs()
    snapshotButtons(gp)
    return
  }

  const mode = store.gamepadMode
  if (mode === 'off') {
    releaseAllOutputs()
    snapshotButtons(gp)
    return
  }

  // Emergency stop (B) takes strict priority over held sticks/triggers
  if (isPressed(gp, BTN.B)) {
    if (justPressed(gp, BTN.B)) {
      triggerEmergencyStop()
    }
    snapshotButtons(gp)
    return
  }

  // View button switches between DRIVE and ARM, releasing previous mode outputs cleanly
  if (justPressed(gp, BTN.VIEW)) {
    releaseAllOutputs()
    store.setGamepadMode(mode === 'drive' ? 'arm' : 'drive')
    snapshotButtons(gp)
    return
  }

  if (justPressed(gp, BTN.Y)) {
    const nextLight = !store.lightOn
    store.setLightState(nextLight)
    pubBool(nextLight)
  }

  // D-Pad Up/Down -> Unfold/Fold; Left/Right -> Speed -/+ consistently in DRIVE & ARM
  const dpadUnfold = justPressed(gp, BTN.DPAD_UP)
  const dpadFold = justPressed(gp, BTN.DPAD_DOWN)
  if (dpadUnfold || dpadFold) {
    if (wasArmActive) {
      wasArmActive = false
      armHandlers?.onStop?.()
    }
    if (dpadUnfold) {
      armHandlers?.onUnfold?.()
    } else {
      armHandlers?.onFold?.()
    }
  }

  const dpadSpeedDelta = (justPressed(gp, BTN.DPAD_RIGHT) ? 1 : 0) - (justPressed(gp, BTN.DPAD_LEFT) ? 1 : 0)

  if (mode === 'drive') {
    if (wasArmActive) {
      wasArmActive = false
      armHandlers?.onStop?.()
    }

    if (dpadSpeedDelta !== 0) {
      setTeleopSpeed(teleopSpeed.value + dpadSpeedDelta * 0.1)
    }

    if (justPressed(gp, BTN.R3)) {
      cameraHandlers?.onToggleFollow?.()
    }

    const rightX = applyAxisDeadzone(gp.axes?.[AXES.RIGHT_X] ?? 0)
    const rightY = applyAxisDeadzone(gp.axes?.[AXES.RIGHT_Y] ?? 0)
    if (Math.abs(rightX) > 0 || Math.abs(rightY) > 0) {
      cameraHandlers?.onOrbit?.(rightX, rightY, POLL_MS / 1000)
    }

    const rt = applyTriggerDeadzone(gp.buttons?.[BTN.RT]?.value ?? 0)
    const lt = applyTriggerDeadzone(gp.buttons?.[BTN.LT]?.value ?? 0)
    const leftX = applyAxisDeadzone(gp.axes?.[AXES.LEFT_X] ?? 0)

    const linNorm = rt - lt
    const angNorm = -leftX // Stick left (-X) -> turn left (+angular.z)
    const driveActive = Math.abs(linNorm) > 0 || Math.abs(angNorm) > 0

    if (driveActive) {
      wasDriveActive = true
      setAnalogTeleop(linNorm, angNorm, store.driveTarget)
    } else if (wasDriveActive) {
      wasDriveActive = false
      clearAnalogTeleop()
    }
  } else if (mode === 'arm') {
    if (wasDriveActive) {
      wasDriveActive = false
      clearAnalogTeleop()
      stopTeleopLoop()
    }

    if (dpadSpeedDelta !== 0) {
      armHandlers?.onStepSpeed?.(dpadSpeedDelta * 10)
    }

    if (justPressed(gp, BTN.R3)) {
      armHandlers?.onToggleAutoLevel?.()
    }

    if (dpadUnfold || dpadFold) {
      snapshotButtons(gp)
      return
    }

    const leftX = applyAxisDeadzone(gp.axes?.[AXES.LEFT_X] ?? 0)
    const leftY = applyAxisDeadzone(gp.axes?.[AXES.LEFT_Y] ?? 0)
    const rightX = applyAxisDeadzone(gp.axes?.[AXES.RIGHT_X] ?? 0)
    const rightY = applyAxisDeadzone(gp.axes?.[AXES.RIGHT_Y] ?? 0)
    const rt = applyTriggerDeadzone(gp.buttons?.[BTN.RT]?.value ?? 0)
    const lt = applyTriggerDeadzone(gp.buttons?.[BTN.LT]?.value ?? 0)
    const roll = (isPressed(gp, BTN.RB) ? 1 : 0) - (isPressed(gp, BTN.LB) ? 1 : 0)
    const grip = (isPressed(gp, BTN.X) ? 1 : 0) - (isPressed(gp, BTN.A) ? 1 : 0)

    const input = {
      reach: -leftY,     // Stick up (-Y) -> R+
      baseYaw: -leftX,   // Stick left (-X) -> J0+ (BASE Left)
      pitch: -rightY,    // Stick up (-Y) -> J4+ (PITCH Up)
      wristYaw: -rightX, // Inverted wrist yaw: Stick left (-X) -> +dq3, right (+X) -> -dq3
      z: rt - lt,        // RT -> Z+, LT -> Z-
      roll,              // LB -> Roll L (-), RB -> Roll R (+)
      grip               // A -> Close (-), X -> Open (+)
    }

    const armActive =
      Math.abs(input.reach) > 0 ||
      Math.abs(input.baseYaw) > 0 ||
      Math.abs(input.pitch) > 0 ||
      Math.abs(input.wristYaw) > 0 ||
      Math.abs(input.z) > 0 ||
      input.roll !== 0 ||
      input.grip !== 0

    if (armActive) {
      wasArmActive = true
      armHandlers?.onStep?.(input)
    } else if (wasArmActive) {
      wasArmActive = false
      armHandlers?.onStop?.()
    }
  }

  prevButtons = (gp.buttons || []).map((_, i) => isPressed(gp, i))
}

function startPolling() {
  if (pollTimer !== null) return
  pollTimer = setInterval(pollGamepad, POLL_MS)
  pollGamepad()
}

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
  prevButtons = []
}

function handleGamepadConnected(e) {
  const store = useRosStore()
  if (e?.gamepad) {
    activePadIndex = e.gamepad.index
    store.setGamepadState(true, formatPadName(e.gamepad.id))
  }
  startPolling()
}

function handleGamepadDisconnected(e) {
  if (e?.gamepad && e.gamepad.index === activePadIndex) {
    activePadIndex = null
  }
  const remaining = findConnectedGamepad()
  const store = useRosStore()
  if (remaining) {
    store.setGamepadState(true, formatPadName(remaining.id))
  } else {
    store.setGamepadState(false, '')
    releaseAllOutputs()
    stopPolling()
  }
}

function handleWindowBlur() {
  releaseAllOutputs()
}

function handleVisibilityChange() {
  if (document.hidden) {
    releaseAllOutputs()
  }
}

export function initGamepadService() {
  if (initialized || typeof window === 'undefined') return
  initialized = true

  window.addEventListener('gamepadconnected', handleGamepadConnected)
  window.addEventListener('gamepaddisconnected', handleGamepadDisconnected)
  window.addEventListener('blur', handleWindowBlur)
  document.addEventListener('visibilitychange', handleVisibilityChange)

  // Detect controller if it was already connected & awakened prior to mount
  const existing = findConnectedGamepad()
  if (existing) {
    useRosStore().setGamepadState(true, formatPadName(existing.id))
    startPolling()
  }
}

export function disposeGamepadService() {
  if (!initialized || typeof window === 'undefined') return
  initialized = false

  window.removeEventListener('gamepadconnected', handleGamepadConnected)
  window.removeEventListener('gamepaddisconnected', handleGamepadDisconnected)
  window.removeEventListener('blur', handleWindowBlur)
  document.removeEventListener('visibilitychange', handleVisibilityChange)

  releaseAllOutputs()
  stopPolling()
  activePadIndex = null
  useRosStore().setGamepadState(false, '')
}
