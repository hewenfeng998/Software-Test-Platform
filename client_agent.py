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

DEFAULT_SERVER_URL = "http://192.168.31.182:5000"
SERVER_URL = DEFAULT_SERVER_URL
HEARTBEAT_INTERVAL = 5
SCREENSHOT_INTERVAL = 0.15
SCALE_FACTOR = 0.5
IMAGE_QUALITY = 50
CONTROL_INTERVAL = 0.02

current_scale = SCALE_FACTOR
current_dpi = 1.0

machine_id = None

def get_system_info():
    screen_width = 1920
    screen_height = 1080
    dpi_scale = 1.0
    
    try:
        if platform.system() == "Windows":
            import pyautogui
            screen_width, screen_height = pyautogui.size()
            
            try:
                import ctypes
                user32 = ctypes.windll.user32
                user32.SetProcessDPIAware()
                dpi_x = user32.GetDpiForSystem()
                dpi_scale = dpi_x / 96.0
            except Exception:
                pass
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
                            
            try:
                result = subprocess.run(['xdpyinfo'], capture_output=True, text=True)
                for line in result.stdout.split('\n'):
                    if 'resolution:' in line:
                        parts = line.split()
                        dpi_x = int(parts[1].split('x')[0])
                        dpi_scale = dpi_x / 96.0
                        break
            except Exception:
                pass
    except Exception:
        pass
    
    info = {
        "hostname": socket.gethostname(),
        "os_type": "windows" if platform.system() == "Windows" else "linux",
        "os_version": platform.version(),
        "cpu_count": os.cpu_count(),
        "ip_address": get_local_ip(),
        "screen_width": screen_width,
        "screen_height": screen_height,
        "dpi_scale": dpi_scale
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
                
                try:
                    response = requests.get(
                        f"{SERVER_URL}/balongma/get_resolution/{machine_id}",
                        timeout=2
                    )
                    if response.status_code == 200:
                        global current_scale
                        data = response.json()
                        current_scale = data.get('scale', SCALE_FACTOR)
                        print(f"分辨率缩放更新为: {current_scale}")
                except Exception as e:
                    pass
                
                try:
                    response = requests.get(
                        f"{SERVER_URL}/balongma/get_dpi/{machine_id}",
                        timeout=2
                    )
                    if response.status_code == 200:
                        global current_dpi
                        data = response.json()
                        current_dpi = data.get('dpi', 1.0)
                        print(f"DPI缩放更新为: {current_dpi}")
                except Exception as e:
                    pass
        except Exception as e:
            print(f"心跳失败: {e}")
        time.sleep(HEARTBEAT_INTERVAL)

def capture_screen():
    try:
        if platform.system() == "Windows":
            try:
                import pyautogui
                screenshot = pyautogui.screenshot()
                width, height = screenshot.size
                new_width = int(width * current_scale)
                new_height = int(height * current_scale)
                screenshot = screenshot.resize((new_width, new_height), 1)
                import io
                buffer = io.BytesIO()
                screenshot.save(buffer, format='JPEG', quality=IMAGE_QUALITY, optimize=True)
                data = buffer.getvalue()
                print(f"截图成功，大小: {len(data)/1024:.1f} KB, 分辨率: {new_width}x{new_height}, 缩放: {current_scale}")
                return data
            except Exception as e:
                print(f"pyautogui截图失败: {e}")
                try:
                    import mss
                    import mss.tools
                    with mss.mss() as sct:
                        monitor = sct.monitors[0]
                        sct_img = sct.grab(monitor)
                        from PIL import Image
                        screenshot = Image.frombytes('RGB', sct_img.size, sct_img.bgra, 'raw', 'BGRX')
                        width, height = screenshot.size
                        new_width = int(width * current_scale)
                        new_height = int(height * current_scale)
                        screenshot = screenshot.resize((new_width, new_height), 1)
                        import io
                        buffer = io.BytesIO()
                        screenshot.save(buffer, format='JPEG', quality=IMAGE_QUALITY, optimize=True)
                        data = buffer.getvalue()
                        print(f"mss截图成功，大小: {len(data)/1024:.1f} KB, 分辨率: {new_width}x{new_height}, 缩放: {current_scale}")
                        return data
                except Exception as e2:
                    print(f"mss截图也失败: {e2}")
                    try:
                        from PIL import ImageGrab
                        screenshot = ImageGrab.grab()
                        width, height = screenshot.size
                        new_width = int(width * current_scale)
                        new_height = int(height * current_scale)
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
                new_width = int(width * current_scale)
                new_height = int(height * current_scale)
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

SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080

def update_screen_size():
    global SCREEN_WIDTH, SCREEN_HEIGHT
    try:
        if platform.system() == "Windows":
            import pyautogui
            SCREEN_WIDTH, SCREEN_HEIGHT = pyautogui.size()
        else:
            import subprocess
            result = subprocess.run(['xrandr'], capture_output=True, text=True)
            for line in result.stdout.split('\n'):
                if '*' in line and '+' in line:
                    parts = line.split()
                    for part in parts:
                        if 'x' in part and '*' in part:
                            SCREEN_WIDTH, SCREEN_HEIGHT = map(int, part.split('x')[0:2])
                            break
    except Exception:
        pass

update_screen_size()

def process_command(cmd):
    cmd_type = cmd.get('type')
    
    try:
        if platform.system() == "Windows":
            import pyautogui
            pyautogui.FAILSAFE = False
            
            if cmd_type == 'move':
                x_ratio = cmd.get('x', 0)
                y_ratio = cmd.get('y', 0)
                x = int(x_ratio * SCREEN_WIDTH)
                y = int(y_ratio * SCREEN_HEIGHT)
                pyautogui.moveTo(x, y, duration=0)
                print(f"移动鼠标到: ({x}, {y}), 屏幕: {SCREEN_WIDTH}x{SCREEN_HEIGHT}")
                
            elif cmd_type == 'click':
                button = cmd.get('button', 'left')
                x_ratio = cmd.get('x')
                y_ratio = cmd.get('y')
                is_down = cmd.get('down', False)
                is_up = cmd.get('up', False)
                
                if x_ratio is not None and y_ratio is not None:
                    x = int(x_ratio * SCREEN_WIDTH)
                    y = int(y_ratio * SCREEN_HEIGHT)
                    pyautogui.moveTo(x, y, duration=0)
                    print(f"点击位置: ({x}, {y}), 按钮: {button}, 屏幕: {SCREEN_WIDTH}x{SCREEN_HEIGHT}")
                
                if is_down:
                    if button == 'left':
                        pyautogui.mouseDown(button='left')
                    elif button == 'right':
                        pyautogui.mouseDown(button='right')
                elif is_up:
                    if button == 'left':
                        pyautogui.mouseUp(button='left')
                    elif button == 'right':
                        pyautogui.mouseUp(button='right')
                else:
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
                x_ratio = cmd.get('x', 0)
                y_ratio = cmd.get('y', 0)
                x = int(x_ratio * SCREEN_WIDTH)
                y = int(y_ratio * SCREEN_HEIGHT)
                mouse.position = (x, y)
                
            elif cmd_type == 'click':
                button = cmd.get('button', 'left')
                x_ratio = cmd.get('x')
                y_ratio = cmd.get('y')
                is_down = cmd.get('down', False)
                is_up = cmd.get('up', False)
                
                if x_ratio is not None and y_ratio is not None:
                    x = int(x_ratio * SCREEN_WIDTH)
                    y = int(y_ratio * SCREEN_HEIGHT)
                    mouse.position = (x, y)
                
                if is_down:
                    if button == 'left':
                        mouse.press(Button.left)
                    elif button == 'right':
                        mouse.press(Button.right)
                elif is_up:
                    if button == 'left':
                        mouse.release(Button.left)
                    elif button == 'right':
                        mouse.release(Button.right)
                else:
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
                
        print(f"执行命令: {cmd_type}, DPI缩放: {current_dpi}")
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
    global SERVER_URL
    
    print("=" * 60)
    print("      白龙马自动化测试 - 客户端代理")
    print("=" * 60)
    
    if len(sys.argv) > 1:
        SERVER_URL = sys.argv[1]
        print(f"使用命令行指定的服务器地址: {SERVER_URL}")
    else:
        print(f"使用默认服务器地址: {SERVER_URL}")
        print("提示: 可通过命令行参数指定服务器地址，如: python client_agent.py http://your-server:5000")
    
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