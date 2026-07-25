#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
from sensor_msgs.msg import CompressedImage
from geometry_msgs.msg import Point
import cv2
import numpy as np
from ultralytics import YOLO

class YoloZoo(Node):
    def __init__(self):
        super().__init__('yolo_tracker')
        
        self.declare_parameter('show_video', False)
        self.show_video = self.get_parameter('show_video').value
        
        self.model = YOLO("yolov8n.pt") 
        
        qos_policy = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=1,
            durability=DurabilityPolicy.VOLATILE
        )
        
        self.sub = self.create_subscription(CompressedImage, '/camera/image_raw/compressed', self.img_callback, qos_profile=qos_policy)
        self.target_pub = self.create_publisher(Point, '/person_track', 10)
        self.debug_pub = self.create_publisher(CompressedImage, '/yolo_overlay/compressed', 10)
        
        self.get_logger().info(f"Mode 1 enabled (Window: {self.show_video})")

    def img_callback(self, msg):
        try:
            np_arr = np.frombuffer(msg.data, np.uint8)
            cv_image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            if cv_image is None: return

            results = self.model(cv_image, classes=[0, 15, 16, 62, 63, 39, 57, 60], verbose=False, conf=0.5)
            annotated_frame = results[0].plot()
            
            height, width, _ = cv_image.shape
            target_msg = Point()
            target_msg.x = -999.0 
            
            if len(results[0].boxes) > 0:
                box = results[0].boxes[0]
                x1, _, x2, _ = box.xyxy[0].tolist()
                obj_center_x = (x1 + x2) / 2
                offset = (width/2 - obj_center_x) / (width/2)
                
                target_msg.x = float(offset)
                cv2.line(annotated_frame, (int(width/2), int(height/2)), (int(obj_center_x), int(height/2)), (0, 255, 0), 2)

            self.target_pub.publish(target_msg)

            _, encoded_img = cv2.imencode('.jpg', annotated_frame)
            out_msg = CompressedImage()
            out_msg.header = msg.header
            out_msg.format = "jpeg"
            out_msg.data = encoded_img.tobytes()
            self.debug_pub.publish(out_msg)
            
            if self.show_video:
                cv2.imshow("YOLO Zoo", annotated_frame)
                cv2.waitKey(1)
            
        except Exception as e:
            pass

def main():
    rclpy.init()
    node = YoloZoo()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()
        cv2.destroyAllWindows()

if __name__ == '__main__':
    main()