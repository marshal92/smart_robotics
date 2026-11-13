/**
 * Pure kinematic helpers for the 6-DOF manipulator (matching manipulator.urdf.xacro).
 * Provides analytical 2D planar FK/Jacobian (R, Z -> J1, J2), exact 3D URDF FK
 * (arm_base_link -> arm_tool0), auto-level J4 compensation, and J3/J5 roll leveling.
 */

export const ARM_JOINT_LIMITS_RAD = [
  { min: -1.57, max: 1.57 },
  { min: -0.05, max: 3.14 },
  { min: -3.2, max: 0.05 },
  { min: -1.57, max: 1.57 },
  { min: -1.57, max: 1.57 },
  { min: -1.57, max: 1.57 }
]

export const ARM_L1 = 0.274
export const ARM_L2 = 0.216
export const ARM_WRIST_DY = 0.028
export const ARM_SHOULDER_Z = 0.09
export const BOOM_DLS_LAMBDA = 0.015

export function clampJointRad(index, valueRad) {
  const lim = ARM_JOINT_LIMITS_RAD[index]
  if (!lim || !Number.isFinite(valueRad)) return 0
  return Math.min(lim.max, Math.max(lim.min, valueRad))
}

export function clampAllJointsRad(anglesRad) {
  return anglesRad.map((val, idx) => clampJointRad(idx, Number(val) || 0))
}

function makeOriginMat4(xyz, rpy) {
  const [rx, ry, rz] = rpy
  const cx = Math.cos(rx), sx = Math.sin(rx)
  const cy = Math.cos(ry), sy = Math.sin(ry)
  const cz = Math.cos(rz), sz = Math.sin(rz)
  // R = Rz(rz) * Ry(ry) * Rx(rx), row-major flat 16
  return [
    cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx, xyz[0],
    sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx, xyz[1],
    -sy, cy * sx, cy * cx, xyz[2],
    0, 0, 0, 1
  ]
}

