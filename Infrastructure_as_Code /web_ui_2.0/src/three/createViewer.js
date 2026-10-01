import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'

export function createViewer(container, options = {}) {
  const bgColor = options.background !== undefined ? options.background : 0x111111

  const scene = new THREE.Scene()

  const camera = new THREE.PerspectiveCamera(
    45, 
    container.clientWidth / container.clientHeight, 
    0.01, 
    200
  )
  camera.up.set(0, 0, 1)
  camera.position.set(3, -4, 3)

  const renderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: false
  })
  renderer.setClearColor(bgColor, 1)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5))
  renderer.setSize(container.clientWidth, container.clientHeight)
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.toneMapping = THREE.NoToneMapping

  container.appendChild(renderer.domElement)

  const controls = new OrbitControls(camera, renderer.domElement)
  controls.target.set(0, 0, 0.3)
  
  controls.enableDamping = false
  controls.autoRotate = false
  controls.rotateSpeed = 0.7
  controls.panSpeed = 0.8
  controls.zoomSpeed = 0.8
  
  controls.mouseButtons = {
    LEFT: THREE.MOUSE.ROTATE,
    MIDDLE: THREE.MOUSE.PAN,
    RIGHT: THREE.MOUSE.DOLLY
  }
  controls.screenSpacePanning = false
  
  controls.update()

  // Basic lighting
  const ambientLight = new THREE.AmbientLight(0xffffff, 2.5)
  scene.add(ambientLight)
  
  const dirLight = new THREE.DirectionalLight(0xffffff, 2.5)
  dirLight.position.set(10, -10, 20)
  scene.add(dirLight)

  const dirLight2 = new THREE.DirectionalLight(0xffffff, 1.5)
  dirLight2.position.set(-10, 10, 10)
  scene.add(dirLight2)


  let animationId = null

  const renderLoop = () => {
    animationId = requestAnimationFrame(renderLoop)
    controls.update()
    renderer.render(scene, camera)
  }
  
  renderLoop()

  const resize = () => {
    if (!container) return
    const width = container.clientWidth
    const height = container.clientHeight
    camera.aspect = width / height
    camera.updateProjectionMatrix()
    renderer.setSize(width, height)
  }

  const resizeObserver = new ResizeObserver(() => {
    resize()
  })
  resizeObserver.observe(container)

  const dispose = () => {
    if (animationId !== null) {
      cancelAnimationFrame(animationId)
    }
    resizeObserver.disconnect()
    controls.dispose()
    renderer.dispose()
    if (container.contains(renderer.domElement)) {
      container.removeChild(renderer.domElement)
    }
  }

  const setBackground = (color) => {
    renderer.setClearColor(color, 1)
  }

  return {
    scene,
    camera,
    renderer,
    controls,
    resize,
    setBackground,
    dispose
  }
}
