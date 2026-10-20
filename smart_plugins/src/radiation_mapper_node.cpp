#include <rclcpp/rclcpp.hpp>
#include <std_msgs/msg/float32.hpp>
#include <std_msgs/msg/empty.hpp>
#include <std_srvs/srv/trigger.hpp>
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
using std::placeholders::_2;

class RadiationMapperNode : public rclcpp::Node {
public:
    RadiationMapperNode() : Node("radiation_mapper") {
        this->declare_parameter("map_path", "explored_map.npy");
        this->declare_parameter("is_recording", false);
        this->declare_parameter("width", 800);
        this->declare_parameter("height", 800);
        this->declare_parameter("res", 0.05);
        this->declare_parameter("ox", -20.0);
        this->declare_parameter("oy", -20.0);

        map_path_param_ = this->get_parameter("map_path").as_string();
        is_recording_ = this->get_parameter("is_recording").as_bool();
        width_ = this->get_parameter("width").as_int();
        height_ = this->get_parameter("height").as_int();
        res_ = this->get_parameter("res").as_double();
        ox_ = this->get_parameter("ox").as_double();
        oy_ = this->get_parameter("oy").as_double();

        map_grid_.resize(width_ * height_, 0.0f);
        weight_grid_.resize(width_ * height_, 0.0f);

        resolve_paths(map_path_param_);
        load_map();

        tf_buffer_ = std::make_unique<tf2_ros::Buffer>(this->get_clock());
        
        param_sub_ = this->add_on_set_parameters_callback(
            [this](const std::vector<rclcpp::Parameter> &params) {
                return this->param_callback(params);
            }
        );

        dose_sub_ = this->create_subscription<std_msgs::msg::Float32>(
            "/radiation/dose", 10, std::bind(&RadiationMapperNode::dose_cb, this, _1)
        );

        trigger_pub_ = this->create_publisher<std_msgs::msg::Empty>("/radiation/map_updated", 10);
        
        save_srv_ = this->create_service<std_srvs::srv::Trigger>(
            "~/save_map", std::bind(&RadiationMapperNode::save_map_cb, this, _1, _2)
        );
        clear_srv_ = this->create_service<std_srvs::srv::Trigger>(
            "~/clear_map", std::bind(&RadiationMapperNode::clear_map_cb, this, _1, _2)
        );

        if (is_recording_) {
            enable_tf();
        }

        shm_timer_ = this->create_wall_timer(
            std::chrono::seconds(2),
            std::bind(&RadiationMapperNode::timer_shm_update, this)
        );
        disk_timer_ = this->create_wall_timer(
            std::chrono::seconds(60),
            std::bind(&RadiationMapperNode::timer_disk_save, this)
        );
        
        roi_r_ = std::round(1.0 / res_);
        int size = 2 * roi_r_ + 1;
        splat_mask_.resize(size * size, 0.0f);
        splat_spot_base_.resize(size * size, 0.0f);
        float sigma = 0.5f;
        
        for (int y = -roi_r_; y <= roi_r_; ++y) {
            for (int x = -roi_r_; x <= roi_r_; ++x) {
                float dist_sq = std::pow(x * res_, 2) + std::pow(y * res_, 2);
                float mask = std::exp(-dist_sq / (2.0f * std::pow(sigma / 2.0f, 2)));
                mask = std::clamp(mask, 0.0f, 1.0f);
                float spot_base = std::exp(-dist_sq / (2.0f * std::pow(sigma, 2)));
                
                splat_mask_[(y + roi_r_) * size + (x + roi_r_)] = mask;
                splat_spot_base_[(y + roi_r_) * size + (x + roi_r_)] = spot_base;
            }
        }
        RCLCPP_INFO(this->get_logger(), "Radiation Mapper C++ started. Recording: %s", is_recording_ ? "true" : "false");
    }

    ~RadiationMapperNode() {
        save_map();
    }

private:
    std::string map_path_param_;
    bool is_recording_;
    int width_, height_;
    double res_, ox_, oy_;
    std::vector<float> map_grid_;
    std::vector<float> weight_grid_;
    bool map_dirty_ = false;
    
    float last_saved_rx_ = 0.0f;
    float last_saved_ry_ = 0.0f;
    float last_saved_dose_ = -1.0f;
    
    std::string map_file_, meta_file_, weight_file_, log_file_;
    const std::string shm_file_ = "/dev/shm/live_rad_map.npy";
    const std::string shm_meta_ = "/dev/shm/live_rad_map_meta.json";

    std::unique_ptr<tf2_ros::Buffer> tf_buffer_;
    std::shared_ptr<tf2_ros::TransformListener> tf_listener_;
    
    rclcpp::node_interfaces::OnSetParametersCallbackHandle::SharedPtr param_sub_;
    rclcpp::Subscription<std_msgs::msg::Float32>::SharedPtr dose_sub_;
    rclcpp::Publisher<std_msgs::msg::Empty>::SharedPtr trigger_pub_;
    rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr save_srv_;
    rclcpp::Service<std_srvs::srv::Trigger>::SharedPtr clear_srv_;
    rclcpp::TimerBase::SharedPtr shm_timer_;
    rclcpp::TimerBase::SharedPtr disk_timer_;
    
