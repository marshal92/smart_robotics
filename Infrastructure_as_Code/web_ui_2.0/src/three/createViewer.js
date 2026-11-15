import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'

export function createViewer(container, options = {}) {
  const bgColor = options.background !== undefined ? options.background : 0x111111

  const scene = new THREE.Scene()

  const initialWidth = container.clientWidth || 1
  const initialHeight = container.clientHeight || 1

  const camera = new THREE.PerspectiveCamera(
    45, 
    initialWidth / initialHeight, 
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
  renderer.setSize(initialWidth, initialHeight)
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
  let renderRequested = false
  let isDisposed = false

  const renderNow = () => {
    animationId = null
    if (isDisposed || !renderRequested) return
    renderRequested = false
    const moved = controls.update()
    renderer.render(scene, camera)
    if (controls.enableDamping && moved) {
      requestRender()
    }
  }

  const requestRender = () => {
    if (isDisposed || renderRequested) return
    renderRequested = true
    animationId = requestAnimationFrame(renderNow)
  }

  controls.addEventListener('change', requestRender)
  requestRender()

  const resize = () => {
    if (!container) return
    const width = container.clientWidth
    const height = container.clientHeight
    if (width <= 0 || height <= 0) return
    camera.aspect = width / height
    camera.updateProjectionMatrix()
    renderer.setSize(width, height)
    requestRender()
  }

  const resizeObserver = new ResizeObserver(() => {
    resize()
  })
  resizeObserver.observe(container)

  const dispose = () => {
    isDisposed = true
    renderRequested = false
    if (animationId !== null) {
      cancelAnimationFrame(animationId)
      animationId = null
    }
    controls.removeEventListener('change', requestRender)
    resizeObserver.disconnect()
    controls.dispose()
    renderer.dispose()
    if (container.contains(renderer.domElement)) {
      container.removeChild(renderer.domElement)
    }
  }

  const setBackground = (color) => {
    renderer.setClearColor(color, 1)
    requestRender()
  }

  return {
    scene,
    camera,
    renderer,
    controls,
    resize,
    setBackground,
    requestRender,
    dispose
  }
}
