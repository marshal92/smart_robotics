import URDFLoader from 'urdf-loader'
import * as ROSLIB from 'roslib'
import * as THREE from 'three'
import { STLLoader } from 'three/addons/loaders/STLLoader.js'

export function createURDFRobot(ros, viewer, tfClient) {
  // 1. Fetch robot_description from get_parameters service
  const paramClient = new ROSLIB.Service({
    ros: ros,
    name: '/robot_state_publisher/get_parameters',
    serviceType: 'rcl_interfaces/srv/GetParameters'
  })

  const request = {
    names: ['robot_description']
  }

  let urdfRobot = null

  paramClient.callService(request, (result) => {
    if (result.values && result.values.length > 0) {
      const urdfString = result.values[0].string_value
      
      const urdfLoader = new URDFLoader(new THREE.LoadingManager())
      urdfLoader.packages = `http://${window.location.hostname}:8080/packages`
      
      urdfLoader.loadMeshCb = function (path, manager, material, done) {
        const ext = path.split('.').pop().toLowerCase()
        if (ext === 'stl') {
          const stlLoader = new STLLoader(manager)
          stlLoader.load(
            path,
            (geometry) => {
              geometry.computeVertexNormals()
              const mesh = new THREE.Mesh(geometry, material || new THREE.MeshStandardMaterial())
              done(mesh)
            },
            undefined,
            (err) => done(null, err)
          )
        } else {
          done(null, new Error('Unsupported mesh format: ' + ext))
        }
      }

      
      urdfRobot = urdfLoader.parse(urdfString)
      
      // We don't want to re-render the base.STL if the URDF already includes it, 
      // but to keep things isolated as per plan, we might just load it. 
      // Wait, the plan says: "Если используем полное преобразование map → link, группы звеньев размещаем непосредственно в общей сцене."
      // Actually, URDFLoader builds a scene graph where children links are nested under parent links.
      // So if we just update the joint angles, the URDFRobot object handles all the forward kinematics internally!
      // This means we just need to subscribe to /joint_states and update the joints.
      // We don't need to subscribe to TF for each individual link!
      // We only need to position the ROOT of the URDFRobot using the TF of its root link (usually base_link).
      
      viewer.scene.add(urdfRobot)
      console.log('URDF Robot Loaded', urdfRobot)

      // Subscribe to joint states to update the arm with throttle to prevent freezing
      const jointSub = new ROSLIB.Topic({
        ros: ros,
        name: '/joint_states',
        messageType: 'sensor_msgs/msg/JointState',
        throttle_rate: 50 // 50ms = 20Hz
      })

      jointSub.subscribe((msg) => {
        if (!urdfRobot) return
        for (let i = 0; i < msg.name.length; i++) {
          const jointName = msg.name[i]
          const jointAngle = msg.position[i]
          if (urdfRobot.joints[jointName]) {
            urdfRobot.setJointValue(jointName, jointAngle)
          }
        }
      })
      
      // Link the root of the URDF to its TF frame (base_link)
      // Note: We need to make sure urdfRobot isn't being double-transformed if the base STL is also there.
      // In fact, we can hide the base STL if the URDF contains it, or let them overlap (they are identical).
      tfClient.subscribe('base_link', (tf) => {
        urdfRobot.position.set(tf.translation.x, tf.translation.y, tf.translation.z)
        urdfRobot.quaternion.set(tf.rotation.x, tf.rotation.y, tf.rotation.z, tf.rotation.w)
      })

    } else {
      console.error('Failed to get robot_description from robot_state_publisher')
    }
  })
  
  return {
    dispose: () => {
      if (urdfRobot) {
        viewer.scene.remove(urdfRobot)
      }
    }
  }
}
