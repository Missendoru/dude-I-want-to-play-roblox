import socket, struct, time, signal, sys, os, datetime, platform, select, subprocess

debug_mode, last_update_time, last_button_state, running = False, time.time(), 0, True
throttle_interval, gamepad, connected_devices = 0.005, None, {}
roblox_mode, last_touch_x, last_touch_y = False, None, None

KEY_A, KEY_B, KEY_SELECT, KEY_START = 1, 2, 4, 8
KEY_DRIGHT, KEY_DLEFT, KEY_DUP, KEY_DDOWN = 16, 32, 64, 128
KEY_R, KEY_L, KEY_X, KEY_Y, KEY_ZL, KEY_ZR = 256, 512, 1024, 2048, 4096, 8192
KEY_TOUCH = 16384

os_name = platform.system()
print(f"Detected OS: {os_name}")

try: import psutil; HAS_PSUTIL = True
except ImportError: HAS_PSUTIL = False

if os_name == "Windows":
  try: import vgamepad as vg; gamepad_type = "vgamepad"
  except ImportError: print("Missing 'vgamepad'. Run: pip install vgamepad"); sys.exit(1)
elif os_name == "Linux":
  try: import uinput; gamepad_type = "uinput"
  except ImportError: print("Missing 'python-uinput'. Run: pip install python-uinput"); sys.exit(1)
else: print(f"Unsupported OS: {os_name}"); sys.exit(1)

def yayroblox():
  if HAS_PSUTIL:
    try:
      for proc in psutil.process_iter(['name']):
        pn = (proc.info['name'] or '').lower()
        return True if 'roblox' in pn or 'sober' in pn else next
      return False
    except Exception: pass
  try:
    if os_name == "Windows":
      out = subprocess.check_output('tasklist /FI "IMAGENAME eq RobloxPlayerBeta.exe"', shell=True, stderr=subprocess.DEVNULL).decode()
      return "RobloxPlayerBeta.exe" in out
    elif os_name == "Linux":
      out = subprocess.check_output(['pgrep', '-i', 'roblox'], stderr=subprocess.DEVNULL).decode()
      return bool(out.strip())
  except Exception: return False
  return False

def setup_controller():
  try:
    if gamepad_type == "vgamepad":
      dev = vg.VX360Gamepad(); print("Xbox 360 controller initialized (Windows)"); dev.reset(); return dev
    elif gamepad_type == "uinput":
      ev = (uinput.BTN_A, uinput.BTN_B, uinput.BTN_X, uinput.BTN_Y, uinput.BTN_TL, uinput.BTN_TR, uinput.BTN_START, uinput.BTN_SELECT, uinput.BTN_THUMBL, uinput.BTN_THUMBR, uinput.ABS_X + (-32768, 32767, 0, 0), uinput.ABS_Y + (-32768, 32767, 0, 0), uinput.ABS_RX + (-32768, 32767, 0, 0), uinput.ABS_RY + (-32768, 32767, 0, 0), uinput.ABS_Z + (0, 255, 0, 0), uinput.ABS_RZ + (0, 255, 0, 0), uinput.ABS_HAT0X + (-1, 1, 0, 0), uinput.ABS_HAT0Y + (-1, 1, 0, 0))
      dev = uinput.Device(ev, name="3DS Controller"); print("Linux uinput controller initialized"); return dev
  except Exception as e: print(f"Failed to initialize controller: {e}"); return None

def map_axis_value(v, min_in=-150, max_in=150, min_out=-32768, max_out=32767):
  if abs(v) < 15: return 0
  v = max(min_in, min(max_in, v))
  return int(((v - min_in) * (max_out - min_out)) / (max_in - min_in) + min_out)

def process_touch_delta(tx, ty, touched):
  global last_touch_x, last_touch_y
  if not touched or (tx <= 0 and ty <= 0): last_touch_x, last_touch_y = None, None; return 0, 0
  if last_touch_x is None or last_touch_y is None: last_touch_x, last_touch_y = tx, ty; return 0, 0
  dx, dy = tx - last_touch_x, last_touch_y - ty
  last_touch_x, last_touch_y = tx, ty
  return max(-32768, min(32767, dx * 3000)), max(-32768, min(32767, dy * 3000))

