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

def normalize(q):
    return (q + math.pi) % (2 * math.pi) - math.pi

def inverse_kinematics_planar_3dof(robot, target_x, target_y):
    active_joints = [j for j in robot.joints if j.type in ['revolute', 'continuous']]
    if len(active_joints) != 3:
        return None
        
    limits = [(j.limit_lower, j.limit_upper) for j in active_joints]
    
    zeros = [0.0] * len(active_joints)
    positions = forward_kinematics_full(robot, zeros)
    
    active_indices = [i for i, j in enumerate(robot.joints) if j.type in ['revolute', 'continuous']]
    
    p0 = positions[active_indices[0] + 1]
    p1 = positions[active_indices[1] + 1]
    p2 = positions[active_indices[2] + 1]
    p3 = positions[-1]
    
    L1 = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    L2 = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
    L3 = math.hypot(p3[0] - p2[0], p3[1] - p2[1])
    
    tx = target_x - p0[0]
    ty = target_y - p0[1]
    D = math.sqrt(tx**2 + ty**2)
    
    min_L23 = abs(D - L1)
    max_L23 = min(L2 + L3, D + L1)
    
    if min_L23 > max_L23 + 1e-6:
        return 'unreachable'
        
    def check_solution(q1, q2, q3):
        q1 = normalize(q1)
        q2 = normalize(q2)
        q3 = normalize(q3)
        if limits[0][0] - 1e-4 <= q1 <= limits[0][1] + 1e-4 and \
           limits[1][0] - 1e-4 <= q2 <= limits[1][1] + 1e-4 and \
           limits[2][0] - 1e-4 <= q3 <= limits[2][1] + 1e-4:
            return [q1, q2, q3]
        return None

    if D <= 1e-6:
        L23 = L1
        for i in range(100):
            q1 = -math.pi + 2 * math.pi * i / 99.0
            for sign_q3 in [1, -1]:
                cos_q3 = (L23**2 - L2**2 - L3**2) / (2.0 * L2 * L3)
                if cos_q3 < -1.0 - 1e-6 or cos_q3 > 1.0 + 1e-6:
                    continue
                q3 = math.acos(max(-1.0, min(1.0, cos_q3))) * sign_q3
                
                L1_x = L1 * math.cos(q1)
                L1_y = L1 * math.sin(q1)
                L23_x = tx - L1_x
                L23_y = ty - L1_y
                L23_angle_world = math.atan2(L23_y, L23_x)
                q23 = L23_angle_world - q1
                gamma = math.atan2(L3 * math.sin(q3), L2 + L3 * math.cos(q3))
                q2 = q23 - gamma
                
                sol = check_solution(q1, q2, q3)
                if sol: return sol
    else:
        for i in range(100):
            L23 = min_L23 + (max_L23 - min_L23) * i / 99.0
            for sign_alpha in [1, -1]:
                for sign_q3 in [1, -1]:
                    cos_q3 = (L23**2 - L2**2 - L3**2) / (2.0 * L2 * L3)
                    if cos_q3 < -1.0 - 1e-6 or cos_q3 > 1.0 + 1e-6:
                        continue
                    q3 = math.acos(max(-1.0, min(1.0, cos_q3))) * sign_q3
                    
                    cos_alpha = (L1**2 + D**2 - L23**2) / (2.0 * L1 * D)
                    if cos_alpha < -1.0 - 1e-6 or cos_alpha > 1.0 + 1e-6:
                        continue
                    alpha = math.acos(max(-1.0, min(1.0, cos_alpha))) * sign_alpha
                    
                    q1 = math.atan2(ty, tx) - alpha
                    
                    L1_x = L1 * math.cos(q1)
                    L1_y = L1 * math.sin(q1)
                    L23_x = tx - L1_x
                    L23_y = ty - L1_y
                    L23_angle_world = math.atan2(L23_y, L23_x)
                    q23 = L23_angle_world - q1
                    gamma = math.atan2(L3 * math.sin(q3), L2 + L3 * math.cos(q3))
                    q2 = q23 - gamma
                    
                    sol = check_solution(q1, q2, q3)
                    if sol: return sol
                    
    return 'unreachable'

def check_trajectory(robot, trajectory):
    violations = []
    active_joints = [j for j in robot.joints if j.type in ['revolute', 'continuous']]
    for step_idx, angles in enumerate(trajectory):
        for joint_idx, (joint, angle) in enumerate(zip(active_joints, angles)):
            if angle < joint.limit_lower or angle > joint.limit_upper:
                violations.append((step_idx, joint.name, angle, joint.limit_lower, joint.limit_upper))
    return violations
