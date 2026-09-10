import re
import base64
import subprocess
from typing import Optional
from pycaw.pycaw import AudioUtilities

def get_current_volume() -> int:
    try:
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        devices = AudioUtilities.GetSpeakers()
        volume = devices.EndpointVolume
        return int(round(volume.GetMasterVolumeLevelScalar() * 100))
    except Exception as e:
        print(f"Error getting volume: {e}")
        return 0

def set_current_volume(percent: int) -> bool:
    try:
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        devices = AudioUtilities.GetSpeakers()
        volume = devices.EndpointVolume
        val = max(0.0, min(1.0, percent / 100.0))
        volume.SetMasterVolumeLevelScalar(val, None)
        return True
    except Exception as e:
        print(f"Error setting volume: {e}")
        return False

def set_mute(mute: bool) -> bool:
    try:
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        devices = AudioUtilities.GetSpeakers()
        volume = devices.EndpointVolume
        volume.SetMute(1 if mute else 0, None)
        return True
    except Exception as e:
        print(f"Error setting mute: {e}")
        return False

def get_current_brightness() -> int:
    try:
        cmd = 'powershell -Command "(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness).CurrentBrightness"'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        out = res.stdout.strip()
        if out:
            lines = [l.strip() for l in out.splitlines() if l.strip()]
            if lines:
                return int(lines[0])
        return -1
    except Exception as e:
        print(f"Error getting brightness: {e}")
        return -1

def set_current_brightness(percent: int) -> bool:
    try:
        percent = max(0, min(100, percent))
        cmd = f'powershell -Command "(Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods).WmiSetBrightness(0, {percent})"'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return res.returncode == 0
    except Exception as e:
        print(f"Error setting brightness: {e}")
        return False

def run_radio_ps_script(kind: str, state: str) -> str:
    ps_cmd = f"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | ? {{ $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' }})[0]
