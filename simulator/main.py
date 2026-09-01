import sys
import os
import time
import threading
import datetime
import requests

# Add the parent directory of this script to the Python module search path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulator.config import MACHINES, SIMULATION_INTERVAL, SEND_TO_BACKEND, BACKEND_URL
from simulator.machines import Machine
from simulator.sensor_generator import generate_sensor_data
from simulator.fault_simulator import register_machines, inject_fault, clear_fault, get_active_fault

# Stop flag for the background simulation thread
stop_event = threading.Event()
# Mutex for thread-safe output printing
print_lock = threading.Lock()

# Registry of active Machine instances
machine_instances = {}

def run_simulation():
    """Background loop that steps machines, prints telemetry, and optionally POSTs to backend."""
    step_count = 0
    while not stop_event.is_set():
        start_time = time.time()
        step_count += 1
        
        # Autonomous rolling demonstration faults
        auto_schedule = [
            ("MOTOR-02", "MECHANICAL_DEGRADATION", 30, 60),
            ("COMPRESSOR-01", "OVERHEATING", 30, 75),
            ("PUMP-01", "ELECTRICAL_ANOMALY", 25, 80),
            ("MOTOR-01", "OVERLOAD", 25, 90),
        ]
        for m_id, f_type, dur, intv in auto_schedule:
            if m_id in machine_instances:
                mod = step_count % intv
                if mod == 5:
                    machine_instances[m_id].inject_fault(f_type)
                elif mod == 5 + dur:
                    machine_instances[m_id].clear_fault()
        
        # Capture current time prefix
        time_str = datetime.datetime.now().strftime("%H:%M:%S")
        
        readings = []
        for machine_id, machine in machine_instances.items():
            # Step the state machine
            machine.step()
            # Generate the reading
            reading = generate_sensor_data(machine)
            readings.append(reading)

        # Print all machine states in a formatted, lock-protected stdout block
        with print_lock:
            # Print timestamp header
            print(f"\n--- Telemetry Update [{time_str}] ---")
            for r in readings:
                active_f = get_active_fault(r['machine_id'])
                fault_tag = f" | Fault: {active_f}" if active_f else ""
                print(f"[{time_str}] {r['machine_id']} | {r['operating_state']}{fault_tag} | Power: {r['power']:.2f} kW | Temp: {r['temperature']:.1f} C | Vib: {r['vibration']:.3f} | PF: {r['power_factor']:.2f}")
            print("GridLite Sim> ", end="", flush=True)

        # Optionally POST data to the backend REST API
        if SEND_TO_BACKEND:
            for r in readings:
                try:
                    # POST telemetry to backend API (timeout of 2.5s for robust pipeline execution)
                    response = requests.post(BACKEND_URL, json=r, timeout=2.5)
                    if response.status_code != 201:
                        with print_lock:
                            print(f"\n[Warning] Backend rejected reading for {r['machine_id']}: HTTP {response.status_code}")
                            print("GridLite Sim> ", end="", flush=True)
                except requests.RequestException:
                    with print_lock:
                        print("\n[Warning] GridLite Backend offline. Continuing local simulation...")
                        print("GridLite Sim> ", end="", flush=True)
                    break # Stop trying other machines in this step if backend is offline

        # Compute sleep time to align precisely with interval
        elapsed = time.time() - start_time
        sleep_dur = max(0.1, SIMULATION_INTERVAL - elapsed)
        stop_event.wait(sleep_dur)

def print_help():
    print("""
======================================================================
GridLite Simulator - Interactive Console CLI
======================================================================
Available Commands:
  inject <machine_id> <fault_type> - Inject a fault into a machine
                                     Fault Types: OVERLOAD, OVERHEATING, 
                                     MECHANICAL_DEGRADATION, ELECTRICAL_ANOMALY
  clear <machine_id>               - Clear all active faults on a machine
  state <machine_id> <state>       - Override machine state (OFF, STARTING, IDLE, RUNNING)
  status                           - Print status of all machines
  help                             - Print this help message
  exit                             - Stop simulation and exit
======================================================================
""")

