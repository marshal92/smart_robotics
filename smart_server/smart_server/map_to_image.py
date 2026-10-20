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
        self._last_hash = None
        self._cached_png = None
        self.get_logger().info("MapToImage node started. Listening to /map...")

    def map_callback(self, msg):
        # 1. Publish metadata immediately
        self.meta_pub.publish(msg.info)
        
        # 2. Convert to Image
        width = msg.info.width
        height = msg.info.height
        
        if width == 0 or height == 0:
            return

        o = msg.info.origin.position
        q = msg.info.origin.orientation
        meta_str = f"map|{msg.info.resolution}|{o.x}|{o.y}|{o.z}|{q.x}|{q.y}|{q.z}|{q.w}"
        cur_hash = hash((width, height, meta_str, bytes(msg.data)))

        if cur_hash != self._last_hash or self._cached_png is None:
            data = np.array(msg.data, dtype=np.int8).reshape((height, width))
            # 1-channel grayscale image (4x faster to allocate & encode than 4-channel RGBA)
            img = np.full((height, width), 128, dtype=np.uint8)
            img[(data >= 0) & (data <= 25)] = 255
            img[data > 25] = 0
            img = cv2.flip(img, 0)

            success, encoded_image = cv2.imencode('.png', img)
            if not success:
                self.get_logger().error("Failed to encode map image")
                return
            self._cached_png = encoded_image.tobytes()
            self._last_hash = cur_hash

        img_msg = CompressedImage()
        img_msg.header = msg.header
        img_msg.header.frame_id = meta_str
        img_msg.format = "png"
        img_msg.data = self._cached_png

        self.img_pub.publish(img_msg)

def main(args=None):
    rclpy.init(args=args)
    node = MapToImageNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()
