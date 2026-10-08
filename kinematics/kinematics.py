import math
from typing import List, Tuple

def identity_matrix():
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0]
    ]

def multiply_matrices(A, B):
    result = [[0.0 for _ in range(4)] for _ in range(4)]
    for i in range(4):
        for j in range(4):
            for k in range(4):
                result[i][j] += A[i][k] * B[k][j]
    return result

def transform_point(M, p):
    x = M[0][0]*p[0] + M[0][1]*p[1] + M[0][2]*p[2] + M[0][3]
    y = M[1][0]*p[0] + M[1][1]*p[1] + M[1][2]*p[2] + M[1][3]
    z = M[2][0]*p[0] + M[2][1]*p[1] + M[2][2]*p[2] + M[2][3]
    return [x, y, z]

def translation_matrix(x, y, z):
    M = identity_matrix()
    M[0][3] = x
    M[1][3] = y
    M[2][3] = z
    return M

def rotation_matrix_rpy(r, p, y):
    # R = R_z(y) * R_y(p) * R_x(r)
    cr = math.cos(r)
    sr = math.sin(r)
    cp = math.cos(p)
    sp = math.sin(p)
    cy = math.cos(y)
    sy = math.sin(y)
    
    return [
        [cy*cp, cy*sp*sr - sy*cr, cy*sp*cr + sy*sr, 0.0],
        [sy*cp, sy*sp*sr + cy*cr, sy*sp*cr - cy*sr, 0.0],
        [-sp,   cp*sr,            cp*cr,            0.0],
        [0.0,   0.0,              0.0,              1.0]
    ]

def rotation_matrix_axis_angle(axis, angle):
    # Normalize axis
    length = math.sqrt(sum(x*x for x in axis))
    ux, uy, uz = [x/length for x in axis]
    
    c = math.cos(angle)
    s = math.sin(angle)
    C = 1 - c
    
    return [
        [ux*ux*C + c,    ux*uy*C - uz*s, ux*uz*C + uy*s, 0.0],
        [uy*ux*C + uz*s, uy*uy*C + c,    uy*uz*C - ux*s, 0.0],
        [uz*ux*C - uy*s, uz*uy*C + ux*s, uz*uz*C + c,    0.0],
        [0.0,            0.0,            0.0,            1.0]
    ]

def forward_kinematics_full(robot, angles):
    active_joints = [j for j in robot.joints if j.type in ['revolute', 'continuous']]
    if len(active_joints) != len(angles):
        raise ValueError(f"Number of active joints ({len(active_joints)}) must match number of angles ({len(angles)})")
        
    positions = []
    T = identity_matrix()
    angle_idx = 0
    for joint in robot.joints:
        positions.append(transform_point(T, [0.0, 0.0, 0.0]))
        T_trans = translation_matrix(*joint.origin_xyz)
        T_rot_origin = rotation_matrix_rpy(*joint.origin_rpy)
        T_joint = multiply_matrices(T_trans, T_rot_origin)
        
        if joint.type in ['revolute', 'continuous']:
            angle = angles[angle_idx]
            angle_idx += 1
            T_rot_axis = rotation_matrix_axis_angle(joint.axis, angle)
            T_local = multiply_matrices(T_joint, T_rot_axis)
        else:
            T_local = T_joint
            
        T = multiply_matrices(T, T_local)
        
    positions.append(transform_point(T, [0.0, 0.0, 0.0])) # tip
    return positions

def forward_kinematics(robot, angles):
    return forward_kinematics_full(robot, angles)[-1]

def inverse_kinematics_planar_3dof(robot, target_x, target_y):
    # Analytical IK for 3-DOF planar arm with L1=1, L2=1, L3=1
    D = math.sqrt(target_x**2 + target_y**2)
    if D > 3.0 or D < 0.0:
        return None
        
    # Choose L23 (effective length of link2 + link3)
    # Must satisfy |1 - L23| <= D <= 1 + L23
    min_L23 = abs(D - 1.0)
    max_L23 = min(2.0, D + 1.0)
    L23 = (min_L23 + max_L23) / 2.0
    
    # Clamp due to floating point
    cos_q3 = (L23**2 - 2.0) / 2.0
    cos_q3 = max(-1.0, min(1.0, cos_q3))
    q3 = math.acos(cos_q3)
    
    # Calculate q1 and virtual q2 (angle of L23 relative to L1)
    cos_alpha = (1.0 + D**2 - L23**2) / (2.0 * D)
    cos_alpha = max(-1.0, min(1.0, cos_alpha))
    alpha = math.acos(cos_alpha)
    
    cos_beta = (1.0 + L23**2 - D**2) / (2.0 * L23)
    cos_beta = max(-1.0, min(1.0, cos_beta))
    beta = math.acos(cos_beta)
    
    q1 = math.atan2(target_y, target_x) - alpha
    q23 = math.pi - beta
    
    # Calculate angle of L23 relative to Link 2
    # By sine rule or just geometry:
    # L23_y = 1.0 * sin(q3)
    # L23_x = 1.0 + 1.0 * cos(q3)
    gamma = math.atan2(math.sin(q3), 1.0 + math.cos(q3))
    
    q2 = q23 - gamma
    
    return [q1, q2, q3]

def check_trajectory(robot, trajectory):
    violations = []
    for step_idx, angles in enumerate(trajectory):
        for joint_idx, (joint, angle) in enumerate(zip(robot.joints, angles)):
            if angle < joint.limit_lower or angle > joint.limit_upper:
                violations.append((step_idx, joint.name, angle, joint.limit_lower, joint.limit_upper))
    return violations
