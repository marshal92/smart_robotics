#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/float32.hpp>
#include <tf2_ros/transform_listener.h>
#include <tf2_ros/buffer.h>
#include <geometry_msgs/msg/transform_stamped.hpp>
#include <nlohmann/json.hpp>
#include <fstream>
#include <cmath>
#include <vector>
#include <string>
#include <filesystem>
#include <algorithm>

using std::placeholders::_1;

class VirtualGeigerNode : public rclcpp::Node {
public:
    VirtualGeigerNode() : Node("virtual_geiger") {
        this->declare_parameter("map_path", "radiation_map.npy");
        this->declare_parameter("is_active", false);

        map_path_param_ = this->get_parameter("map_path").as_string();
        is_active_ = this->get_parameter("is_active").as_bool();
        
        rad_ox_ = -20.0;
        rad_oy_ = -20.0;
        rad_res_ = 0.05;
        width_ = 800;
        height_ = 800;
        raw_dose_map_.resize(width_ * height_, 0.0f);

        tf_buffer_ = std::make_unique<tf2_ros::Buffer>(this->get_clock());
        
        param_sub_ = this->add_on_set_parameters_callback(
            [this](const std::vector<rclcpp::Parameter> &params) {
                return this->param_callback(params);
            }
        );

        dose_pub_ = this->create_publisher<std_msgs::msg::Float32>("/radiation/dose", 10);
        
        loop_timer_ = this->create_wall_timer(
            std::chrono::milliseconds(200),
            std::bind(&VirtualGeigerNode::loop, this)
        );

        if (is_active_) {
            load_truth_map(map_path_param_);
            enable_tf();
        }
        
        RCLCPP_INFO(this->get_logger(), "Virtual Geiger C++ started. Active: %s", is_active_ ? "true" : "false");
    }

private:
    std::string map_path_param_;
    bool is_active_;
    
    int width_, height_;
    double rad_res_, rad_ox_, rad_oy_;
    std::vector<float> raw_dose_map_;
    bool map_loaded_ = false;

    std::unique_ptr<tf2_ros::Buffer> tf_buffer_;
    std::shared_ptr<tf2_ros::TransformListener> tf_listener_;
    
    rclcpp::node_interfaces::OnSetParametersCallbackHandle::SharedPtr param_sub_;
    rclcpp::Publisher<std_msgs::msg::Float32>::SharedPtr dose_pub_;
    rclcpp::TimerBase::SharedPtr loop_timer_;

    void enable_tf() {
        if (!tf_listener_) {
            tf_listener_ = std::make_shared<tf2_ros::TransformListener>(*tf_buffer_);
            RCLCPP_INFO(this->get_logger(), "TF Listener enabled");
        }
    }

    void disable_tf() {
        if (tf_listener_) {
            tf_listener_.reset();
            RCLCPP_INFO(this->get_logger(), "TF Listener disabled");
        }
    }

    rcl_interfaces::msg::SetParametersResult param_callback(const std::vector<rclcpp::Parameter> &params) {
        for (const auto &param : params) {
            if (param.get_name() == "is_active") {
                is_active_ = param.as_bool();
                if (is_active_) {
                    load_truth_map(map_path_param_);
                    enable_tf();
                } else {
                    disable_tf();
                    std_msgs::msg::Float32 msg;
                    msg.data = 0.0f;
                    dose_pub_->publish(msg);
                }
            } else if (param.get_name() == "map_path") {
                std::string new_path = param.as_string();
                map_path_param_ = new_path;
                if (is_active_) {
                    load_truth_map(map_path_param_);
                }
            }
        }
        rcl_interfaces::msg::SetParametersResult result;
        result.successful = true;
        return result;
    }

    void load_truth_map(const std::string &filename) {
        std::string base_dir = "/home/oleksandr/ros2_ws/src/smart_robotics/smart_radiation/maps";
        std::string map_file;
        std::filesystem::path p(filename);
        if (p.is_absolute()) {
            map_file = filename;
        } else {
            map_file = base_dir + "/" + filename;
        }
        
        std::string base_name = map_file.substr(0, map_file.find_last_of('.'));
        std::string ext = map_file.substr(map_file.find_last_of('.'));
        if (ext != ".npy") {
            map_file += ".npy";
            base_name = map_file.substr(0, map_file.find_last_of('.'));
        }
        
        std::string meta_file = base_name + "_meta.json";

        if (std::filesystem::exists(map_file)) {
            std::ifstream in(map_file, std::ios::binary);
            if (in) {
                in.seekg(8); 
                unsigned short header_len;
                in.read(reinterpret_cast<char*>(&header_len), 2);
                
                std::string header(header_len, ' ');
                in.read(&header[0], header_len);
                
                // Very basic shape extraction from numpy header
                size_t shape_pos = header.find("'shape': (");
                if (shape_pos != std::string::npos) {
                    size_t comma_pos = header.find(",", shape_pos);
                    size_t end_pos = header.find(")", comma_pos);
                    if (comma_pos != std::string::npos && end_pos != std::string::npos) {
                        height_ = std::stoi(header.substr(shape_pos + 10, comma_pos - (shape_pos + 10)));
                        width_ = std::stoi(header.substr(comma_pos + 1, end_pos - (comma_pos + 1)));
                        raw_dose_map_.resize(width_ * height_, 0.0f);
                    }
                }
                
                in.read(reinterpret_cast<char*>(raw_dose_map_.data()), raw_dose_map_.size() * sizeof(float));
                map_loaded_ = true;
            }
            
            if (std::filesystem::exists(meta_file)) {
                std::ifstream f(meta_file);
                nlohmann::json meta;
                f >> meta;
                if (meta.contains("ox")) rad_ox_ = meta["ox"];
                if (meta.contains("oy")) rad_oy_ = meta["oy"];
                if (meta.contains("res")) rad_res_ = meta["res"];
            }
            RCLCPP_INFO(this->get_logger(), "Loaded map: %s", map_file.c_str());
        } else {
            std::fill(raw_dose_map_.begin(), raw_dose_map_.end(), 0.0f);
            map_loaded_ = false;
            RCLCPP_WARN(this->get_logger(), "Map file not found: %s", map_file.c_str());
        }
    }

    void loop() {
        if (!is_active_ || !map_loaded_) return;
        
        geometry_msgs::msg::TransformStamped trans;
        try {
            trans = tf_buffer_->lookupTransform("map", "base_footprint", tf2::TimePointZero);
        } catch (...) {
            return;
        }
        
        float rx = trans.transform.translation.x;
        float ry = trans.transform.translation.y;
        
        int rad_x = std::floor((rx - rad_ox_) / rad_res_);
        int rad_y = std::floor((ry - rad_oy_) / rad_res_);
        
        float dose_val = 0.0f;
        if (rad_x >= 0 && rad_x < width_ && rad_y >= 0 && rad_y < height_) {
            dose_val = raw_dose_map_[rad_y * width_ + rad_x];
            if (std::isnan(dose_val)) dose_val = 0.0f;
        }
        
        std_msgs::msg::Float32 msg;
        msg.data = dose_val;
        dose_pub_->publish(msg);
    }
};

int main(int argc, char **argv) {
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<VirtualGeigerNode>());
    rclcpp::shutdown();
    return 0;
}