Function Await($WinRtTask, $ResultType) {{
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}}
[Windows.Devices.Radios.Radio,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
$r = $radios | Where-Object {{ $_.Kind -eq '{kind}' }}
if ($r) {{
    $status = Await ($r.SetStateAsync('{state}')) ([Windows.Devices.Radios.RadioAccessStatus])
    Write-Output $status
}} else {{
    Write-Output "NotFound"
}}
"""
    try:
        encoded_cmd = base64.b64encode(ps_cmd.encode('utf-16-le')).decode('utf-8')
        cmd = f"powershell -NoProfile -NonInteractive -EncodedCommand {encoded_cmd}"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return res.stdout.strip()
    except Exception as e:
        print(f"Error toggling radio: {e}")
        return "Error"

def toggle_dark_mode(enabled: bool) -> bool:
    val = 0 if enabled else 1
    try:
        cmd1 = f'reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize" /v AppsUseLightTheme /t REG_DWORD /d {val} /f'
        cmd2 = f'reg add "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize" /v SystemUsesLightTheme /t REG_DWORD /d {val} /f'
        res1 = subprocess.run(cmd1, shell=True, capture_output=True)
        res2 = subprocess.run(cmd2, shell=True, capture_output=True)
        return res1.returncode == 0 and res2.returncode == 0
    except Exception as e:
        print(f"Error toggling dark mode: {e}")
        return False

def get_current_theme() -> str:
    try:
        cmd = 'powershell -Command "(Get-ItemProperty -Path HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize).AppsUseLightTheme"'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        out = res.stdout.strip()
        if out == "0":
            return "dark"
        elif out == "1":
            return "light"
    except Exception:
        pass
    return "unknown"

def handle_device_command(msg_lower: str) -> Optional[str]:
    # 1. BLUETOOTH
    if re.search(r"\b(?:turn\s+)?(?:on|enable|activate)\s+bluetooth\b", msg_lower):
        status = run_radio_ps_script("Bluetooth", "On")
        if status == "Allowed":
            return "Bluetooth has been turned on."
        elif status == "DeniedBySystemPolicy":
            return "System policy prevents turning on Bluetooth."
        else:
            return "Failed to turn on Bluetooth. Please check if Bluetooth hardware is enabled."
            
    if re.search(r"\b(?:turn\s+)?(?:off|disable|deactivate)\s+bluetooth\b", msg_lower):
        status = run_radio_ps_script("Bluetooth", "Off")
        if status == "Allowed":
            return "Bluetooth has been turned off."
        else:
            return "Failed to turn off Bluetooth."

    # 2. WI-FI
    if re.search(r"\b(?:turn\s+)?(?:on|enable|activate)\s+wi-?fi\b", msg_lower):
        status = run_radio_ps_script("WiFi", "On")
        if status == "Allowed":
            return "Wi-Fi has been turned on."
        else:
            return "Failed to turn on Wi-Fi."
            
    if re.search(r"\b(?:turn\s+)?(?:off|disable|deactivate)\s+wi-?fi\b", msg_lower):
        status = run_radio_ps_script("WiFi", "Off")
        if status == "Allowed":
            return "Wi-Fi has been turned off. Note: I will be offline until Wi-Fi is turned back on."
        else:
            return "Failed to turn off Wi-Fi."

    # 3. MUTE / UNMUTE
    if re.search(r"\b(?:mute\s+volume|mute)\b", msg_lower):
        if set_mute(True):
            return "Volume muted."
        return "Failed to mute volume."
        
    if re.search(r"\b(?:unmute\s+volume|unmute)\b", msg_lower):
        if set_mute(False):
            return "Volume unmuted."
        return "Failed to unmute volume."

    # 4. VOLUME SETTINGS
    # Match: "increase volume by 50%" or "raise volume by 50%" or "volume up by 50%"
    vol_inc_match = re.search(
        r"\b(?:increase|raise|up|boost)\s+volume(?:\s+by)?\s+(\d+)\b|\bvolume\s+up(?:\s+by)?\s+(\d+)\b|\bvolume\s+(?:up|increase|raise)\s+by\s+(\d+)\b",
        msg_lower
    )
    if vol_inc_match:
        digits = next(g for g in vol_inc_match.groups() if g is not None)
        amt = int(digits)
        curr = get_current_volume()
        target = min(100, curr + amt)
        if set_current_volume(target):
            return f"Increased volume by {amt}%. Current volume is {target}%."
        return "Failed to increase volume."

    # Match: "decrease volume by 50%" or "lower volume by 50%" or "volume down by 50%"
    vol_dec_match = re.search(
        r"\b(?:decrease|lower|down|reduce)\s+volume(?:\s+by)?\s+(\d+)\b|\bvolume\s+down(?:\s+by)?\s+(\d+)\b|\bvolume\s+(?:down|decrease|lower|reduce)\s+by\s+(\d+)\b",
        msg_lower
    )
    if vol_dec_match:
        digits = next(g for g in vol_dec_match.groups() if g is not None)
        amt = int(digits)
        curr = get_current_volume()
        target = max(0, curr - amt)
        if set_current_volume(target):
            return f"Decreased volume by {amt}%. Current volume is {target}%."
        return "Failed to decrease volume."

    # Match: "set volume to 50%" or "volume to 50%" or "volume 50%" or "volume set to 50%"
    vol_set_match = re.search(
        r"\b(?:set|change|put)\s+volume(?:\s+to)?\s+(\d+)\b|\bvolume\s+(?:set\s+)?to\s+(\d+)\b|\bvolume\s+(?:set\s+)?(\d+)\b",
        msg_lower
    )
    if vol_set_match:
        digits = next(g for g in vol_set_match.groups() if g is not None)
        target = int(digits)
        if set_current_volume(target):
            return f"Volume set to {target}%."
        return "Failed to set volume."

    # Match simple relative volume changes without numbers
    if re.search(r"\b(?:increase|raise|up)\s+volume\b|\bvolume\s+up\b", msg_lower):
        curr = get_current_volume()
        target = min(100, curr + 10)
        if set_current_volume(target):
            return f"Increased volume to {target}%."
        return "Failed to increase volume."

    if re.search(r"\b(?:decrease|lower|down|reduce)\s+volume\b|\bvolume\s+down\b", msg_lower):
        curr = get_current_volume()
        target = max(0, curr - 10)
        if set_current_volume(target):
            return f"Decreased volume to {target}%."
        return "Failed to decrease volume."

    if re.search(r"\bvolume\s+(?:status|level|info|current)\b", msg_lower):
        curr = get_current_volume()
        return f"Current volume level is {curr}%."

    # 5. BRIGHTNESS SETTINGS
    # Match: "increase brightness by 50%" or "raise brightness by 50%" or "brightness up by 50%"
    br_inc_match = re.search(
        r"\b(?:increase|raise|up|boost)\s+brightness(?:\s+by)?\s+(\d+)\b|\bbrightness\s+up(?:\s+by)?\s+(\d+)\b|\bbrightness\s+(?:up|increase|raise)\s+by\s+(\d+)\b",
        msg_lower
    )
    if br_inc_match:
        digits = next(g for g in br_inc_match.groups() if g is not None)
        amt = int(digits)
        curr = get_current_brightness()
        if curr == -1:
            return "Brightness control is not supported on this device's display hardware."
        target = min(100, curr + amt)
        if set_current_brightness(target):
            return f"Increased brightness by {amt}%. Current brightness is {target}%."
        return "Failed to increase brightness."

    # Match: "decrease brightness by 50%" or "lower brightness by 50%" or "brightness down by 50%"
    br_dec_match = re.search(
        r"\b(?:decrease|lower|down|reduce)\s+brightness(?:\s+by)?\s+(\d+)\b|\bbrightness\s+down(?:\s+by)?\s+(\d+)\b|\bbrightness\s+(?:down|decrease|lower|reduce)\s+by\s+(\d+)\b",
        msg_lower
    )
    if br_dec_match:
        digits = next(g for g in br_dec_match.groups() if g is not None)
        amt = int(digits)
        curr = get_current_brightness()
        if curr == -1:
            return "Brightness control is not supported on this device's display hardware."
        target = max(0, curr - amt)
        if set_current_brightness(target):
            return f"Decreased brightness by {amt}%. Current brightness is {target}%."
        return "Failed to decrease brightness."

    # Match: "set brightness to 50%" or "brightness to 50%" or "brightness 50%" or "brightness set to 50%"
    br_set_match = re.search(
        r"\b(?:set|change|put)\s+brightness(?:\s+to)?\s+(\d+)\b|\bbrightness\s+(?:set\s+)?to\s+(\d+)\b|\bbrightness\s+(?:set\s+)?(\d+)\b",
        msg_lower
    )
    if br_set_match:
        digits = next(g for g in br_set_match.groups() if g is not None)
        target = int(digits)
        if get_current_brightness() == -1:
            return "Brightness control is not supported on this device's display hardware."
        if set_current_brightness(target):
            return f"Brightness set to {target}%."
        return "Failed to set brightness."

    # Match simple relative brightness changes without numbers
    if re.search(r"\b(?:increase|raise|up)\s+brightness\b|\bbrightness\s+up\b", msg_lower):
        curr = get_current_brightness()
        if curr == -1:
            return "Brightness control is not supported on this device's display hardware."
        target = min(100, curr + 10)
        if set_current_brightness(target):
            return f"Increased brightness to {target}%."
        return "Failed to increase brightness."

    if re.search(r"\b(?:decrease|lower|down|reduce)\s+brightness\b|\bbrightness\s+down\b", msg_lower):
        curr = get_current_brightness()
        if curr == -1:
            return "Brightness control is not supported on this device's display hardware."
        target = max(0, curr - 10)
        if set_current_brightness(target):
            return f"Decreased brightness to {target}%."
        return "Failed to decrease brightness."

    if re.search(r"\bbrightness\s+(?:status|level|info|current)\b", msg_lower):
        curr = get_current_brightness()
        if curr == -1:
            return "Brightness control is not supported on this device's display hardware."
        return f"Current brightness level is {curr}%."

    # 6. DARK / LIGHT THEME MODE
    if re.search(r"\b(?:turn\s+)?(?:on|enable|activate)\s+dark\s+mode\b|\b(?:set|change|switch)\s+(?:to\s+)?dark\s+mode\b", msg_lower):
        if toggle_dark_mode(True):
            return "Dark mode has been enabled."
        return "Failed to enable dark mode."

    if re.search(r"\b(?:turn\s+)?(?:on|enable|activate)\s+light\s+mode\b|\b(?:set|change|switch)\s+(?:to\s+)?light\s+mode\b", msg_lower):
        if toggle_dark_mode(False):
            return "Light mode has been enabled."
        return "Failed to enable light mode."

    if re.search(r"\b(?:toggle|switch)\s+(?:theme|mode|dark\s+mode|light\s+mode)\b", msg_lower):
        curr = get_current_theme()
        if curr == "dark":
            if toggle_dark_mode(False):
                return "Switched to Light mode."
        elif curr == "light":
            if toggle_dark_mode(True):
                return "Switched to Dark mode."
        if toggle_dark_mode(True):
            return "Toggled mode."
        return "Failed to toggle theme mode."

    return None
