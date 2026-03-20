
import subprocess
import os

def check_hardware_stability():
    print("--- Sheppard Hardware Stability Watchdog ---")
    
    # 1. Check for Hardware Errors in Kernel Logs
    try:
        mce_check = subprocess.check_output("dmesg | grep -iE 'MCE|WHEA|Hardware Error'", shell=True).decode()
        if mce_check:
            print("[!] WARNING: Hardware/Memory errors detected in kernel logs!")
            print(mce_check)
        else:
            print("[✓] No critical hardware errors found in kernel logs.")
    except subprocess.CalledProcessError:
        print("[✓] No hardware errors detected.")

    # 2. Check Memory Bus Pressure
    try:
        with open("/proc/loadavg", "r") as f:
            load = f.read().strip()
            print(f"[*] System Load: {load}")
    except:
        pass

    # 3. Check Swappiness
    try:
        swappiness = subprocess.check_output("cat /proc/sys/vm/swappiness", shell=True).decode().strip()
        print(f"[*] Swappiness Level: {swappiness} (Ideal: 10)")
    except:
        pass

if __name__ == "__main__":
    check_hardware_stability()
