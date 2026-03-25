import os
import json
import time
import threading
import math

# Suppress pygame welcome message
import pygame
from pynput.keyboard import Controller as KeyboardController, Key
from pynput.mouse import Controller as MouseController, Button
from PyQt5.QtCore import QThread, pyqtSignal
from hud_widget import DEFAULT_HUD_ITEMS

try:
    import win32gui
    import win32process
    import psutil
    WINDOWS_AVAILABLE = True
except ImportError:
    WINDOWS_AVAILABLE = False
    print("Warning: win32gui/psutil not available. Profile switching won't work.")

# --- Globals ---
keyboard = KeyboardController()
mouse = MouseController()

active_profile_name = "Default"
profiles = {}

# Map Pygame button IDs to recognizable names (Xbox Standard)
# Note: These indices might vary slightly depending on OS/Drivers, but generally:
BUTTON_MAP = {
    0: "A",
    1: "B",
    2: "X",
    3: "Y",
    4: "LB",
    5: "RB",
    6: "Back",
    7: "Start",
    8: "LS",
    9: "RS",
    10: "Guide"
}

# Map Pynput special keys
SPECIAL_KEYS = {
    "enter": Key.enter,
    "esc": Key.esc,
    "space": Key.space,
    "backspace": Key.backspace,
    "tab": Key.tab,
    "shift": Key.shift,
    "ctrl": Key.ctrl,
    "alt": Key.alt,
    "up": Key.up,
    "down": Key.down,
    "left": Key.left,
    "right": Key.right,
    "cmd": Key.cmd,
    "volume_up": Key.media_volume_up,
    "volume_down": Key.media_volume_down,
    "volume_mute": Key.media_volume_mute,
    "next_track": Key.media_next,
    "prev_track": Key.media_previous,
    "play_pause": Key.media_play_pause
}

# --- Core Logic ---

haptic_enabled = True
global_mouse_speed = 15.0
global_scroll_speed = 0.2
hud_dictionary = {"Default HUD": list(DEFAULT_HUD_ITEMS)}

def load_config():
    global profiles, haptic_enabled, global_mouse_speed, global_scroll_speed, hud_dictionary
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            profiles = data.get("profiles", {})
            haptic_enabled = data.get("haptic_enabled", True)
            global_mouse_speed = data.get("mouse_speed", 15.0)
            global_scroll_speed = data.get("scroll_speed", 0.2)
            
            # Legacy support + multi-hud support
            hud_dictionary = {}
            if "huds" in data:
                hud_dictionary = data["huds"]
            elif "hud_items" in data:
                hud_dictionary["Default HUD"] = data["hud_items"]
            else:
                hud_dictionary["Default HUD"] = list(DEFAULT_HUD_ITEMS)
                
            print("Configuration loaded.")
    except Exception as e:
        print(f"Error loading config.json: {e}")
        profiles = {"Default": {"buttons": {}, "triggers": {}, "axes": {}}}
        haptic_enabled = True
        global_mouse_speed = 15.0
        global_scroll_speed = 0.2
        hud_dictionary = {"Default HUD": list(DEFAULT_HUD_ITEMS)}

def get_active_window_profile():
    if not WINDOWS_AVAILABLE:
        return "Global"
    
    try:
        hwnd = win32gui.GetForegroundWindow()
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        process = psutil.Process(pid)
        process_name = process.name().lower()
        
        # Dynamic search through profiles to find bound executable
        for profile_name, profile_data in profiles.items():
            bound_exe = profile_data.get("process_name", "")
            if bound_exe and bound_exe.lower() == process_name:
                return profile_name
            
    except Exception as e:
        pass # Ignore transient errors when switching windows
        
    return "Global"

def window_monitor_loop():
    global active_profile_name
    while True:
        new_profile = get_active_window_profile()
        if new_profile != active_profile_name:
            if new_profile in profiles:
                active_profile_name = new_profile
                print(f"Switched to profile: {active_profile_name}")
            else:
                 if active_profile_name != "Default":
                     active_profile_name = "Default"
                     print(f"Switched to profile: {active_profile_name} (Fallback)")
        time.sleep(1.0) # Check active window every second

