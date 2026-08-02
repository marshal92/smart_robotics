import rclpy
from rclpy.node import Node
from nav_msgs.msg import OccupancyGrid, MapMetaData
from sensor_msgs.msg import CompressedImage
import numpy as np
import cv2

class MapToImageNode(Node):
    def __init__(self):
        super().__init__('map_to_image')
        # We use a QoS profile with depth 1 to avoid processing old maps
        self.subscription = self.create_subscription(
            OccupancyGrid,
            '/map',
            self.map_callback,
            1)
        self.img_pub = self.create_publisher(CompressedImage, '/map_image/compressed', 1)
        self.meta_pub = self.create_publisher(MapMetaData, '/map_metadata', 1)
        self.get_logger().info("MapToImage node started. Listening to /map...")

    def map_callback(self, msg):
        # 1. Publish metadata immediately
        self.meta_pub.publish(msg.info)
        
        # 2. Convert to Image
        width = msg.info.width
        height = msg.info.height
        
        if width == 0 or height == 0:
            return
            
        data = np.array(msg.data, dtype=np.int8).reshape((height, width))
        
        # Create RGBA image
        img = np.zeros((height, width, 4), dtype=np.uint8)
        
        # Free space: White
        free_mask = (data >= 0) & (data <= 25)
        img[free_mask] = [255, 255, 255, 255]
        
        # Occupied space: Black
        occ_mask = data > 25
        img[occ_mask] = [0, 0, 0, 255]
        
        # Unknown space: Transparent! This will look gorgeous in 3D
        unk_mask = data < 0
        img[unk_mask] = [0, 0, 0, 0]
        
        # OpenCV uses BGRA by default, but White/Black are the same.
        # We need to flip the image vertically because ROS Origin is at the bottom-left,
        # whereas standard image UV coordinates start at top-left.
        img = cv2.flip(img, 0)
        
        # Compress to PNG
        success, encoded_image = cv2.imencode('.png', img)
        if not success:
            self.get_logger().error("Failed to encode map image")
            return
            
        img_msg = CompressedImage()
        img_msg.header = msg.header
        img_msg.format = "png"
        img_msg.data = encoded_image.tobytes()
        
        self.img_pub.publish(img_msg)

def main(args=None):
    rclpy.init(args=args)
    node = MapToImageNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
