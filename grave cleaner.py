import os
import re
import sys
import time
import tempfile
import subprocess
import psutil
import tkinter as tk
from tkinter import filedialog, messagebox
import win32gui, win32con, win32process
import ctypes

# =========================
# Version
# =========================
VERSION = "1.0.0"

# =========================
# Auto-Update Check
# =========================
def check_for_update():
    try:
        # Replace with your raw GitHub URL of your script
        latest_url = "https://raw.githubusercontent.com/yourusername/yourrepo/main/grave_cleaner.py"
        with urllib.request.urlopen(latest_url) as response:
            latest_code = response.read().decode('utf-8')
        match = re.search(r'VERSION\s*=\s*["\']([^"\']+)["\']', latest_code)
        if match:
            latest_version = match.group(1)
            if latest_version != VERSION:
                if messagebox.askyesno("Update Available",
                                       f"A new version ({latest_version}) is available. Update now?"):
                    with open(sys.argv[0], 'w', encoding='utf-8') as f:
                        f.write(latest_code)
                    messagebox.showinfo("Updated", "The script has been updated. Please restart.")
                    os._exit(0)
    except Exception as e:
        print("Update check failed:", e)

# =========================
# Remaining code (your existing script)
# =========================

# --- Admin / UAC ---
try:
    import winreg
except Exception:
    winreg = None

GWL_EXSTYLE = -20
WS_EX_APPWINDOW = 0x00040000
WS_EX_TOOLWINDOW = 0x00000080
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020
WM_CLOSE = 0x0010

_SAVED_OBS_HWND = None
_HIDDEN_OBS_WINDOWS = set()
RUN_ELEVATED = False

def ensure_admin_on_start():
    global RUN_ELEVATED
    try:
        RUN_ELEVATED = bool(ctypes.windll.shell32.IsUserAnAdmin())
    except:
        RUN_ELEVATED = False
    if RUN_ELEVATED:
        return
    try:
        exe = sys.executable
        params = " ".join(f'"{a}"' for a in sys.argv)
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
        if int(ret) > 32:
            os._exit(0)
    except:
        pass

ensure_admin_on_start()