    int roi_r_;
    std::vector<float> splat_mask_;
    std::vector<float> splat_spot_base_;

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
            if (param.get_name() == "is_recording") {
                is_recording_ = param.as_bool();
                if (is_recording_) {
                    enable_tf();
                    map_dirty_ = true;
                    timer_shm_update();
                } else {
                    disable_tf();
                }
            } else if (param.get_name() == "map_path") {
                std::string new_path = param.as_string();
                if (new_path != map_path_param_) {
                    save_map();
                    map_path_param_ = new_path;
                    resolve_paths(new_path);
                    load_map();
                }
            }
        }
        rcl_interfaces::msg::SetParametersResult result;
        result.successful = true;
        return result;
    }

    void resolve_paths(const std::string &filename) {
        std::string base_dir = "/home/oleksandr/ros2_ws/src/smart_robotics/smart_radiation/maps";
        std::filesystem::path p(filename);
        if (p.is_absolute()) {
            map_file_ = filename;
        } else {
            map_file_ = base_dir + "/" + filename;
        }
        
        std::string base_name = map_file_.substr(0, map_file_.find_last_of('.'));
        std::string ext = map_file_.substr(map_file_.find_last_of('.'));
        if (ext != ".npy") {
            map_file_ += ".npy";
            base_name = map_file_.substr(0, map_file_.find_last_of('.'));
        }
        
        meta_file_ = base_name + "_meta.json";
        weight_file_ = base_name + "_weights.npy";
        log_file_ = base_name + "_log.csv";
    }

    void write_npy(const std::string& filename, const std::vector<float>& data) {
        std::ofstream out(filename, std::ios::binary);
        if (!out) return;
        const char magic[] = "\x93NUMPY";
        out.write(magic, 6);
        out.put(1); out.put(0);
        
        std::string dict = "{'descr': '<f4', 'fortran_order': False, 'shape': (" + std::to_string(height_) + ", " + std::to_string(width_) + "), }";
        int padding = 16 - ((10 + dict.length()) % 16);
        dict.append(padding, ' ');
        dict.back() = '\n';
        
        unsigned short header_len = dict.length();
        out.write(reinterpret_cast<const char*>(&header_len), 2);
        out.write(dict.c_str(), dict.length());
        out.write(reinterpret_cast<const char*>(data.data()), data.size() * sizeof(float));
    }

    void load_npy(const std::string& filename, std::vector<float>& data) {
        std::ifstream in(filename, std::ios::binary);
        if (!in) {
            std::fill(data.begin(), data.end(), 0.0f);
            return;
        }
        in.seekg(8); 
        unsigned short header_len;
        in.read(reinterpret_cast<char*>(&header_len), 2);
        
        std::string header(header_len, ' ');
        in.read(&header[0], header_len);
        
        size_t shape_pos = header.find("'shape': (");
        if (shape_pos != std::string::npos) {
            size_t comma_pos = header.find(",", shape_pos);
            size_t end_pos = header.find(")", comma_pos);
            if (comma_pos != std::string::npos && end_pos != std::string::npos) {
                height_ = std::stoi(header.substr(shape_pos + 10, comma_pos - (shape_pos + 10)));
                width_ = std::stoi(header.substr(comma_pos + 1, end_pos - (comma_pos + 1)));
                data.resize(width_ * height_, 0.0f);
            }
        }
        
        in.read(reinterpret_cast<char*>(data.data()), data.size() * sizeof(float));
    }

    void load_map() {
        if (std::filesystem::exists(map_file_)) {
            load_npy(map_file_, map_grid_);
            if (std::filesystem::exists(meta_file_)) {
                std::ifstream f(meta_file_);
                nlohmann::json meta;
                f >> meta;
                if (meta.contains("width")) width_ = meta["width"];
                if (meta.contains("height")) height_ = meta["height"];
                if (meta.contains("ox")) ox_ = meta["ox"];
                if (meta.contains("oy")) oy_ = meta["oy"];
                if (meta.contains("res")) res_ = meta["res"];
            }
            if (std::filesystem::exists(weight_file_)) {
                load_npy(weight_file_, weight_grid_);
            } else {
                std::fill(weight_grid_.begin(), weight_grid_.end(), 0.0f);
                for (size_t i = 0; i < map_grid_.size(); ++i) {
                    if (map_grid_[i] > 0.0f) weight_grid_[i] = 1.0f;
                }
            }
        } else {
            map_grid_.resize(width_ * height_, 0.0f);
            std::fill(map_grid_.begin(), map_grid_.end(), 0.0f);
            weight_grid_.resize(width_ * height_, 0.0f);
            std::fill(weight_grid_.begin(), weight_grid_.end(), 0.0f);
        }
        save_meta();
        map_dirty_ = false;
        
        if (!std::filesystem::exists(log_file_)) {
            std::ofstream f(log_file_);
            f << "Timestamp,X,Y,Dose\n";
        }
    }

    void save_meta() {
        nlohmann::json meta = {
            {"width", width_}, {"height", height_}, {"res", res_}, {"ox", ox_}, {"oy", oy_}
        };
        std::ofstream f(meta_file_);
        f << meta.dump(4);
    }

    void save_map() {
        write_npy(map_file_ + "_temp.npy", map_grid_);
        std::filesystem::rename(map_file_ + "_temp.npy", map_file_);
        write_npy(weight_file_ + "_temp.npy", weight_grid_);
        std::filesystem::rename(weight_file_ + "_temp.npy", weight_file_);
    }

    void timer_shm_update() {
        if (map_dirty_) {
            write_npy(shm_file_, map_grid_);
            nlohmann::json meta = {
                {"width", width_}, {"height", height_}, {"res", res_}, {"ox", ox_}, {"oy", oy_}
            };
            std::ofstream f(shm_meta_);
            f << meta.dump(4);
            
            std_msgs::msg::Empty msg;
            trigger_pub_->publish(msg);
            map_dirty_ = false;
        }
    }

    void timer_disk_save() {
        if (is_recording_) save_map();
    }

    void dose_cb(const std_msgs::msg::Float32::SharedPtr msg) {
        if (!is_recording_) return;
        float current_dose = msg->data;
        
        geometry_msgs::msg::TransformStamped trans;
        try {
            trans = tf_buffer_->lookupTransform("map", "base_footprint", tf2::TimePointZero);
        } catch (...) {
            return;
        }
        
        float rx = trans.transform.translation.x;
        float ry = trans.transform.translation.y;
        
        if (last_saved_dose_ >= 0) {
            float dx = rx - last_saved_rx_;
            float dy = ry - last_saved_ry_;
            float dist = std::sqrt(dx*dx + dy*dy);
            
            float dose_diff_pct = 0.0f;
            if (last_saved_dose_ > 0) {
                dose_diff_pct = std::abs(current_dose - last_saved_dose_) / last_saved_dose_;
            } else {
                dose_diff_pct = current_dose > 0 ? 1.0f : 0.0f;
            }
            if (dist < 0.2f && dose_diff_pct < 0.15f) return;
        }
        
        last_saved_rx_ = rx;
        last_saved_ry_ = ry;
        last_saved_dose_ = current_dose;
        
        int rad_x = std::round((rx - ox_) / res_);
        int rad_y = std::round((ry - oy_) / res_);
        
        int x_min = rad_x - roi_r_;
        int x_max = rad_x + roi_r_ + 1;
        int y_min = rad_y - roi_r_;
        int y_max = rad_y + roi_r_ + 1;
        
        int map_x_min = std::max(0, x_min);
        int map_x_max = std::min(width_, x_max);
        int map_y_min = std::max(0, y_min);
        int map_y_max = std::min(height_, y_max);
        
        if (map_x_min >= map_x_max || map_y_min >= map_y_max) return;
        
        int mask_x_min = map_x_min - x_min;
        int mask_x_max = mask_x_min + (map_x_max - map_x_min);
        int mask_y_min = map_y_min - y_min;
        int mask_y_max = mask_y_min + (map_y_max - map_y_min);
        
        int mask_size = 2 * roi_r_ + 1;
        
        for (int y = map_y_min, my = mask_y_min; y < map_y_max; ++y, ++my) {
            for (int x = map_x_min, mx = mask_x_min; x < map_x_max; ++x, ++mx) {
                float mask = splat_mask_[my * mask_size + mx];
                float spot = current_dose * splat_spot_base_[my * mask_size + mx];
                
                int map_idx = y * width_ + x;
                float old_weight = weight_grid_[map_idx];
                float new_weight = old_weight + mask;
                float new_weight_safe = std::max(new_weight, 1e-6f);
                
                map_grid_[map_idx] = (map_grid_[map_idx] * old_weight + spot * mask) / new_weight_safe;
                weight_grid_[map_idx] = std::clamp(new_weight, 0.0f, 10.0f);
            }
        }
        map_dirty_ = true;
    }
    
    void save_map_cb(const std_srvs::srv::Trigger::Request::SharedPtr, std_srvs::srv::Trigger::Response::SharedPtr res) {
        save_map();
        res->success = true;
        res->message = "Map saved.";
    }
    
    void clear_map_cb(const std_srvs::srv::Trigger::Request::SharedPtr, std_srvs::srv::Trigger::Response::SharedPtr res) {
        std::fill(map_grid_.begin(), map_grid_.end(), 0.0f);
        std::fill(weight_grid_.begin(), weight_grid_.end(), 0.0f);
        save_map();
        map_dirty_ = true;
        timer_shm_update();
        res->success = true;
        res->message = "Map cleared.";
    }
};

int main(int argc, char **argv) {
    rclcpp::init(argc, argv);
    rclcpp::spin(std::make_shared<RadiationMapperNode>());
    rclcpp::shutdown();
    return 0;
}
