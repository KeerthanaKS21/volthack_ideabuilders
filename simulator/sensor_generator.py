import datetime
import random
from simulator.config import PROFILES, STATE_FACTORS, AMBIENT_TEMP, NOISE_FACTOR

def generate_sensor_data(machine):
    """
    Generate realistic, physically correlated sensor readings for a machine 
    based on its operating state, active faults, and historical values.
    """
    profile = PROFILES[machine.machine_type]
    state = machine.operating_state
    factors = STATE_FACTORS[state]
    
    # 1. State-based baseline targets
    v_nom = profile["voltage"]["nominal"]
    p_nom = profile["power"]["nominal"]
    pf_nom = profile["power_factor"]["nominal"]
    t_nom = profile["temperature"]["nominal"]
    vib_nom = profile["vibration"]["nominal"]
    
    # Apply state multipliers to get baseline targets
    target_voltage = v_nom * factors["voltage_mult"]
    target_power = p_nom * factors["power_mult"]
    target_pf = pf_nom * factors["pf_mult"]
    
    # Get target temperature
    if "temp_target" in factors:
        target_temp = factors["temp_target"]
    else:
        target_temp = t_nom + factors["temp_target_offset"]
        
    # Get target vibration
    target_vib = vib_nom * factors["vib_mult"]
    
    # 2. Apply active faults (gradual ramp up over time)
    fault = machine.active_fault
    duration = machine.fault_duration
    
    # Base rates for gradual fault propagation
    if fault and state != "OFF":
        # Fault severity increases linearly to 100% over 20 steps
        severity = min(duration / 20.0, 1.0)
        
        if fault == "OVERLOAD":
            # Power increases up to 1.6x of nominal, temperature follows
            target_power *= (1.0 + severity * 0.6)
            target_temp += (severity * 25.0)
            target_vib *= (1.0 + severity * 0.3)
            
        elif fault == "OVERHEATING":
            # Temperature increases up to +40 degrees Celsius, others unchanged
            target_temp += (severity * 40.0)
            # Power increases slightly due to efficiency drop
            target_power *= (1.0 + severity * 0.05)
            
        elif fault == "MECHANICAL_DEGRADATION":
            # Vibration increases up to 4x of nominal, power/temp rise from friction
            target_vib *= (1.0 + severity * 3.0)
            target_power *= (1.0 + severity * 0.25)
            target_temp += (severity * 15.0)
            
        elif fault == "ELECTRICAL_ANOMALY":
            # Voltage fluctuates wildly, power factor degrades, current spikes
            # Create a fluctuating voltage coefficient (voltage dips and spikes)
            volts_fluctuation = 1.0 + (random.uniform(-0.15, 0.1) * severity)
            target_voltage *= volts_fluctuation
            target_pf = max(0.5, target_pf - (severity * 0.25))
            # Slightly higher vibration due to electrical noise
            target_vib *= (1.0 + severity * 0.4)

    # 3. Add statistical noise and compute state values
    # Generate Voltage (only if machine is not OFF)
    if state != "OFF":
        voltage = target_voltage + random.uniform(-1.5, 1.5)
        # Power factor calculation
        pf = target_pf + random.uniform(-0.015, 0.015)
        pf = max(0.4, min(pf, 0.99)) # keep within logical bounds
        # Power calculation
        power = target_power + random.uniform(-p_nom * NOISE_FACTOR, p_nom * NOISE_FACTOR)
        power = max(0.0, power)
    else:
        voltage = 0.0
        pf = 0.0
        power = 0.0

    # 4. Thermal physics (gradual temperature shift using exponential smoothing)
    # Slow heat dissipation / absorption rate
    alpha_temp = 0.06 if state != "OFF" else 0.03
    temp_noise = random.uniform(-0.15, 0.15) if state != "OFF" else random.uniform(-0.05, 0.05)
    temperature = machine.last_temperature + alpha_temp * (target_temp - machine.last_temperature) + temp_noise
    
    # Prevent dropping below ambient room temperature
    temperature = max(AMBIENT_TEMP - 0.5, temperature)
    machine.last_temperature = temperature # save to history

    # 5. Vibration physics (gradual vibration shift using exponential smoothing)
    alpha_vib = 0.35 if state == "STARTING" else 0.15
    vib_noise = random.uniform(-vib_nom * 0.04, vib_nom * 0.04) if state != "OFF" else 0.0
    vibration = machine.last_vibration + alpha_vib * (target_vib - machine.last_vibration) + vib_noise
    vibration = max(0.0, vibration)
    machine.last_vibration = vibration # save to history

    # 6. Electrical calculation correlation (Current = P / (V * PF))
    if state != "OFF" and voltage > 0 and pf > 0:
        # Convert power from kW to W: Power * 1000
        current = (power * 1000.0) / (voltage * pf)
        # Add slight current measurement noise
        current += random.uniform(-0.08, 0.08)
        current = max(0.0, current)
    else:
        current = 0.0

    # Create timestamp
    timestamp = datetime.datetime.now().isoformat()

    return {
        "timestamp": timestamp,
        "machine_id": machine.machine_id,
        "machine_type": machine.machine_type,
        "location": machine.location,
        "voltage": round(voltage, 1),
        "current": round(current, 2),
        "power": round(power, 2),
        "temperature": round(temperature, 1),
        "vibration": round(vibration, 3),
        "power_factor": round(pf, 2),
        "operating_state": state
    }
