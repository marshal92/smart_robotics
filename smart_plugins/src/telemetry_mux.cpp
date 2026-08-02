#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/string.hpp>
#include <std_msgs/msg/bool.hpp>
#include <std_msgs/msg/float32.hpp>
#include <nav_msgs/msg/odometry.hpp>
#include <smart_interfaces/msg/smart_telemetry.hpp>
#include <nlohmann/json.hpp>

using std::placeholders::_1;
using json = nlohmann::json;

class TelemetryMuxCpp : public rclcpp::Node {
public:
    TelemetryMuxCpp() : Node("telemetry_mux") {
        // Initialization of default values
        telemetry_msg_.fsm_state = "UNKNOWN";
        telemetry_msg_.nav_status = "IDLE";

        // Subscriptions
        fsm_sub_ = this->create_subscription<std_msgs::msg::String>("/fsm_status", 10, std::bind(&TelemetryMuxCpp::fsm_cb, this, _1));
        nav_sub_ = this->create_subscription<std_msgs::msg::String>("/nav_status", 10, std::bind(&TelemetryMuxCpp::nav_cb, this, _1));
        odom_sub_ = this->create_subscription<nav_msgs::msg::Odometry>("/odom", 10, std::bind(&TelemetryMuxCpp::odom_cb, this, _1));
        dose_sub_ = this->create_subscription<std_msgs::msg::Float32>("/current_dose_rate", 10, std::bind(&TelemetryMuxCpp::dose_cb, this, _1));
        light_sub_ = this->create_subscription<std_msgs::msg::Bool>("/cmd_light", 10, std::bind(&TelemetryMuxCpp::light_cb, this, _1));
        payload_sub_ = this->create_subscription<std_msgs::msg::String>("/payload/status", 10, std::bind(&TelemetryMuxCpp::payload_cb, this, _1));

        // Publisher
        pub_ = this->create_publisher<smart_interfaces::msg::SmartTelemetry>("/smart_telemetry", 10);
        
        // Timer 5Hz (200 мс)
        timer_ = this->create_wall_timer(std::chrono::milliseconds(200), std::bind(&TelemetryMuxCpp::timer_cb, this));

        RCLCPP_INFO(this->get_logger(), "C++ Telemetry Mux Запущен: агрегация данных 5Hz");
    }

private:
    void fsm_cb(const std_msgs::msg::String::SharedPtr msg) { telemetry_msg_.fsm_state = msg->data; }
    void nav_cb(const std_msgs::msg::String::SharedPtr msg) { telemetry_msg_.nav_status = msg->data; }
    void dose_cb(const std_msgs::msg::Float32::SharedPtr msg) { telemetry_msg_.dose_rate = msg->data; }
    void light_cb(const std_msgs::msg::Bool::SharedPtr msg) { telemetry_msg_.light_is_on = msg->data; }
    
    void odom_cb(const nav_msgs::msg::Odometry::SharedPtr msg) {
        telemetry_msg_.linear_speed = msg->twist.twist.linear.x;
        telemetry_msg_.angular_speed = msg->twist.twist.angular.z;
    }
    
    void payload_cb(const std_msgs::msg::String::SharedPtr msg) {
        try {
            auto j = json::parse(msg->data);
            if (j.contains("active_tools")) {
                telemetry_msg_.active_tools = j["active_tools"].get<std::vector<std::string>>();
            }
        } catch (...) {
            // Silently ignore JSON parsing errors to prevent the node from crashing.
        }
    }
    
    void timer_cb() {
        telemetry_msg_.header.stamp = this->now();
        pub_->publish(telemetry_msg_);
    }

    smart_interfaces::msg::SmartTelemetry telemetry_msg_;
    
    rclcpp::Subscription<std_msgs::msg::String>::SharedPtr fsm_sub_;
    rclcpp::Subscription<std_msgs::msg::String>::SharedPtr nav_sub_;
    rclcpp::Subscription<nav_msgs::msg::Odometry>::SharedPtr odom_sub_;
    rclcpp::Subscription<std_msgs::msg::Float32>::SharedPtr dose_sub_;
    rclcpp::Subscription<std_msgs::msg::Bool>::SharedPtr light_sub_;
    rclcpp::Subscription<std_msgs::msg::String>::SharedPtr payload_sub_;
    
    rclcpp::Publisher<smart_interfaces::msg::SmartTelemetry>::SharedPtr pub_;
    rclcpp::TimerBase::SharedPtr timer_;
};

int main(int argc, char **argv) {
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<TelemetryMuxCpp>());
    rclcpp::shutdown();
    return 0;
}