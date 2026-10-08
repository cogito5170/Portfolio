import unittest
import os
import json
import math
from urdf_parser import parse_urdf
from kinematics import forward_kinematics, inverse_kinematics_planar_3dof, check_trajectory

class TestKinematics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base_dir = os.path.dirname(__file__)
        cls.planar_robot = parse_urdf(os.path.join(base_dir, 'planar_3_dof.urdf'))
        cls.arm_6_robot = parse_urdf(os.path.join(base_dir, 'arm_6_dof.urdf'))
        
        with open(os.path.join(base_dir, 'test_vectors.json'), 'r') as f:
            cls.test_vectors = json.load(f)

    def test_fk_known_poses(self):
        # All zeros -> straight line along X
        ee = forward_kinematics(self.planar_robot, [0.0, 0.0, 0.0])
        self.assertAlmostEqual(ee[0], 3.0, places=4)
        self.assertAlmostEqual(ee[1], 0.0, places=4)
        self.assertAlmostEqual(ee[2], 0.0, places=4)
        
        # J1 at 90 deg -> straight line along Y
        ee = forward_kinematics(self.planar_robot, [math.pi/2, 0.0, 0.0])
        self.assertAlmostEqual(ee[0], 0.0, places=4)
        self.assertAlmostEqual(ee[1], 3.0, places=4)
        self.assertAlmostEqual(ee[2], 0.0, places=4)
        
        # J1 90, J2 90, J3 -90 -> J2 at (0,1), J3 at (-1,1), EE at (-1, 2)
        # Wait, if J2 is 90, link 2 points along -X in world. J3 is at (0,1) + (-1,0) = (-1,1).
        # J3 is -90 relative to link 2, so it points along Y in world. EE is at (-1,1) + (0,1) = (-1,2).
        ee = forward_kinematics(self.planar_robot, [math.pi/2, math.pi/2, -math.pi/2])
        self.assertAlmostEqual(ee[0], -1.0, places=4)
        self.assertAlmostEqual(ee[1], 2.0, places=4)
        self.assertAlmostEqual(ee[2], 0.0, places=4)

    def test_ik_round_trip(self):
        tolerance = 1e-3
        max_error = 0.0
        
        # We test IK using the valid poses from test vectors
        poses = [p for p in self.test_vectors[self.planar_robot.name] if not p['is_violation']]
        for pose in poses:
            target = pose['expected_ee']
            # Run IK
            ik_angles = inverse_kinematics_planar_3dof(self.planar_robot, target[0], target[1])
            self.assertIsNotNone(ik_angles, f"IK failed for reachable target {target}")
            
            # Forward kinematics to check round trip
            ee = forward_kinematics(self.planar_robot, ik_angles)
            
            dx = ee[0] - target[0]
            dy = ee[1] - target[1]
            error = math.sqrt(dx*dx + dy*dy)
            if error > max_error:
                max_error = error
                
            self.assertLess(error, tolerance, f"IK round trip error {error} exceeds tolerance {tolerance}")
            
        print(f"\nIK round-trip max error: {max_error:.6f} with tolerance: {tolerance}")

    def test_trajectory_violations(self):
        for robot_name, robot in [('planar_3_dof', self.planar_robot), ('arm_6_dof', self.arm_6_robot)]:
            poses = self.test_vectors[robot_name]
            trajectory = [p['angles'] for p in poses]
            
            violations = check_trajectory(robot, trajectory)
            
            expected_violation_steps = set(i for i, p in enumerate(poses) if p['is_violation'])
            violated_steps = set(v[0] for v in violations)
            self.assertEqual(violated_steps, expected_violation_steps, 
                             f"Expected violation steps {expected_violation_steps}, found {violated_steps}")

    def test_ik_unreachable(self):
        # Target way outside workspace (max reach is 3.0)
        ik_angles = inverse_kinematics_planar_3dof(self.planar_robot, 10.0, 10.0)
        self.assertEqual(ik_angles, 'unreachable', "IK should return 'unreachable' for unreachable targets")


    def test_ik_edge_cases(self):
        # Origin
        angles = inverse_kinematics_planar_3dof(self.planar_robot, 0.0, 0.0)
        self.assertIsNotNone(angles)
        self.assertNotEqual(angles, 'unreachable')
        ee = forward_kinematics(self.planar_robot, angles)
        self.assertAlmostEqual(ee[0], 0.0, places=4)
        self.assertAlmostEqual(ee[1], 0.0, places=4)
        
        # Full reach (3.0)
        angles = inverse_kinematics_planar_3dof(self.planar_robot, 3.0, 0.0)
        self.assertIsNotNone(angles)
        self.assertNotEqual(angles, 'unreachable')
        ee = forward_kinematics(self.planar_robot, angles)
        self.assertAlmostEqual(ee[0], 3.0, places=4)
        self.assertAlmostEqual(ee[1], 0.0, places=4)
        
        # Just beyond reach
        angles = inverse_kinematics_planar_3dof(self.planar_robot, 3.0001, 0.0)
        self.assertEqual(angles, 'unreachable')
        
    def test_ik_diff_links(self):
        robot = parse_urdf(os.path.join(os.path.dirname(__file__), 'planar_3_dof_diff_links.urdf'))
        # Origin
        angles = inverse_kinematics_planar_3dof(robot, 0.0, 0.0)
        self.assertIsNotNone(angles)
        self.assertNotEqual(angles, 'unreachable')
        ee = forward_kinematics(robot, angles)
        self.assertAlmostEqual(ee[0], 0.0, places=4)
        self.assertAlmostEqual(ee[1], 0.0, places=4)
        
        # Full reach
        angles = inverse_kinematics_planar_3dof(robot, 3.0, 0.0)
        self.assertIsNotNone(angles)
        self.assertNotEqual(angles, 'unreachable')
        ee = forward_kinematics(robot, angles)
        self.assertAlmostEqual(ee[0], 3.0, places=4)
        self.assertAlmostEqual(ee[1], 0.0, places=4)
        
        # Just beyond reach
        angles = inverse_kinematics_planar_3dof(robot, 3.0001, 0.0)
        self.assertEqual(angles, 'unreachable')

    def test_trajectory_violations_with_fixed_joint(self):
        robot = parse_urdf(os.path.join(os.path.dirname(__file__), 'planar_arm_with_fixed.urdf'))
        trajectory = [
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 1.5],
            [0.0, 4.0, 0.0],
        ]
        violations = check_trajectory(robot, trajectory)
        violated_steps = set(v[0] for v in violations)
        self.assertEqual(violated_steps, {1, 2})

if __name__ == '__main__':
    unittest.main()