def extract_right_stick(d, btns, r_mode, r_press, cx, cy):
  tx, ty = (struct.unpack("=H", d[8:10])[0], struct.unpack("=H", d[10:12])[0]) if len(d) >= 12 else (0, 0)
  mx, my = process_touch_delta(tx, ty, bool(btns & KEY_TOUCH) or (tx > 0 or ty > 0))
  return (mx, my) if mx != 0 or my != 0 else ((map_axis_value(cx), map_axis_value(cy)) if r_mode and r_press else (map_axis_value(struct.unpack("=h", d[12:14])[0] if len(d) >= 14 else 0), map_axis_value(struct.unpack("=h", d[14:16])[0] if len(d) >= 16 else 0)))

def signal_handler(sig, frame): global running; print("\nExiting..."); running = False

def handle_windows_controller(d, gp):
  global last_button_state, roblox_mode
  b = struct.unpack("=I", d[0:4])[0]
  bp, rp, dup = bool(b & KEY_B), bool(b & KEY_R), bool(b & KEY_DUP)
  b_act, r2_act, r3_act, dup_act = (False, bool((b & KEY_ZR) or bp), rp and dup, dup and not rp) if roblox_mode else (bp, bool(b & KEY_ZR), False, dup)

  for btn, act in [(vg.XUSB_BUTTON.XUSB_GAMEPAD_A, bool(b & KEY_A)), (vg.XUSB_BUTTON.XUSB_GAMEPAD_B, b_act), (vg.XUSB_BUTTON.XUSB_GAMEPAD_X, bool(b & KEY_X)), (vg.XUSB_BUTTON.XUSB_GAMEPAD_Y, bool(b & KEY_Y)), (vg.XUSB_BUTTON.XUSB_GAMEPAD_LEFT_SHOULDER, bool(b & KEY_L)), (vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER, rp), (vg.XUSB_BUTTON.XUSB_GAMEPAD_START, bool(b & KEY_START)), (vg.XUSB_BUTTON.XUSB_GAMEPAD_BACK, bool(b & KEY_SELECT)), (vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_THUMB, r3_act), (vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_UP, dup_act), (vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_DOWN, bool(b & KEY_DDOWN)), (vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_LEFT, bool(b & KEY_DLEFT)), (vg.XUSB_BUTTON.XUSB_GAMEPAD_DPAD_RIGHT, bool(b & KEY_DRIGHT))]:
    gp.press_button(btn) if act else gp.release_button(btn)

  gp.left_trigger(255 if (b & KEY_ZL) else 0)
  gp.right_trigger(255 if r2_act else 0)
  cx, cy = struct.unpack("=h", d[4:6])[0], struct.unpack("=h", d[6:8])[0]
  lx, ly = (0, 0) if roblox_mode and rp else (map_axis_value(cx), map_axis_value(cy))
  rx, ry = extract_right_stick(d, b, roblox_mode, rp, cx, cy)
  gp.left_joystick(lx, ly); gp.right_joystick(rx, ry); gp.update()
  last_button_state = b

