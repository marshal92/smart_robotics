import * as ROSLIB from 'roslib'
import { useRosStore } from '../stores/rosStore'

let ros = null
let smartCmdTopic = null
let cmdVelTopic = null
let cmdShadowTopic = null
let cmdLightTopic = null

export function getRosInstance() {
  return ros
}

export function connectROS(url) {
  const store = useRosStore()
  
  if (ros) ros.close()
  ros = new ROSLIB.Ros({ url: url })

  ros.on('connection', () => {
    store.setConnectionStatus('Connected 🟢', true)
    
    // Publishers
    smartCmdTopic = new ROSLIB.Topic({
      ros: ros,
      name: '/smart_command',
      messageType: 'smart_interfaces/msg/SmartCommand'
    })
    
    cmdVelTopic = new ROSLIB.Topic({ ros: ros, name: '/cmd_vel', messageType: 'geometry_msgs/msg/Twist' })
    cmdShadowTopic = new ROSLIB.Topic({ ros: ros, name: '/cmd_vel_shadow', messageType: 'geometry_msgs/msg/Twist' })
    cmdLightTopic = new ROSLIB.Topic({ ros: ros, name: '/cmd_light', messageType: 'std_msgs/msg/Bool' })

    // Subscribers
    const telemetrySub = new ROSLIB.Topic({
      ros: ros,
      name: '/smart_telemetry',
      messageType: 'smart_interfaces/msg/SmartTelemetry'
    })
    telemetrySub.subscribe((msg) => store.updateTelemetry(msg))

    const fsmStatusSub = new ROSLIB.Topic({
      ros: ros,
      name: '/fsm_status',
      messageType: 'std_msgs/msg/String'
    })
    fsmStatusSub.subscribe((msg) => store.setFsmState(msg.data))

    const camSub = new ROSLIB.Topic({
      ros: ros,
      name: '/camera/image_raw/compressed',
      messageType: 'sensor_msgs/msg/CompressedImage'
    })
    camSub.subscribe((msg) => store.updateCameraStream(msg.data))

    const rosoutSub = new ROSLIB.Topic({
      ros: ros,
      name: '/rosout',
      messageType: 'rcl_interfaces/msg/Log'
    })
    rosoutSub.subscribe((msg) => store.addLog(msg))

    const wpListSub = new ROSLIB.Topic({
      ros: ros,
      name: '/waypoints_list',
      messageType: 'std_msgs/msg/String'
    })
    wpListSub.subscribe((msg) => store.updateWaypoints(JSON.parse(msg.data)))
  })

  ros.on('error', () => {
    store.setConnectionStatus('Error 🟡', false)
  })

  ros.on('close', () => {
    store.setConnectionStatus('Disconnected 🔴', false)
  })
}

export function pubSmartCommand(target_system, command, payloadObj = null) {
  if (!smartCmdTopic) return
  const payloadStr = payloadObj ? JSON.stringify(payloadObj) : ""
  const msg = {
    target_system: target_system,
    command: command,
    payload_json: payloadStr
  }
  smartCmdTopic.publish(msg)
  console.log(`[SmartCommand] -> [${target_system}] ${command}`, payloadObj || "")
}

export function pubTwist(topicName, linearX, angularZ) {
  const topic = topicName === 'base' ? cmdVelTopic : cmdShadowTopic
  if (!topic) return
  topic.publish({
    linear: { x: linearX, y: 0.0, z: 0.0 },
    angular: { x: 0.0, y: 0.0, z: angularZ }
  })
}

export function pubBool(state) {
  if (cmdLightTopic) cmdLightTopic.publish({ data: state })
}