def execute_action(action, state="down"):
    if not action:
        return
        
    action_type = action.get("type", "")
    key_str = action.get("key", "")
    
    if action_type in ["key_press", "key_tap"] and key_str:
        # Check for mouse clicks first
        mouse_btn = None
        if key_str == "mouse_left":
            mouse_btn = Button.left
        elif key_str == "mouse_right":
            mouse_btn = Button.right
        elif key_str == "mouse_middle":
            mouse_btn = Button.middle
            
        if mouse_btn:
            try:
                if action_type == "key_press":
                    if state == "down":
                        mouse.press(mouse_btn)
                    else:
                        mouse.release(mouse_btn)
                elif action_type == "key_tap" and state == "down":
                    mouse.click(mouse_btn)
            except Exception as e:
                print(f"Error clicking {key_str}: {e}")
            return
            

        # Keyboard presses
        key = SPECIAL_KEYS.get(key_str, key_str)
        try:
            if action_type == "key_press":
                if state == "down":
                    keyboard.press(key)
                else:
                    keyboard.release(key)
            elif action_type == "key_tap" and state == "down":
                keyboard.press(key)
                keyboard.release(key)
        except Exception as e:
            print(f"Error pressing {key}: {e}")
            
    elif action_type == "macro" and key_str and state == "down":
        # Handle hotkey sequences separated by '+' (e.g. ctrl+shift+s)
        if '+' in key_str:
            keys = [SPECIAL_KEYS.get(k.strip(), k.strip()) for k in key_str.split('+')]
            try:
                for k in keys:
                    keyboard.press(k)
                for k in reversed(keys):
                    keyboard.release(k)
            except Exception as e:
                 print(f"Error in macro {key_str}: {e}")
        # Handle sequential sequences separated by ',' (e.g. a,b,c)
        elif ',' in key_str:
            keys = [SPECIAL_KEYS.get(k.strip(), k.strip()) for k in key_str.split(',')]
            try:
                for k in keys:
                    keyboard.press(k)
                    keyboard.release(k)
                    time.sleep(0.05)
            except Exception as e:
                 print(f"Error in sequence {key_str}: {e}")
                 
    elif action_type == "run_app" and key_str and state == "down":
        try:
            import subprocess
            subprocess.Popen(key_str, shell=True)
            print(f"Launched application: {key_str}")
        except Exception as e:
            print(f"Error launching {key_str}: {e}")

# Used to rate-limit continuous trigger holding
last_trigger_time = 0

def process_continuous_input(joystick, profile):
    global last_trigger_time
    current_time = time.time()
    
    # --- AXIS PROCESSING (Sticks) ---
    axes_config = profile.get("axes", {})
    if axes_config:
        lx = joystick.get_axis(0) if joystick.get_numaxes() > 0 else 0.0
        ly = joystick.get_axis(1) if joystick.get_numaxes() > 1 else 0.0
        rx = joystick.get_axis(2) if joystick.get_numaxes() > 2 else 0.0
        ry = joystick.get_axis(3) if joystick.get_numaxes() > 3 else 0.0
        
        deadzone = 0.15
        
        def process_axis(axis_name, value):
            if abs(value) < deadzone:
                return
            
            action_type = axes_config.get(axis_name, {}).get("type")
            if not action_type:
                action_type = profiles.get("Global", {}).get("axes", {}).get(axis_name, {}).get("type")
                
            if not action_type:
                return
                
            speed = global_mouse_speed
            scroll_speed = global_scroll_speed
            
            try:
                if action_type == "mouse_x":
                    dx = int(value * speed)
                    mouse.move(dx, 0)
                elif action_type == "mouse_y":
                    dy = int(value * speed)
                    mouse.move(0, dy)
                elif action_type == "scroll_vertical":
                    mouse.scroll(0, -value * scroll_speed)
                elif action_type == "scroll_horizontal":
                    mouse.scroll(value * scroll_speed, 0)
            except Exception as e:
                print(f"Axis error: {e}")
                
        process_axis("LeftX", lx)
        process_axis("LeftY", ly)
        process_axis("RightX", rx)
        process_axis("RightY", ry)

    # --- TRIGGER PROCESSING (Rate limited) ---
    if current_time - last_trigger_time < 0.066:
        return
        
    action_taken = False
        
    def get_trigger_action(t_name):
        action = profile.get("triggers", {}).get(t_name)
        if not action:
            action = profiles.get("Global", {}).get("triggers", {}).get(t_name)
        return action
        
    # Xbox triggers are often axes 4 and 5 in Pygame CE on Windows
    lt_action = get_trigger_action("LT")
    if lt_action and joystick.get_numaxes() > 4:
        lt_val = joystick.get_axis(4) 
        # Range is usually -1 (released) to 1 (fully pressed)
        if lt_val > 0.0: 
            execute_action(lt_action, "down")
            action_taken = True
            
    rt_action = get_trigger_action("RT")
    if rt_action and joystick.get_numaxes() > 5:
        rt_val = joystick.get_axis(5)
        if rt_val > 0.0:
            execute_action(rt_action, "down")
            action_taken = True
            
    if action_taken:
        last_trigger_time = current_time