function makeJointAxisMat4(axis, q) {
  const c = Math.cos(q)
  const s = Math.sin(q)
  if (axis === 'x') {
    return [1, 0, 0, 0, 0, c, -s, 0, 0, s, c, 0, 0, 0, 0, 1]
  }
  if (axis === 'y') {
    return [c, 0, s, 0, 0, 1, 0, 0, -s, 0, c, 0, 0, 0, 0, 1]
  }
  return [c, -s, 0, 0, s, c, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
}

function mulMat4(a, b) {
  const out = new Array(16)
  for (let r = 0; r < 4; r++) {
    const r4 = r * 4
    const a0 = a[r4], a1 = a[r4 + 1], a2 = a[r4 + 2], a3 = a[r4 + 3]
    out[r4] = a0 * b[0] + a1 * b[4] + a2 * b[8] + a3 * b[12]
    out[r4 + 1] = a0 * b[1] + a1 * b[5] + a2 * b[9] + a3 * b[13]
    out[r4 + 2] = a0 * b[2] + a1 * b[6] + a2 * b[10] + a3 * b[14]
    out[r4 + 3] = a0 * b[3] + a1 * b[7] + a2 * b[11] + a3 * b[15]
  }
  return out
}

// Exact joint transforms from manipulator_description/urdf/manipulator.urdf.xacro
const URDF_CHAIN = [
  { origin: makeOriginMat4([0, 0, 0.01], [1.5708, 0, -1.5708]), axis: 'y' },
  { origin: makeOriginMat4([0, 0.08, 0], [0, 0, -3.1416]), axis: 'x' },
  { origin: makeOriginMat4([0, 0, 0.274], [-3.1416, 0, 0]), axis: 'x' },
  { origin: makeOriginMat4([0, 0.028, 0.076], [3.1416, 0, 3.1416]), axis: 'z' },
  { origin: makeOriginMat4([0, 0, -0.14], [0, 0, 0]), axis: 'x' },
  { origin: makeOriginMat4([-0.0095, 0, -0.0225], [3.1416, 1.5708, 0]), axis: 'x' }
]
const FLANGE_ORIGIN = makeOriginMat4([0.073, 0, 0], [0, 0, 0])

/**
 * Compute exact 3D pose of arm_tool0 in arm_base_link frame.
 */
export function computeArmToolFrame(qRad) {
  let T = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
  for (let i = 0; i < URDF_CHAIN.length; i++) {
    T = mulMat4(T, URDF_CHAIN[i].origin)
    T = mulMat4(T, makeJointAxisMat4(URDF_CHAIN[i].axis, Number(qRad[i]) || 0))
  }
  T = mulMat4(T, FLANGE_ORIGIN)

  // Extract ROS standard ZYX intrinsic / XYZ extrinsic RPY (matches tf2 + eulerFromQuaternion)
  const sinp = -T[8]
  const pitchRad = Math.abs(sinp) >= 1 ? Math.sign(sinp) * (Math.PI / 2) : Math.asin(sinp)
  const rollRad = Math.atan2(T[9], T[10])
  const yawRad = Math.atan2(T[4], T[0])

  // Tool pointing elevation angle (+up / -down) in world XY vs Z
  const xyLen = Math.hypot(T[0], T[4])
  const pitchElevRad = Math.atan2(T[8], xyLen)

  const radToDeg = 180.0 / Math.PI
  return {
    position: [T[3], T[7], T[11]],
    xAxis: [T[0], T[4], T[8]],
    zAxis: [T[2], T[6], T[10]],
    rollDeg: rollRad * radToDeg,
    pitchDeg: pitchRad * radToDeg,
    yawDeg: yawRad * radToDeg,
    pitchElevRad,
    pitchElevDeg: pitchElevRad * radToDeg
  }
}

/**
 * Analytical 2D forward kinematics of wrist pitch axis (arm_joint_4)
 * in the vertical plane of the boom (in meters relative to arm_base_link).
 */
export function computePlanarWristRZ(q1, q2) {
  const alpha = q1 + q2
  const r = -ARM_L1 * Math.cos(q1) + ARM_L2 * Math.cos(alpha) + ARM_WRIST_DY * Math.sin(alpha)
  const z = ARM_SHOULDER_Z + ARM_L1 * Math.sin(q1) + ARM_WRIST_DY * Math.cos(alpha) - ARM_L2 * Math.sin(alpha)
  return { r, z }
}

/**
 * Compute boom planar readout (Reach R mm, Height Z mm, Tool Pitch deg).
 */
export function computePlanarState(qRad) {
  const q1 = Number(qRad[1]) || 0
  const q2 = Number(qRad[2]) || 0
  const { r, z } = computePlanarWristRZ(q1, q2)
  const frame = computeArmToolFrame(qRad)
  return {
    reachM: r,
    heightM: z,
    reachMm: r * 1000.0,
    heightMm: z * 1000.0,
    pitchElevDeg: frame.pitchElevDeg
  }
}

/**
 * Compute one cylindrical boom step (dR, dZ in meters) using 2x2 Damped Least Squares Jacobian
 * with optional global wrist pitch auto-leveling on J4.
 */
export function stepCylindricalBoom(qRad, dR, dZ, autoLevelJ4 = true) {
  const q = [...qRad]
  const q1 = q[1]
  const q2 = q[2]
  const q4 = q[4]
  const alpha = q1 + q2

  // 2x2 analytical Jacobian: J = d(R, Z) / d(q1, q2)
  const sin1 = Math.sin(q1), cos1 = Math.cos(q1)
  const sinA = Math.sin(alpha), cosA = Math.cos(alpha)
  const j00 = ARM_L1 * sin1 - ARM_L2 * sinA + ARM_WRIST_DY * cosA
  const j01 = -ARM_L2 * sinA + ARM_WRIST_DY * cosA
  const j10 = ARM_L1 * cos1 - ARM_WRIST_DY * sinA - ARM_L2 * cosA
  const j11 = -ARM_WRIST_DY * sinA - ARM_L2 * cosA

  const detJ = j00 * j11 - j01 * j10
  const { r, z } = computePlanarWristRZ(q1, q2)
  const outward = r * dR + (z - ARM_SHOULDER_Z) * dZ
  if (Math.abs(detJ) < 0.006 && outward > 0) {
    return { joints: q, applied: false, reason: 'MAX_REACH' }
  }

  // DLS 2x2: dq = J^T * (J * J^T + lambda^2 * I)^-1 * [dR, dZ]^T
  const lam2 = BOOM_DLS_LAMBDA * BOOM_DLS_LAMBDA
  const a00 = j00 * j00 + j01 * j01 + lam2
  const a01 = j00 * j10 + j01 * j11
  const a11 = j10 * j10 + j11 * j11 + lam2
  const detA = a00 * a11 - a01 * a01
  if (detA < 1e-12) {
    return { joints: q, applied: false, reason: 'SINGULAR' }
  }

  const invDet = 1.0 / detA
  const v0 = (a11 * dR - a01 * dZ) * invDet
  const v1 = (-a01 * dR + a00 * dZ) * invDet
  const dq1 = j00 * v0 + j10 * v1
  const dq2 = j01 * v0 + j11 * v1

  const q1Next = q1 + dq1
  const q2Next = q2 + dq2
  if (
    q1Next < ARM_JOINT_LIMITS_RAD[1].min || q1Next > ARM_JOINT_LIMITS_RAD[1].max ||
    q2Next < ARM_JOINT_LIMITS_RAD[2].min || q2Next > ARM_JOINT_LIMITS_RAD[2].max
  ) {
    return { joints: q, applied: false, reason: 'LIMIT' }
  }

  q[1] = q1Next
  q[2] = q2Next

  if (autoLevelJ4) {
    // At q3 = 0, exact pitch invariance gives dq4 = dq1 + dq2 (verified against URDF FK).
    // If q3 != 0, compute pitch elevation sensitivity numerically to keep tool pitch flat.
    let dq4 = dq1 + dq2
    if (Math.abs(q[3]) > 1e-3) {
      const eps = 1e-4
      const baseElev = computeArmToolFrame(qRad).pitchElevRad
      const de1 = (computeArmToolFrame([q[0], q1 + eps, q2, q[3], q4, q[5]]).pitchElevRad - baseElev) / eps
      const de2 = (computeArmToolFrame([q[0], q1, q2 + eps, q[3], q4, q[5]]).pitchElevRad - baseElev) / eps
      const de4 = (computeArmToolFrame([q[0], q1, q2, q[3], q4 + eps, q[5]]).pitchElevRad - baseElev) / eps
      if (Math.abs(de4) > 0.35) {
        dq4 = -(de1 * dq1 + de2 * dq2) / de4
      } else {
        dq4 = (dq1 + dq2) * Math.cos(q[3])
      }
    }
    q[4] = clampJointRad(4, q4 + dq4)
  }

  return { joints: q, applied: true, reason: null }
}

/**
 * Step wrist yaw (J3) while adjusting tool roll (J5) to maintain target jaw horizon (zAxis[2]).
 */
export function stepWristYawWithRollComp(qRad, dq3, targetJawRollZ = 0) {
  const q = [...qRad]
  const q3Next = clampJointRad(3, q[3] + dq3)
  const effectiveDq3 = q3Next - q[3]
  if (Math.abs(effectiveDq3) < 1e-6) {
    return { joints: q, applied: false, reason: 'LIMIT' }
  }

  const eps = 1e-4
  const frame0 = computeArmToolFrame(q)
  const z0 = frame0.zAxis[2]
  const dz3 = (computeArmToolFrame([q[0], q[1], q[2], q[3] + eps, q[4], q[5]]).zAxis[2] - z0) / eps
  const dz5 = (computeArmToolFrame([q[0], q[1], q[2], q[3], q[4], q[5] + eps]).zAxis[2] - z0) / eps

  let q5Next = q[5]
  if (Math.abs(dz5) > 0.15) {
    const dq5 = (-dz3 * effectiveDq3 - 0.5 * (z0 - targetJawRollZ)) / dz5
    q5Next = clampJointRad(5, q[5] + dq5)
  }

  q[3] = q3Next
  q[5] = q5Next
  return { joints: q, applied: true, reason: null }
}
