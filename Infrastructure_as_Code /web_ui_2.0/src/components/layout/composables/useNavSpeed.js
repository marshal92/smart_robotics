import { ref } from 'vue'
import * as ROSLIB from 'roslib'

export function useNavSpeed() {
  const maxSpeed = ref(0.8)
  const isSettingSpeed = ref(false)

  function setMaxSpeed(ros, speed) {
    if (!ros) return

    isSettingSpeed.value = true
    const setParamClient = new ROSLIB.Service({
      ros: ros,
      name: '/controller_server/set_parameters',
      serviceType: 'rcl_interfaces/srv/SetParameters'
    })

    const request = {
      parameters: [
        {
          name: 'FollowPath.vx_max',
          value: {
            type: 3, // DOUBLE_TYPE
            double_value: parseFloat(speed)
          }
        }
      ]
    }

    setParamClient.callService(request, (result) => {
      console.log('Successfully updated Nav2 vx_max to:', speed, result)
      maxSpeed.value = speed
      isSettingSpeed.value = false
    }, (error) => {
      console.warn('Failed to update Nav2 parameter (Navigation might not be running yet):', error)
      isSettingSpeed.value = false
    })
  }

  return {
    maxSpeed,
    isSettingSpeed,
    setMaxSpeed
  }
}
