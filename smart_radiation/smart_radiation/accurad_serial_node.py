#!/usr/bin/env python3
"""ROS 2 node for reading Mirion AccuRad PRD telemetry over USB/Serial."""

import serial
import rclpy
from rclpy.node import Node

from smart_radiation.accurad_protocol import (
    AccuradPublishers,
    DEFAULT_DOSE_TOPIC,
    DEFAULT_SERIAL_BAUDRATE,
    DEFAULT_SERIAL_PORT,
    DEVICE_HEADER,
    GET_DEVICE_DATA,
    MAX_FRAME_LEN,
    parse_device_data,
)

MAX_HEADER_SEARCH_BYTES = 128
MAX_CONSECUTIVE_PARSE_ERRORS = 3


class AccuradSerialNode(Node):
    """Polls an AccuRad PRD dosimeter over serial UART and publishes ROS 2 telemetry."""

    def __init__(self):
        super().__init__('accurad_serial_node')

        self.declare_parameter('port', DEFAULT_SERIAL_PORT)
        self.declare_parameter('baudrate', DEFAULT_SERIAL_BAUDRATE)
        self.declare_parameter('rate_hz', 1.0)
        self.declare_parameter('topic', DEFAULT_DOSE_TOPIC)
        self.declare_parameter('dose_scale', 1.0)

        self.port = self.get_parameter('port').get_parameter_value().string_value
        self.baudrate = max(
            int(self.get_parameter('baudrate').get_parameter_value().integer_value),
            1200,
        )
        rate_hz = self.get_parameter('rate_hz').get_parameter_value().double_value
        topic = self.get_parameter('topic').get_parameter_value().string_value
        dose_scale = self.get_parameter('dose_scale').get_parameter_value().double_value

        self.telemetry_pubs = AccuradPublishers(self, topic, dose_scale=dose_scale)
        self.ser = None
        self._consecutive_parse_errors = 0

        self.timer = self.create_timer(1.0 / max(rate_hz, 0.1), self.poll_sensor)
        self.get_logger().info(
            f'AccuRad Serial node started on {self.port} ({self.baudrate} baud) '
            f'-> {topic} (scale={dose_scale})'
        )

    def _connect(self) -> bool:
        if self.ser is not None and self.ser.is_open:
            return True
        try:
            self.ser = serial.Serial(
                self.port,
                self.baudrate,
                timeout=1.0,
                write_timeout=1.0,
                exclusive=True,
            )
            self.ser.reset_input_buffer()
            self._consecutive_parse_errors = 0
            self.get_logger().info(f'Connected to AccuRad PRD on {self.port}')
            return True
        except (serial.SerialException, OSError) as exc:
            self.get_logger().warn(
                f'Waiting for AccuRad on {self.port}: {exc}',
                throttle_duration_sec=5.0,
            )
            self.ser = None
            return False

    def _disconnect(self):
        if self.ser is not None:
            try:
                self.ser.close()
            except Exception:
                pass
            self.ser = None

    def _read_exact(self, size: int) -> bytes:
        data = self.ser.read(size)
        if len(data) != size:
            raise IOError(f'Incomplete serial read ({len(data)}/{size} bytes)')
        return data

    def _read_frame(self) -> bytes:
        sync_buf = bytearray()
        for _ in range(MAX_HEADER_SEARCH_BYTES):
            ch = self.ser.read(1)
            if not ch:
                raise IOError('Timeout waiting for AccuRad frame header')
            sync_buf.extend(ch)
            if sync_buf.endswith(DEVICE_HEADER):
                break
        else:
            raise ValueError(
                f'AccuRad header not found within {MAX_HEADER_SEARCH_BYTES} bytes'
            )

        raw_len = self._read_exact(2)
        data_length = int.from_bytes(raw_len, byteorder='little')
        if data_length < 2 or data_length > MAX_FRAME_LEN:
            raise ValueError(f'Invalid AccuRad payload length: {data_length}')

        return self._read_exact(data_length)

    def poll_sensor(self):
        if not self._connect():
            return

        try:
            self.ser.reset_input_buffer()
            self.ser.write(GET_DEVICE_DATA)
            raw_data = self._read_frame()
            sample = parse_device_data(raw_data)
            self._consecutive_parse_errors = 0
            self.telemetry_pubs.publish(sample)
        except (serial.SerialException, OSError, IOError) as exc:
            self.get_logger().warn(
                f'Serial transport error: {exc}. Reconnecting...',
                throttle_duration_sec=2.0,
            )
            self._disconnect()
        except ValueError as exc:
            self._consecutive_parse_errors += 1
            self.get_logger().warn(
                f'Serial frame parse error ({self._consecutive_parse_errors}/'
                f'{MAX_CONSECUTIVE_PARSE_ERRORS}): {exc}',
                throttle_duration_sec=2.0,
            )
            if self._consecutive_parse_errors >= MAX_CONSECUTIVE_PARSE_ERRORS:
                self._disconnect()

    def destroy_node(self):
        self._disconnect()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = AccuradSerialNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
