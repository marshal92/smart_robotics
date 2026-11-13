"""Shared Mirion AccuRad PRD binary protocol parser and ROS 2 publishing helpers."""

import math
import struct
from typing import Any

from rclpy.node import Node
from std_msgs.msg import Float32

DEFAULT_DOSE_TOPIC = '/radiation/dose'
DEFAULT_CPS_TOPIC = '/accurad/cps'
DEFAULT_BATTERY_TOPIC = '/accurad/battery'

DEFAULT_SERIAL_PORT = '/dev/accurad'
DEFAULT_SERIAL_BAUDRATE = 9600

GET_DEVICE_DATA = bytes(b'\x7E\x04\x00\x11\xA7\x1E\x43\xE7')
GET_DEVICE_INFO = bytes(b'\x7E\x04\x00\x10\xA7\x07\x46\xE7')

DEVICE_HEADER = b'#!AccuRad!#'
HEADER_SIZE = 13  # 11-byte DEVICE_HEADER + 2-byte little-endian payload length
MIN_DATA_FRAME_LEN = 43  # Minimum length covering battery_level at index 40 + 2-byte CRC16
MAX_FRAME_LEN = 512


def crc16(data: bytes, size: int) -> int:
    """Compute Mirion AccuRad CRC-16 checksum (polynomial 0xAC5E, init 0xFFFF)."""
    polynom = 0xAC5E
    crc = 0xFFFF
    if size <= 0 or data is None:
        return 0
    for i in range(size):
        crc ^= data[i]
        if crc == 0:
            crc = 1
        for _ in range(8):
            parity = crc
            crc >>= 1
            if (parity & 1) != 0:
                crc ^= polynom
    return crc


def parse_device_data(raw_data: bytes) -> dict[str, Any]:
    """Validate CRC-16 and unpack GET_DEVICE_DATA payload bytes from AccuRad PRD."""
    data_length = len(raw_data)
    if data_length < MIN_DATA_FRAME_LEN:
        raise ValueError(f'Payload too short ({data_length} < {MIN_DATA_FRAME_LEN} bytes)')

    expected_crc = int.from_bytes(raw_data[data_length - 2:data_length], byteorder='little')
    actual_crc = crc16(raw_data, data_length - 2)
    if actual_crc != expected_crc:
        raise ValueError(f'CRC16 mismatch (expected 0x{expected_crc:04X}, got 0x{actual_crc:04X})')

    dose_rate = float(struct.unpack('<f', raw_data[3:7])[0])
    count_rate = float(struct.unpack('<f', raw_data[7:11])[0])
    battery_level = float(raw_data[40])
    state = int(raw_data[2])

    if not (math.isfinite(dose_rate) and math.isfinite(count_rate) and math.isfinite(battery_level)):
        raise ValueError(
            f'Non-finite telemetry values: dose={dose_rate}, cps={count_rate}, bat={battery_level}'
        )

    return {
        'state': state,
        'dose_rate': dose_rate,
        'count_rate': count_rate,
        'battery_level': battery_level,
    }


class AccuradPublishers:
    """Publishes parsed AccuRad dose rate, CPS, and battery telemetry to ROS 2."""

    def __init__(self, node: Node, dose_topic: str, dose_scale: float = 1.0):
        self._node = node
        self._dose_topic = dose_topic
        self._dose_scale = float(dose_scale)
        self._logged_first_sample = False

        self.dose_pub = node.create_publisher(Float32, dose_topic, 10)
        self.cps_pub = node.create_publisher(Float32, DEFAULT_CPS_TOPIC, 10)
        self.battery_pub = node.create_publisher(Float32, DEFAULT_BATTERY_TOPIC, 10)

    def publish(self, sample: dict[str, Any]) -> bool:
        """Scale dose rate if configured and publish dose, CPS, and battery Float32 messages."""
        scaled_dose = float(sample['dose_rate']) * self._dose_scale
        count_rate = float(sample['count_rate'])
        battery_level = float(sample['battery_level'])

        if not (math.isfinite(scaled_dose) and math.isfinite(count_rate) and math.isfinite(battery_level)):
            self._node.get_logger().warn(
                'Skipping non-finite AccuRad reading after scaling.',
                throttle_duration_sec=5.0,
            )
            return False

        msg_dose = Float32()
        msg_dose.data = scaled_dose
        self.dose_pub.publish(msg_dose)

        msg_cps = Float32()
        msg_cps.data = count_rate
        self.cps_pub.publish(msg_cps)

        msg_bat = Float32()
        msg_bat.data = battery_level
        self.battery_pub.publish(msg_bat)

        if not self._logged_first_sample:
            self._logged_first_sample = True
            self._node.get_logger().info(
                f'First AccuRad reading on {self._dose_topic}: '
                f'raw_dose={sample["dose_rate"]:.6g}, scaled_dose={scaled_dose:.6g}, '
                f'cps={count_rate:.3f}, battery={battery_level:.0f}%'
            )
        return True
