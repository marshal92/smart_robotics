import { ref } from 'vue'
import { pubSmartCommand } from '../../../services/rosConnection'

export function useNavSpeed() {
  const maxSpeed = ref(0.8)
  const isSettingSpeed = ref(false)

  function setMaxSpeed(ros, speed) {
    if (!ros) return

    const val = parseFloat(speed)
    if (isNaN(val)) return

    isSettingSpeed.value = true
    pubSmartCommand('system', `set_speed:${val.toFixed(2)}`)
    maxSpeed.value = val
    isSettingSpeed.value = false
  }

  return {
    maxSpeed,
    isSettingSpeed,
    setMaxSpeed
  }
}
