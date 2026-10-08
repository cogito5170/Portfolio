import math
import xml.etree.ElementTree as ET

class Joint:
    def __init__(self, name, type, origin_xyz, origin_rpy, axis, limit_lower, limit_upper):
        self.name = name
        self.type = type # 'revolute'
        self.origin_xyz = origin_xyz
        self.origin_rpy = origin_rpy
        self.axis = axis
        self.limit_lower = limit_lower
        self.limit_upper = limit_upper

class Robot:
    def __init__(self, name):
        self.name = name
        self.joints = []

def parse_urdf(filepath):
    tree = ET.parse(filepath)
    root = tree.getroot()
    robot = Robot(root.attrib.get('name', 'robot'))
    
    for joint_elem in root.findall('joint'):
        name = joint_elem.attrib.get('name')
        jtype = joint_elem.attrib.get('type')
        
        if jtype not in ['revolute', 'continuous', 'fixed']:
            continue
            
        origin_elem = joint_elem.find('origin')
        origin_xyz = [0.0, 0.0, 0.0]
        origin_rpy = [0.0, 0.0, 0.0]
        if origin_elem is not None:
            if 'xyz' in origin_elem.attrib:
                origin_xyz = [float(x) for x in origin_elem.attrib['xyz'].split()]
            if 'rpy' in origin_elem.attrib:
                origin_rpy = [float(x) for x in origin_elem.attrib['rpy'].split()]
                
        axis_elem = joint_elem.find('axis')
        axis = [0.0, 0.0, 1.0]
        if axis_elem is not None and 'xyz' in axis_elem.attrib:
            axis = [float(x) for x in axis_elem.attrib['xyz'].split()]
            
        limit_elem = joint_elem.find('limit')
        limit_lower = -math.pi
        limit_upper = math.pi
        if limit_elem is not None:
            if 'lower' in limit_elem.attrib:
                limit_lower = float(limit_elem.attrib['lower'])
            if 'upper' in limit_elem.attrib:
                limit_upper = float(limit_elem.attrib['upper'])
                
        joint = Joint(name, jtype, origin_xyz, origin_rpy, axis, limit_lower, limit_upper)
        robot.joints.append(joint)
            
    return robot