def main():
    print("Initializing GridLite Industrial Simulator...")
    
    # 1. Instantiate machines
    for m_cfg in MACHINES:
        m_id = m_cfg["machine_id"]
        machine_instances[m_id] = Machine(
            machine_id=m_id,
            machine_name=m_cfg["machine_name"],
            machine_type=m_cfg["machine_type"],
            location=m_cfg["location"]
        )
        
    # 2. Register machines in fault simulator registry
    register_machines(machine_instances)
    
    print(f"Loaded {len(machine_instances)} virtual machines.")
    print_help()
    
    # 3. Start background simulation loop thread
    sim_thread = threading.Thread(target=run_simulation, daemon=True)
    sim_thread.start()
    
    # 4. Interactive Command Input Loop
    try:
        while not stop_event.is_set():
            # Prompt the user for input
            cmd_line = input()
            cmd_line = cmd_line.strip()
            if not cmd_line:
                with print_lock:
                    print("GridLite Sim> ", end="", flush=True)
                continue
                
            parts = cmd_line.split()
            cmd = parts[0].lower()
            
            if cmd == "exit":
                print("Stopping simulator, please wait...")
                stop_event.set()
                break
                
            elif cmd == "help":
                with print_lock:
                    print_help()
                    
            elif cmd == "status":
                with print_lock:
                    print("\n--- Current Simulator Status ---")
                    print(f"{'Machine ID':<15} | {'State':<10} | {'Active Fault':<22} | {'Location':<20}")
                    print("-" * 75)
                    for m_id, machine in machine_instances.items():
                        fault = machine.active_fault or "None"
                        print(f"{m_id:<15} | {machine.operating_state:<10} | {fault:<22} | {machine.location:<20}")
                    print()
                    
            elif cmd in ["inject", "inject_fault"]:
                if len(parts) < 3:
                    with print_lock:
                        print("Error: Command format must be 'inject <machine_id> <fault_type>'")
                        print("Example: inject MOTOR-01 OVERLOAD")
                    continue
                
                m_id = parts[1].upper()
                fault = parts[2].upper()
                
                if m_id not in machine_instances:
                    with print_lock:
                        print(f"Error: Unknown machine ID: '{m_id}'")
                    continue
                    
                try:
                    res = inject_fault(m_id, fault)
                    with print_lock:
                        print(f"Success: {res}")
                except Exception as e:
                    with print_lock:
                        print(f"Error: {e}")
                        
            elif cmd in ["clear", "clear_fault"]:
                if len(parts) < 2:
                    with print_lock:
                        print("Error: Command format must be 'clear <machine_id>'")
                    continue
                    
                m_id = parts[1].upper()
                if m_id not in machine_instances:
                    with print_lock:
                        print(f"Error: Unknown machine ID: '{m_id}'")
                    continue
                    
                res = clear_fault(m_id)
                with print_lock:
                    print(f"Success: {res}")
                    
            elif cmd == "state":
                if len(parts) < 3:
                    with print_lock:
                        print("Error: Command format must be 'state <machine_id> <state>'")
                        print("Example: state MOTOR-01 RUNNING")
                    continue
                    
                m_id = parts[1].upper()
                state = parts[2].upper()
                
                if m_id not in machine_instances:
                    with print_lock:
                        print(f"Error: Unknown machine ID: '{m_id}'")
                    continue
                    
                try:
                    machine_instances[m_id].set_state(state, manual=True)
                    with print_lock:
                        print(f"Success: Set {m_id} state manually to {state}.")
                except Exception as e:
                    with print_lock:
                        print(f"Error: {e}")
            else:
                with print_lock:
                    print(f"Unknown command: '{cmd}'. Type 'help' to view commands.")
                    
    except KeyboardInterrupt:
        print("\nKeyboardInterrupt caught. Shutting down simulator...")
        stop_event.set()
        
    sim_thread.join(timeout=2.0)
    print("Simulator stopped. Goodbye!")

if __name__ == "__main__":
    main()
