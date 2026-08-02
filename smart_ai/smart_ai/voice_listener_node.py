#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from faster_whisper import WhisperModel
import pyaudio
import wave
import threading
import tempfile
import os
import time
import sys
import tty
import termios
import signal

# ROS SETTINGS
VOICE_RAW_TOPIC = '/ai/voice_raw'

class VoiceListenerNode(Node):
    def __init__(self):
        super().__init__('voice_listener_node')
        
        self.voice_pub = self.create_publisher(String, VOICE_RAW_TOPIC, 10)
        
        self.running = True

        self.get_logger().info('Loading Faster-Whisper (CUDA, base.en)...')
        self.model = WhisperModel("base.en", device="cuda", compute_type="float16")
        
        self.chunk = 1024
        self.format = pyaudio.paInt16
        self.channels = 1
        self.rate = 16000
        self.p = pyaudio.PyAudio()
        
        self.is_recording = False
        self.is_processing = False 
        self.frames = []

        self.get_logger().info('Voice Listener Ready. Press SPACE to record.')
        threading.Thread(target=self.terminal_listener, daemon=True).start()

    def get_single_char(self):
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch

    def terminal_listener(self):
        time.sleep(2) 
        self.unlock_terminal() 
        print("\n" + "="*50)
        print(" READY! Press SPACE (once) to start, again to stop.")
        print("="*50 + "\n")
        
        last_press_time = 0
        
        while self.running and rclpy.ok():
            ch = self.get_single_char()
            current_time = time.time()
            
            if self.is_processing:
                continue
            
            if ch == ' ' and (current_time - last_press_time) > 0.3: 
                last_press_time = current_time
                
                if not self.is_recording:
                    self.is_recording = True
                    self.frames = []
                    print("\n RECORDING... (Say)")
                    threading.Thread(target=self.record_audio, daemon=True).start()
                else:
                    self.is_recording = False
                    self.is_processing = True
                    print("Final processing...")
                    
            elif ch == '\x03': 
                self.running = False
                os.kill(os.getpid(), signal.SIGINT)
                break

    def record_audio(self):
        stream = self.p.open(format=self.format, channels=self.channels,
                             rate=self.rate, input=True,
                             frames_per_buffer=self.chunk)
        
        while self.is_recording:
            try:
                data = stream.read(self.chunk, exception_on_overflow=False)
                self.frames.append(data)
            except Exception:
                pass
            
        stream.stop_stream()
        stream.close()
        self.process_audio_final()

    def process_audio_final(self):
        if len(self.frames) < 5: 
            self.unlock_terminal()
            return

        fd, temp_path = tempfile.mkstemp(suffix='.wav')
        os.close(fd)
        
        wf = wave.open(temp_path, 'wb')
        wf.setnchannels(self.channels)
        wf.setsampwidth(self.p.get_sample_size(self.format))
        wf.setframerate(self.rate)
        wf.writeframes(b''.join(self.frames))
        wf.close()

        try:
            # Cheat sheet from the original script
            prompt_cheat_sheet = "Robot commands: forward, back, left, right, turn around, degrees, stop, halt, wait, light on, light off, go to base, head to home, save waypoint alpha, one, two, three, four, five meters, half."
            
            segments, _ = self.model.transcribe(
                temp_path, 
                beam_size=3, 
                language="en", 
                condition_on_previous_text=False,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=300),
                initial_prompt=prompt_cheat_sheet 
            )
            
            clean_text = " ".join([segment.text for segment in segments]).strip()
            
            if clean_text:
                print(f"Recognized: '{clean_text}'")
                
                # Publish to Dispatcher
                msg = String()
                msg.data = clean_text
                self.voice_pub.publish(msg)
                
            else:
                print(' Silence or noise.')
                
        except Exception as e:
            print(f"Error: {e}")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            self.unlock_terminal()
            print("-" * 30)

    def unlock_terminal(self):
        self.is_processing = False
        try:
            termios.tcflush(sys.stdin, termios.TCIFLUSH)
        except Exception:
            pass

def main():
    rclpy.init()
    node = VoiceListenerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.running = False
        try:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, termios.tcgetattr(sys.stdin.fileno()))
        except Exception:
            pass
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()
