#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
白龙马自动化测试 - 客户端代理
支持远程桌面控制
"""

import os
import sys
import json
import time
import socket
import platform
import requests
import threading

SERVER_URL = "http://192.168.31.182:5000"
HEARTBEAT_INTERVAL = 5
SCREENSHOT_INTERVAL = 0.3
SCALE_FACTOR = 0.6
IMAGE_QUALITY = 40
CONTROL_INTERVAL = 0.05

machine_id = None

def get_system_info():
    screen_width = 1920
    screen_height = 1080
    try:
        if platform.system() == "Windows":
            import pyautogui
            screen_width, screen_height = pyautogui.size()
        else:
            import subprocess
            result = subprocess.run(['xrandr'], capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                if '*' in line and '+' in line:
                    parts = line.split()
                    for part in parts:
                        if 'x' in part and '*' in part:
                            screen_width, screen_height = map(int, part.split('x')[0:2])
                            break
    except Exception:
        pass
    
    info = {
        "hostname": socket.gethostname(),
        "os_type": "windows" if platform.system() == "Windows" else "linux",
        "os_version": platform.version(),
        "cpu_count": os.cpu_count(),
        "ip_address": get_local_ip(),
        "screen_width": screen_width,
        "screen_height": screen_height
    }
    return info

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def register_with_server():
    global machine_id
    try:
        info = get_system_info()
        response = requests.post(
            f"{SERVER_URL}/balongma/register",
            json=info,
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            machine_id = data.get('machine_id')
            return machine_id
        return None
    except Exception as e:
        print(f"注册失败: {e}")
        return None

def send_heartbeat():
    global machine_id
    while True:
        try:
            if machine_id:
                response = requests.post(
                    f"{SERVER_URL}/balongma/heartbeat/{machine_id}",
                    timeout=5
                )
                if response.status_code != 200:
                    print("心跳失败，重新注册...")
                    register_with_server()
        except Exception as e:
            print(f"心跳失败: {e}")
        time.sleep(HEARTBEAT_INTERVAL)

def capture_screen():
    try:
        if platform.system() == "Windows":
            try:
                import mss
                import mss.tools
                with mss.mss() as sct:
                    monitor = sct.monitors[1]
                    sct_img = sct.grab(monitor)
                    from PIL import Image
                    screenshot = Image.frombytes('RGB', sct_img.size, sct_img.bgra, 'raw', 'BGRX')
                    width, height = screenshot.size
                    new_width = int(width * SCALE_FACTOR)
                    new_height = int(height * SCALE_FACTOR)
                    screenshot = screenshot.resize((new_width, new_height), 1)
                    import io
                    buffer = io.BytesIO()
                    screenshot.save(buffer, format='JPEG', quality=IMAGE_QUALITY, optimize=True)
                    data = buffer.getvalue()
                    print(f"截图成功，大小: {len(data)/1024:.1f} KB, 分辨率: {new_width}x{new_height}")
                    return data
            except Exception as e:
                print(f"mss截图失败: {e}")
                try:
                    import pyautogui
                    screenshot = pyautogui.screenshot()
                    width, height = screenshot.size
                    new_width = int(width * SCALE_FACTOR)
                    new_height = int(height * SCALE_FACTOR)
                    screenshot = screenshot.resize((new_width, new_height), 1)
                    import io
                    buffer = io.BytesIO()
                    screenshot.save(buffer, format='JPEG', quality=IMAGE_QUALITY, optimize=True)
                    data = buffer.getvalue()
                    print(f"pyautogui截图成功，大小: {len(data)/1024:.1f} KB, 分辨率: {new_width}x{new_height}")
                    return data
                except Exception as e2:
                    print(f"pyautogui截图失败: {e2}")
                    try:
                        from PIL import ImageGrab
                        screenshot = ImageGrab.grab()
                        width, height = screenshot.size
                        new_width = int(width * SCALE_FACTOR)
                        new_height = int(height * SCALE_FACTOR)
                        screenshot = screenshot.resize((new_width, new_height), 1)
                        import io
                        buffer = io.BytesIO()
                        screenshot.save(buffer, format='JPEG', quality=IMAGE_QUALITY, optimize=True)
                        data = buffer.getvalue()
                        print(f"PIL截图成功，大小: {len(data)/1024:.1f} KB, 分辨率: {new_width}x{new_height}")
                        return data
                    except Exception as e3:
                        print(f"PIL截图也失败: {e3}")
                        return None
        else:
            try:
                from PIL import ImageGrab
                screenshot = ImageGrab.grab()
                width, height = screenshot.size
                new_width = int(width * SCALE_FACTOR)
                new_height = int(height * SCALE_FACTOR)
                screenshot = screenshot.resize((new_width, new_height), 1)
                import io
                buffer = io.BytesIO()
                screenshot.save(buffer, format='JPEG', quality=IMAGE_QUALITY, optimize=True)
                data = buffer.getvalue()
                print(f"截图成功，大小: {len(data)/1024:.1f} KB, 分辨率: {new_width}x{new_height}")
                return data
            except Exception as e:
                print(f"截图失败: {e}")
                return None
    except Exception as e:
        print(f"截图异常: {e}")
        return None

def need_screenshot():
    global machine_id
    try:
        response = requests.get(
            f"{SERVER_URL}/balongma/need_screenshot/{machine_id}",
            timeout=1
        )
        if response.status_code == 200:
            data = response.json()
            return data.get('need', False)
    except Exception as e:
        pass
    return False

def execute_control():
    global machine_id
    while True:
        if machine_id:
            try:
                response = requests.get(
                    f"{SERVER_URL}/balongma/get_command/{machine_id}",
                    timeout=0.5
                )
                if response.status_code == 200:
                    cmd = response.json()
                    if cmd.get('type'):
                        process_command(cmd)
            except Exception as e:
                pass
        time.sleep(CONTROL_INTERVAL)

def process_command(cmd):
    cmd_type = cmd.get('type')
    
    try:
        if platform.system() == "Windows":
            import pyautogui
            pyautogui.FAILSAFE = False
            
            if cmd_type == 'move':
                x = int(cmd.get('x', 0) / SCALE_FACTOR)
                y = int(cmd.get('y', 0) / SCALE_FACTOR)
                pyautogui.moveTo(x, y, duration=0)
                
            elif cmd_type == 'click':
                button = cmd.get('button', 'left')
                if button == 'left':
                    pyautogui.click()
                elif button == 'right':
                    pyautogui.click(button='right')
                    
            elif cmd_type == 'scroll':
                delta = cmd.get('delta', 0)
                pyautogui.scroll(delta)
                
            elif cmd_type == 'type':
                text = cmd.get('text', '')
                pyautogui.typewrite(text)
                
            elif cmd_type == 'key':
                key = cmd.get('key', '')
                pyautogui.press(key)
                
        else:
            from pynput.mouse import Controller, Button
            from pynput.keyboard import Controller as KeyboardController, Key
            mouse = Controller()
            keyboard = KeyboardController()
            
            if cmd_type == 'move':
                x = int(cmd.get('x', 0) / SCALE_FACTOR)
                y = int(cmd.get('y', 0) / SCALE_FACTOR)
                mouse.position = (x, y)
                
            elif cmd_type == 'click':
                button = cmd.get('button', 'left')
                if button == 'left':
                    mouse.click(Button.left)
                elif button == 'right':
                    mouse.click(Button.right)
                    
            elif cmd_type == 'scroll':
                delta = cmd.get('delta', 0)
                mouse.scroll(0, delta)
                
            elif cmd_type == 'type':
                text = cmd.get('text', '')
                keyboard.type(text)
                
            elif cmd_type == 'key':
                key = cmd.get('key', '')
                keyboard.press(getattr(Key, key, key))
                keyboard.release(getattr(Key, key, key))
                
        print(f"执行命令: {cmd_type}")
    except Exception as e:
        print(f"执行命令失败: {e}")

def send_screenshot():
    global machine_id
    import base64
    count = 0
    while True:
        if machine_id:
            if need_screenshot():
                screen_data = capture_screen()
                if screen_data:
                    try:
                        encoded = base64.b64encode(screen_data).decode('utf-8')
                        response = requests.post(
                            f"{SERVER_URL}/balongma/screenshot/{machine_id}",
                            data=encoded,
                            headers={'Content-Type': 'text/plain'},
                            timeout=2
                        )
                        if response.status_code == 200:
                            count += 1
                            if count % 10 == 0:
                                print(f"已发送 {count} 帧截图")
                        else:
                            print(f"发送截图失败，状态码: {response.status_code}")
                    except Exception as e:
                        print(f"发送截图失败: {e}")
                else:
                    print("截图数据为空")
            else:
                time.sleep(1)
                continue
        time.sleep(SCREENSHOT_INTERVAL)

def main():
    print("=" * 60)
    print("      白龙马自动化测试 - 客户端代理")
    print("=" * 60)
    
    info = get_system_info()
    print(f"主机名: {info['hostname']}")
    print(f"操作系统: {info['os_type']}")
    print(f"IP地址: {info['ip_address']}")
    print(f"CPU核心: {info['cpu_count']}")
    print("-" * 60)
    
    print("正在连接服务器...")
    if register_with_server():
        print(f"✓ 成功注册到服务器，机器ID: {machine_id}")
        print("✓ 客户端已启动，保持此窗口打开")
        print("✓ 远程桌面服务已启动")
        print("-" * 60)
        
        heartbeat_thread = threading.Thread(target=send_heartbeat, daemon=True)
        heartbeat_thread.start()
        
        screenshot_thread = threading.Thread(target=send_screenshot, daemon=True)
        screenshot_thread.start()
        
        control_thread = threading.Thread(target=execute_control, daemon=True)
        control_thread.start()
        
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n客户端已停止")
    else:
        print("无法连接到服务器，请检查网络连接")
        input("按回车键退出...")
        sys.exit(1)

if __name__ == "__main__":
    main()