def handle_linux_controller(d, gp):
  global last_button_state, roblox_mode
  b = struct.unpack("=I", d[0:4])[0]
  bp, rp, dup = bool(b & KEY_B), bool(b & KEY_R), bool(b & KEY_DUP)
  b_act, r2_act, r3_act, dup_act = (False, bool((b & KEY_ZR) or bp), rp and dup, dup and not rp) if roblox_mode else (bp, bool(b & KEY_ZR), False, dup)

  for btn, act in [(uinput.BTN_A, bool(b & KEY_A)), (uinput.BTN_B, b_act), (uinput.BTN_X, bool(b & KEY_X)), (uinput.BTN_Y, bool(b & KEY_Y)), (uinput.BTN_TL, bool(b & KEY_L)), (uinput.BTN_TR, rp), (uinput.BTN_START, bool(b & KEY_START)), (uinput.BTN_SELECT, bool(b & KEY_SELECT)), (uinput.BTN_THUMBR, r3_act)]:
    gp.emit(btn, 1 if act else 0, syn=False)

  gp.emit(uinput.ABS_Z, 255 if (b & KEY_ZL) else 0, syn=False)
  gp.emit(uinput.ABS_RZ, 255 if r2_act else 0, syn=False)
  gp.emit(uinput.ABS_HAT0Y, -1 if dup_act else (1 if b & KEY_DDOWN else 0), syn=False)
  gp.emit(uinput.ABS_HAT0X, -1 if b & KEY_DLEFT else (1 if b & KEY_DRIGHT else 0), syn=False)
  cx, cy = struct.unpack("=h", d[4:6])[0], struct.unpack("=h", d[6:8])[0]
  lx, ly = (0, 0) if roblox_mode and rp else (map_axis_value(cx), map_axis_value(cy))
  rx, ry = extract_right_stick(d, b, roblox_mode, rp, cx, cy)
  gp.emit(uinput.ABS_X, lx, syn=False); gp.emit(uinput.ABS_Y, -ly, syn=False)
  gp.emit(uinput.ABS_RX, rx, syn=False); gp.emit(uinput.ABS_RY, -ry, syn=False)
  gp.syn(); last_button_state = b

def handle_controller_state(d, addr, gp):
  global last_update_time, connected_devices, gamepad_type
  ip = addr[0]
  if ip not in connected_devices: print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] New 3DS connected from {ip}")
  connected_devices[ip] = time.time()
  ct = time.time()
  if ct - last_update_time < throttle_interval: return
  last_update_time = ct
  if len(d) == 5 and d == b'ping\x00': server_socket.sendto(b'pong', addr); return

  if len(d) >= 8:
    if debug_mode:
      b = struct.unpack("=I", d[0:4])[0]
      tx, ty = (struct.unpack("=H", d[8:10])[0], struct.unpack("=H", d[10:12])[0]) if len(d) >= 12 else (0, 0)
      print(f"Buttons: {b} | Touch Flag: {bool(b & KEY_TOUCH)} | X: {tx}, Y: {ty}")
    handle_windows_controller(d, gp) if gamepad_type == "vgamepad" else handle_linux_controller(d, gp)

def check_inactive_devices():
  global connected_devices
  ct = time.time()
  for addr, ls in list(connected_devices.items()):
    if ct - ls > 10:
      print(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 3DS at {addr} disconnected (timeout)")
      del connected_devices[addr]

def main():
  global debug_mode, running, gamepad, gamepad_type, server_socket, roblox_mode
  signal.signal(signal.SIGINT, signal_handler); signal.signal(signal.SIGTERM, signal_handler)

  if "--debug" in sys.argv: debug_mode = True; print("Debug mode enabled")
  gamepad = setup_controller()
  return sys.exit(1) unless gamepad

  server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
  server_socket.bind(('0.0.0.0', 8888))
  server_socket.settimeout(0.5)

  print(f"3DS Receiver Active on port 8888 ({os_name})")
  print("Touchscreen drag gestures active for Right Stick camera pan.")

  last_check_time, last_proc_check_time = time.time(), 0

  try:
    while running:
      ct = time.time()
      if ct - last_proc_check_time > 2.0:
        is_running = yayroblox()
        if is_running != roblox_mode:
          roblox_mode = is_running
          mstr = "Roblox Mode (B=R2, R-Hold=RightStick, R+DpadUp=R3)" if roblox_mode else "Standard Controller Mode"
          print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] Config Profile Switched -> {mstr}")
        last_proc_check_time = ct

      try:
        ready, _, _ = select.select([server_socket], [], [], 0.05)
        if ready:
          d, addr = server_socket.recvfrom(1024)
          handle_controller_state(d, addr, gamepad)
        if ct - last_check_time > 2:
          check_inactive_devices()
          last_check_time = ct
      except socket.timeout: continue
      except Exception as e: print(f"Socket error: {e}") if debug_mode else next
  finally:
    print("Shutting down...")
    gamepad.reset() if gamepad and gamepad_type == "vgamepad" else next
    server_socket.close()

if __name__ == "__main__": main()