def find_obs_path():
    candidates = [
        r"C:\Program Files\obs-studio\bin\64bit\obs64.exe",
        r"C:\Program Files (x86)\obs-studio\bin\64bit\obs64.exe",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None

obs_path = find_obs_path()

def get_obs_root_dir_from_exe(exe_path):
    exe_dir = os.path.dirname(exe_path)
    return os.path.abspath(os.path.join(exe_dir, "..", ".."))

def is_portable_detected_for(exe_path):
    try:
        root = get_obs_root_dir_from_exe(exe_path)
        return os.path.isdir(os.path.join(root, "config", "obs-studio"))
    except:
        return False

def get_obs_config_path(exe_path, portable):
    if not exe_path:
        return os.path.join(os.environ.get("APPDATA", ""), "obs-studio", "global.ini")
    if portable:
        root = get_obs_root_dir_from_exe(exe_path)
        return os.path.join(root, "config", "obs-studio", "global.ini")
    else:
        return os.path.join(os.environ.get("APPDATA", ""), "obs-studio", "global.ini")

def _patch_ini_keys(config_path, kv):
    try:
        if not config_path:
            return
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        lines = []
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        found = {k: False for k in kv}
        out = []
        for line in lines:
            wrote = False
            for k, v in kv.items():
                if k in line:
                    out.append(f"{k}={'true' if v else 'false'}\n")
                    found[k] = True
                    wrote = True
                    break
            if not wrote:
                out.append(line)
        for k, v in kv.items():
            if not found[k]:
                out.append(f"{k}={'true' if v else 'false'}\n")
        with open(config_path, "w", encoding="utf-8", errors="ignore") as f:
            f.writelines(out)
    except:
        pass

def disable_obs_tray(config_path):
    _patch_ini_keys(config_path, {
        "MinimizeToTray": False,
        "EnableTray": False,
        "EnableSystemTray": False,
        "SysTray": False,
        "UseSystemTray": False,
    })

def enable_hide_obs_from_capture(config_path):
    _patch_ini_keys(config_path, {
        "HideOBSWindowsFromCapture": True,
    })

def is_obs_running():
    for proc in psutil.process_iter(["name"]):
        try:
            if (proc.info["name"] or "").lower() == "obs64.exe":
                return True
        except:
            pass
    return False

def get_obs_hwnd():
    global _SAVED_OBS_HWND
    if _SAVED_OBS_HWND and _is_window(_SAVED_OBS_HWND):
        return _SAVED_OBS_HWND
    target = None
    def enum_cb(hwnd, _):
        nonlocal target
        if win32gui.GetParent(hwnd):
            return True
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            name = (psutil.Process(pid).name() or "").lower()
        except:
            name = ""
        if name == "obs64.exe":
            title = (win32gui.GetWindowText(hwnd) or "").lower()
            if "obs" in title:
                target = hwnd
                return False
        return True
    win32gui.EnumWindows(enum_cb, None)
    if target:
        _SAVED_OBS_HWND = target
        return target
    return None

def get_all_obs_windows():
    main = get_obs_hwnd()
    all_hwnds = []

    def enum_cb(hwnd, _):
        if win32gui.GetParent(hwnd):
            return True
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            name = (psutil.Process(pid).name() or "").lower()
            if name == "obs64.exe":
                all_hwnds.append(hwnd)
        except:
            pass
        return True

    win32gui.EnumWindows(enum_cb, None)
    if main is None and all_hwnds:
        main = all_hwnds[0]
    return main, all_hwnds

def _apply_style(hwnd, add_flags=0, remove_flags=0):
    ex_style = win32gui.GetWindowLong(hwnd, GWL_EXSTYLE)
    ex_style = (ex_style | add_flags) & (~remove_flags)
    win32gui.SetWindowLong(hwnd, GWL_EXSTYLE, ex_style)
    win32gui.SetWindowPos(
        hwnd, None, 0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED
    )

def is_obs_projector_title(title):
    t = re.sub(r"\s+", " ", (title or "").lower()).strip()
    projector_keys = [
        "projector",
        "full screen projector",
        "fullscreen projector",
        "projector (preview)",
        "projector (program)",
        "game capture projector",
        "source projector",
    ]
    return any(k in t for k in projector_keys)

def _windows_for_pid(pid):
    hwnds = []
    def cb(hwnd, _):
        try:
            _, wpid = win32process.GetWindowThreadProcessId(hwnd)
            if wpid == pid and not win32gui.GetParent(hwnd):
                hwnds.append(hwnd)
        except:
            pass
        return True
    win32gui.EnumWindows(cb, None)
    return hwnds

def _collect_wipe_targets():
    targets = []
    for p in [r"C:\Program Files\obs-studio", r"C:\Program Files (x86)\obs-studio"]:
        if os.path.isdir(p):
            targets.append(p)
    if obs_path:
        try:
            root = get_obs_root_dir_from_exe(obs_path)
            if os.path.isdir(root) and os.path.basename(root).lower() == "obs-studio":
                targets.append(root)
        except:
            pass
    for p in [
        os.path.join(os.environ.get("APPDATA", ""), "obs-studio"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "obs-studio"),
        os.path.join(os.environ.get("PROGRAMDATA", ""), "obs-studio"),
    ]:
        if p and os.path.isdir(p):
            targets.append(p)
    for p in [r"C:\Program Files\Common Files\obs-plugins", r"C:\Program Files (x86)\Common Files\obs-plugins"]:
        if os.path.isdir(p):
            targets.append(p)
    try:
        self_path = os.path.abspath(sys.argv[0])
        if os.path.isfile(self_path):
            targets.append(self_path)
    except:
        pass
    seen = set()
    deduped = []
    for t in targets:
        if t and t not in seen:
            deduped.append(t)
            seen.add(t)
    return deduped

def _collect_prefetch_globs():
    patterns = []
    prefetch_dir = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Prefetch")
    patterns.append(os.path.join(prefetch_dir, "OBS*.PF"))
    patterns.append(os.path.join(prefetch_dir, "OBS64*.PF"))
    try:
        exe_base = os.path.basename(sys.executable)
        if exe_base:
            patterns.append(os.path.join(prefetch_dir, f"{exe_base.upper()}-*.PF"))
            base_no_ext = os.path.splitext(exe_base)[0]
            patterns.append(os.path.join(prefetch_dir, f"{base_no_ext.upper()}*.PF"))
    except:
        pass
    try:
        self_bin = os.path.basename(sys.argv[0])
        if self_bin.lower().endswith(".exe"):
            patterns.append(os.path.join(prefetch_dir, f"{self_bin.upper()}-*.PF"))
    except:
        pass
    seen = set()
    out = []
    for p in patterns:
        if p and p not in seen:
            out.append(p)
            seen.add(p)
    return out

def _build_wipe_batch(targets, glob_patterns):
    lines = [
        "@echo off",
        "setlocal enabledelayedexpansion",
        "title OBS Full Wipe",
        "timeout /t 1 /nobreak >nul",
        "taskkill /f /im obs64.exe >nul 2>&1",
    ]
    for path in targets:
        q = f"\"{path}\""
        if os.path.isdir(path):
            lines.append(f'if exist {q} rmdir /s /q {q} >nul 2>&1')
        else:
            lines.append(f'if exist {q} del /f /q {q} >nul 2>&1')
    for mask in glob_patterns:
        q = f"\"{mask}\""
        lines.append(f'for %%F in ({q}) do if exist "%%~fF" del /f /q "%%~fF" >nul 2>&1')
    lines.append('del /f /q "%~f0" >nul 2>&1')
    lines.append("exit /b 0")
    return "\r\n".join(lines)

def _launch_wipe_batch_and_exit(batch_text):
    tmpdir = tempfile.gettempdir()
    bat_path = os.path.join(tmpdir, f"obs_wipe_{int(time.time())}.bat")
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(batch_text)
    CREATE_NO_WINDOW = 0x08000000
    try:
        subprocess.Popen(["cmd.exe", "/c", bat_path], creationflags=CREATE_NO_WINDOW)
    except:
        subprocess.Popen(["cmd.exe", "/c", bat_path])
    try:
        root.destroy()
    except:
        pass
    os._exit(0)

def _wipe_registry():
    if not winreg:
        return
    to_delete = [
        (winreg.HKEY_CURRENT_USER, r"Software\OBS Studio"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\OBS Studio"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\OBS Studio"),
    ]
    def del_tree(hroot, subkey):
        try:
            key = winreg.OpenKey(hroot, subkey, 0, winreg.KEY_ALL_ACCESS)
        except FileNotFoundError:
            return
        try:
            while True:
                child = winreg.EnumKey(key, 0)
                del_tree(hroot, subkey + "\\" + child)
        except OSError:
            pass
        try:
            winreg.DeleteKey(hroot, subkey)
        except:
            pass
        try:
            winreg.CloseKey(key)
        except:
            pass
    for h, p in to_delete:
        try:
            del_tree(h, p)
        except:
            pass

# =========================
# Actions
# =========================
def launch_obs():
    global obs_path
    if not obs_path:
        status_label.config(text="Please browse for OBS first")
        return
    if is_obs_running():
        status_label.config(text="OBS already running")
        return
    try:
        exe_dir = os.path.dirname(obs_path)
        args = [obs_path]
        if portable_var.get():
            args.append("--portable")
        subprocess.Popen(args, shell=False, cwd=exe_dir)
        status_label.config(text=f"OBS launched ✅ ({'portable' if portable_var.get() else 'installed'})")
    except Exception as e:
        status_label.config(text=f"Launch error: {e}")

def hide_obs():
    main, hwnds = get_all_obs_windows()
    if not main:
        status_label.config(text="OBS window not found ❌")
        return
    cfg_path = get_obs_config_path(obs_path, portable_var.get())
    disable_obs_tray(cfg_path)
    enable_hide_obs_from_capture(cfg_path)
    _apply_style(main, add_flags=WS_EX_TOOLWINDOW, remove_flags=WS_EX_APPWINDOW)
    win32gui.ShowWindow(main, win32con.SW_SHOWNA)
    _HIDDEN_OBS_WINDOWS.clear()
    for hwnd in hwnds:
        if hwnd == main:
            continue
        try:
            title = win32gui.GetWindowText(hwnd) or ""
            if is_obs_projector_title(title):
                _apply_style(hwnd, add_flags=WS_EX_TOOLWINDOW, remove_flags=WS_EX_APPWINDOW)
                win32gui.ShowWindow(hwnd, win32con.SW_SHOWNA)
                continue
            if win32gui.IsWindowVisible(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
                _HIDDEN_OBS_WINDOWS.add(hwnd)
        except:
            pass
    status_label.config(text="OBS stealthed 👻 | Projectors stealthed | Aux windows hidden")

def show_obs():
    main, _ = get_all_obs_windows()
    if not main:
        status_label.config(text="OBS not running ❌")
        return
    _apply_style(main, add_flags=WS_EX_APPWINDOW, remove_flags=WS_EX_TOOLWINDOW)
    win32gui.ShowWindow(main, win32con.SW_RESTORE)
    try:
        win32gui.SetForegroundWindow(main)
    except:
        pass
    for hwnd in list(_HIDDEN_OBS_WINDOWS):
        try:
            if win32gui.IsWindow(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_SHOWNA)
        except:
            pass
    _HIDDEN_OBS_WINDOWS.clear()
    status_label.config(text="OBS restored ✅")

def kill_and_wipe():
    if not RUN_ELEVATED:
        if messagebox.askyesno("Administrator required",
                               "To fully wipe OBS (Program Files, Prefetch, registry), I need admin rights.\n"
                               "Relaunch with Administrator now?",
                               icon="warning"):
            ensure_admin_on_start()
            return
    warn = (
        "This will PERMANENTLY delete OBS, its configs/profiles/scenes, Prefetch traces, "
        "and remove this cleaner. Continue?"
    )
    if not messagebox.askyesno("Kill & Wipe", warn, icon="warning"):
        return
    # Close OBS gracefully
    for proc in list(psutil.process_iter(["name", "pid"])):
        try:
            if (proc.info["name"] or "").lower() == "obs64.exe":
                for hwnd in _windows_for_pid(proc.info["pid"]):
                    try:
                        win32gui.PostMessage(hwnd, WM_CLOSE, 0, 0)
                    except:
                        pass
        except:
            pass
    time.sleep(1.0)
    # Force kill
    for proc in list(psutil.process_iter(["name", "pid"])):
        try:
            if (proc.info["name"] or "").lower() == "obs64.exe":
                try:
                    psutil.Process(proc.info["pid"]).terminate()
                except:
                    pass
        except:
            pass
    time.sleep(1.0)
    for proc in list(psutil.process_iter(["name", "pid"])):
        try:
            if (proc.info["name"] or "").lower() == "obs64.exe":
                try:
                    psutil.Process(proc.info["pid"]).kill()
                except:
                    pass
        except:
            pass
    # Collect targets and prefetch masks
    targets = _collect_wipe_targets()
    prefetch_masks = _collect_prefetch_globs()
    # Registry cleanup
    _wipe_registry()
    # Build and run wipe batch
    batch_text = _build_wipe_batch(targets, prefetch_masks)
    _launch_wipe_batch_and_exit(batch_text)

def browse_exe():
    global obs_path
    file_path = filedialog.askopenfilename(
        filetypes=[("Executable Files", "*.exe")],
        title="Select obs64.exe"
    )
    if file_path:
        obs_path = file_path
        auto_portable = is_portable_detected_for(obs_path)
        portable_var.set(auto_portable)
        postfix = " (portable detected)" if auto_portable else ""
        status_label.config(text=f"OBS path set: {os.path.basename(file_path)}{postfix}")

# =========================
# GUI setup
# =========================

import urllib.request

root = tk.Tk()
root.title("GRAVE OBS CLEANER")
root.configure(bg="white")

# Large title label
title_label = tk.Label(root, text="GRAVE OBS CLEANER", font=("Arial", 24, "bold"), fg="#4B0082", bg="white")
title_label.pack(pady=10)

status_label = tk.Label(root, text="Checking for updates...", font=("Consolas", 12), fg="black", bg="white")
status_label.pack(pady=10)

# Check for updates at startup
check_for_update()

# Browse button
browse_btn = tk.Button(root, text="BROWSE FOR OBS EXECUTABLE", bg="#FFA500", fg="black", command=browse_exe)
browse_btn.pack(pady=5, fill="x")

# Portable mode toggle button
def toggle_portable():
    current = portable_var.get()
    portable_var.set(not current)
    btn_text = "Portable Mode: ON" if portable_var.get() else "Portable Mode: OFF"
    portable_btn.config(text=btn_text)
    mode_text = "Portable" if portable_var.get() else "Installed"
    status_label.config(text=f"Mode: {mode_text}")

portable_var = tk.BooleanVar(value=False)

portable_btn = tk.Button(
    root,
    text="Portable Mode: OFF",
    bg="#87CEFA",
    fg="black",
    command=toggle_portable,
    width=20,
    height=2
)
portable_btn.pack(pady=10)

# Launch button
launch_btn = tk.Button(root, text="Launch", bg="#6A0DAD", fg="white", command=launch_obs)
launch_btn.pack(pady=5, fill="x")

# Hide button
hide_btn = tk.Button(root, text="Hide", bg="#DC143C", fg="white", command=hide_obs)
hide_btn.pack(pady=5, fill="x")

# Show button
show_btn = tk.Button(root, text="Show", bg="#228B22", fg="white", command=show_obs)
show_btn.pack(pady=5, fill="x")

# Kill & Wipe button
kill_btn = tk.Button(root, text="Kill", bg="#800000", fg="white", command=kill_and_wipe)
kill_btn.pack(pady=5, fill="x")

# Initialize portable button text
if portable_var.get():
    portable_btn.config(text="Portable Mode: ON")
else:
    portable_btn.config(text="Portable Mode: OFF")

# Run the GUI main loop
root.mainloop()