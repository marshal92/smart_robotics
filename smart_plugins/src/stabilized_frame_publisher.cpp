#include "rclcpp/rclcpp.hpp"
#include "tf2_ros/buffer.h"
#include "tf2_ros/transform_listener.h"
#include "tf2_ros/transform_broadcaster.h"
#include "geometry_msgs/msg/transform_stamped.hpp"
#include "tf2/utils.h"
#include "tf2/LinearMath/Quaternion.h"
#include "tf2_geometry_msgs/tf2_geometry_msgs.hpp"

using namespace std::chrono_literals;

class StabilizedFramePublisher : public rclcpp::Node {
public:
    StabilizedFramePublisher() : Node("stabilized_frame_publisher") {
        tf_buffer_ = std::make_unique<tf2_ros::Buffer>(this->get_clock());
        tf_listener_ = std::make_shared<tf2_ros::TransformListener>(*tf_buffer_);
        tf_broadcaster_ = std::make_shared<tf2_ros::TransformBroadcaster>(this);

        timer_ = this->create_wall_timer(
            20ms, std::bind(&StabilizedFramePublisher::timer_callback, this));
            
        RCLCPP_INFO(this->get_logger(), "⚖️ Stabilized Frame Publisher (C++) started at 50Hz");
    }

private:
    void timer_callback() {
        try {
            // Get the transform from odom to base_footprint
            auto t = tf_buffer_->lookupTransform("odom", "base_footprint", tf2::TimePointZero);

            // Get the actual yaw rotation
            double yaw = tf2::getYaw(t.transform.rotation);

            // Create ideal quaternion (Roll=0, Pitch=0, Yaw=Actual)
            tf2::Quaternion q;
            q.setRPY(0.0, 0.0, yaw);

            // Form new frame
            geometry_msgs::msg::TransformStamped msg;
            msg.header.stamp = this->get_clock()->now();
            msg.header.frame_id = "odom";
            msg.child_frame_id = "base_stabilized";

            // Coordinates (X,Y,Z) we take from the tank
            msg.transform.translation.x = t.transform.translation.x;
            msg.transform.translation.y = t.transform.translation.y;
            msg.transform.translation.z = t.transform.translation.z;

            // And the rotation - leveled with the horizon!
            msg.transform.rotation.x = q.x();
            msg.transform.rotation.y = q.y();
            msg.transform.rotation.z = q.z();
            msg.transform.rotation.w = q.w();

            // Publish
            tf_broadcaster_->sendTransform(msg);

        } catch (const tf2::TransformException & ex) {
        }
    }

    std::unique_ptr<tf2_ros::Buffer> tf_buffer_;
    std::shared_ptr<tf2_ros::TransformListener> tf_listener_;
    std::shared_ptr<tf2_ros::TransformBroadcaster> tf_broadcaster_;
    rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char * argv[]) {
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<StabilizedFramePublisher>());
    rclcpp::shutdown();
    return 0;
}