class ControllerThread(QThread):
    profile_changed = pyqtSignal(str)
    controllers_changed = pyqtSignal(list, int)
    show_hud_signal = pyqtSignal(list)
    hide_hud_signal = pyqtSignal()
    update_hud_signal = pyqtSignal(float)
    
    def __init__(self):
        super().__init__()
        self.running = True
        self.joysticks = {}
        self.active_joystick_id = None
        self.hat_state = {"Up": False, "Down": False, "Left": False, "Right": False}
        self.active_actions = {}
        self.hud_active = False
        self.current_hud_angle = None
        self.active_hud_name = "Default HUD"
        # Hold-to-execute state for HUD
        self._hud_selected_idx = -1
        self._hud_select_time = 0.0   # time when current slice was first selected
        self._hud_last_fire = 0.0     # time of last repeated fire
        self._hud_fired_initial = False

    def reload_config(self):
        load_config()

    def _fire_hud_action(self, idx):
        """Execute the HUD action at the given slice index."""
        current_hud_items = hud_dictionary.get(self.active_hud_name, hud_dictionary.get("Default HUD", []))
        if 0 <= idx < len(current_hud_items):
            hud_act = current_hud_items[idx].get("action")
            if hud_act:
                execute_action(hud_act, "down")
                time.sleep(0.05)
                execute_action(hud_act, "up")

    def set_active_controller(self, instance_id):
        if instance_id in self.joysticks:
            self.active_joystick_id = instance_id
            print(f"Manually switched active controller to ID {instance_id}")

    def emit_controllers(self):
        controller_list = [{"id": j.get_instance_id(), "name": j.get_name()} for j in self.joysticks.values()]
        self.controllers_changed.emit(controller_list, self.active_joystick_id if self.active_joystick_id is not None else -1)

    def run(self):
        load_config()
        
        pygame.init()
        pygame.joystick.init()
        
        for i in range(pygame.joystick.get_count()):
            try:
                joy = pygame.joystick.Joystick(i)
                joy.init()
                self.joysticks[joy.get_instance_id()] = joy
            except Exception as e:
                print("Init joystick error:", e)
                
        if self.joysticks:
            self.active_joystick_id = list(self.joysticks.keys())[0]
            print(f"Active controller: {self.joysticks[self.active_joystick_id].get_name()}")
            self.emit_controllers()
        
        # Start window monitor thread
        def win_loop():
            global active_profile_name
            while self.running:
                new_profile = get_active_window_profile()
                old_profile = active_profile_name
                
                if new_profile != active_profile_name:
                    if new_profile in profiles:
                        active_profile_name = new_profile
                    else:
                         if active_profile_name != "Default":
                             active_profile_name = "Default"
                             
                if active_profile_name != old_profile:
                    print(f"Switched to profile: {active_profile_name}")
                    if self.active_joystick_id is not None and self.active_joystick_id in self.joysticks:
                        if haptic_enabled:
                            try:
                                # Vibrate for 200ms at 50% strength
                                self.joysticks[self.active_joystick_id].rumble(0.5, 0.5, 200)
                            except Exception as e:
                                print(f"Rumble error: {e}")
                    self.profile_changed.emit(active_profile_name)
                    
                time.sleep(1.0)
                
        monitor_thread = threading.Thread(target=win_loop, daemon=True)
        monitor_thread.start()
        
        clock = pygame.time.Clock()
        
        try:
            while self.running:
                for event in pygame.event.get():
                    if event.type == pygame.JOYDEVICEADDED:
                        try:
                            joy = pygame.joystick.Joystick(event.device_index)
                            joy.init()
                            self.joysticks[joy.get_instance_id()] = joy
                            print(f"Controller connected: {joy.get_name()} (ID: {joy.get_instance_id()})")
                            if self.active_joystick_id is None:
                                self.active_joystick_id = joy.get_instance_id()
                            self.emit_controllers()
                        except Exception as e:
                            print(f"Error adding joystick: {e}")
                            
                    elif event.type == pygame.JOYDEVICEREMOVED:
                        if event.instance_id in self.joysticks:
                            joy = self.joysticks.pop(event.instance_id)
                            joy.quit()
                            print(f"Controller disconnected: ID {event.instance_id}")
                            if self.active_joystick_id == event.instance_id:
                                self.active_joystick_id = list(self.joysticks.keys())[0] if self.joysticks else None
                                if self.active_joystick_id:
                                    print(f"Switched to fallback controller: ID {self.active_joystick_id}")
                                else:
                                    print("No controllers left.")
                            self.emit_controllers()
                            
                    if hasattr(event, 'instance_id') and event.instance_id != self.active_joystick_id:
                        continue

                    profile = profiles.get(active_profile_name, {})
                    global_profile = profiles.get("Global", {})
                    
                    def get_action_for_btn(p, b_name, c_name):
                        cfg = p.get("buttons", {})
                        if c_name and c_name in cfg:
                            return cfg.get(c_name)
                        return cfg.get(b_name)
                    
                    def get_active_modifiers():
                        mods = []
                        if self.active_joystick_id not in self.joysticks: return mods
                        joy = self.joysticks[self.active_joystick_id]
                        if joy.get_button(4): mods.append("LB")
                        if joy.get_button(5): mods.append("RB")
                        if joy.get_numaxes() > 4 and joy.get_axis(4) > 0.0: mods.append("LT")
                        if joy.get_numaxes() > 5 and joy.get_axis(5) > 0.0: mods.append("RT")
                        return mods
                    
                    if event.type == pygame.JOYBUTTONDOWN:
                        btn_name = BUTTON_MAP.get(event.button, f"Btn{event.button}")
                        print(f"Pressed: {btn_name}")
                        
                        mods = [m for m in get_active_modifiers() if m != btn_name]
                        combo_name = f"{mods[0]}+{btn_name}" if mods else None
                        
                        action = get_action_for_btn(profile, btn_name, combo_name)
                        if not action:
                            action = get_action_for_btn(global_profile, btn_name, combo_name)
                        
                        if action:
                            if action.get("type") == "radial_menu":
                                self.hud_active = True
                                self.active_hud_name = action.get("key") or "Default HUD"
                                items_to_show = hud_dictionary.get(self.active_hud_name, hud_dictionary.get("Default HUD", []))
                                self.show_hud_signal.emit(items_to_show)
                            else:
                                self.active_actions[btn_name] = action
                                execute_action(action, "down")
                            
                    elif event.type == pygame.JOYBUTTONUP:
                        btn_name = BUTTON_MAP.get(event.button, f"Btn{event.button}")
                        print(f"Released: {btn_name}")
                        
                        action = self.active_actions.pop(btn_name, None)
                        if not action:
                            action = get_action_for_btn(profile, btn_name, None)
                        if not action:
                            action = get_action_for_btn(global_profile, btn_name, None)
                            
                        if action:
                            if action.get("type") == "radial_menu":
                                self.hud_active = False
                                self.hide_hud_signal.emit()
                                # Only fire on release if hold didn't already fire
                                if not self._hud_fired_initial and self.current_hud_angle is not None:
                                    self._fire_hud_action(self._hud_selected_idx)
                                # Reset hold state
                                self._hud_selected_idx = -1
                                self._hud_fired_initial = False
                            else:
                                execute_action(action, "up")
                        
                    elif event.type == pygame.JOYHATMOTION:
                        lx, ly = event.value
                        
                        new_state = {
                            "Up": ly == 1,
                            "Down": ly == -1,
                            "Left": lx == -1,
                            "Right": lx == 1
                        }
                        
                        for dir_name, is_pressed in new_state.items():
                            if is_pressed and not self.hat_state[dir_name]:
                                print(f"Pressed: {dir_name}")
                                mods = [m for m in get_active_modifiers() if m != dir_name]
                                combo_name = f"{mods[0]}+{dir_name}" if mods else None
                                
                                action = get_action_for_btn(profile, dir_name, combo_name)
                                if not action:
                                    action = get_action_for_btn(global_profile, dir_name, combo_name)
                                    
                                if action:
                                    self.active_actions[dir_name] = action
                                    if action.get("type") == "radial_menu":
                                        self.hud_active = True
                                        self.current_hud_angle = None
                                        self.active_hud_name = action.get("key") or "Default HUD"
                                        items_to_show = hud_dictionary.get(self.active_hud_name, hud_dictionary.get("Default HUD", []))
                                        self.show_hud_signal.emit(items_to_show)
                                    else:
                                        execute_action(action, "down")
                                        
                            elif not is_pressed and self.hat_state[dir_name]:
                                print(f"Released: {dir_name}")
                                action = self.active_actions.pop(dir_name, None)
                                if not action:
                                    action = get_action_for_btn(profile, dir_name, None)
                                if not action:
                                    action = get_action_for_btn(global_profile, dir_name, None)
                                    
                                if action:
                                    if action.get("type") == "radial_menu":
                                        self.hud_active = False
                                        self.hide_hud_signal.emit()
                                        # Only fire on release if hold didn't already fire
                                        if not self._hud_fired_initial and self.current_hud_angle is not None:
                                            self._fire_hud_action(self._hud_selected_idx)
                                        # Reset hold state
                                        self._hud_selected_idx = -1
                                        self._hud_fired_initial = False
                                    else:
                                        execute_action(action, "up")
                                        
                            self.hat_state[dir_name] = is_pressed
                profile = profiles.get(active_profile_name, {})
                
                if self.hud_active and self.active_joystick_id in self.joysticks:
                    joy = self.joysticks[self.active_joystick_id]
                    # Right Stick
                    rx = joy.get_axis(2) if joy.get_numaxes() > 2 else 0.0
                    ry = joy.get_axis(3) if joy.get_numaxes() > 3 else 0.0
                    now = time.time()

                    if math.hypot(rx, ry) > 0.3:  # Deadzone
                        angle_deg = (math.degrees(math.atan2(ry, rx)) + 360) % 360
                        shifted = (angle_deg + 22.5) % 360
                        new_idx = int(shifted // 45)

                        # Update visual selection
                        if self.current_hud_angle != angle_deg:
                            self.current_hud_angle = angle_deg
                            self.update_hud_signal.emit(angle_deg)

                        # Track slice selection timing
                        if new_idx != self._hud_selected_idx:
                            # Moved to a new slice — reset timers
                            self._hud_selected_idx = new_idx
                            self._hud_select_time = now
                            self._hud_last_fire = 0.0
                            self._hud_fired_initial = False
                        else:
                            # Still on the same slice — check hold timers
                            hold_duration = now - self._hud_select_time
                            
                            # Load hold settings for this slice
                            current_hud_items = hud_dictionary.get(self.active_hud_name, hud_dictionary.get("Default HUD", []))
                            hud_item = current_hud_items[new_idx] if 0 <= new_idx < len(current_hud_items) else {}
                            hold_execute = hud_item.get("hold_execute", False)
                            hold_delay = hud_item.get("hold_delay_s", 0.5)
                            hold_repeat = hud_item.get("hold_repeat", False)
                            repeat_interval = hud_item.get("hold_repeat_s", 0.2)
                            
                            if hold_execute:
                                if not self._hud_fired_initial and hold_duration >= hold_delay:
                                    # Initial fire after hold_delay
                                    self._fire_hud_action(new_idx)
                                    self._hud_fired_initial = True
                                    self._hud_last_fire = now
                                elif self._hud_fired_initial and hold_repeat and (now - self._hud_last_fire) >= repeat_interval:
                                    # Repeat fire every repeat_interval
                                    self._fire_hud_action(new_idx)
                                    self._hud_last_fire = now
                    else:
                        if self.current_hud_angle is not None:
                            self.current_hud_angle = None
                            self.update_hud_signal.emit(-1.0)
                        # Reset hold state when stick returns to center
                        self._hud_selected_idx = -1
                        self._hud_fired_initial = False
                else:
                    if self.active_joystick_id in self.joysticks:
                        process_continuous_input(self.joysticks[self.active_joystick_id], profile)
                
                clock.tick(60)
                
        except Exception as e:
            print(f"Controller thread error: {e}")
        finally:
            pygame.quit()

    def stop(self):
        self.running = False
        self.wait()

if __name__ == "__main__":
    # Test stub
    app = __import__('PyQt5.QtWidgets').QtWidgets.QApplication([])
    thread = ControllerThread()
    thread.start()
    app.exec_()

