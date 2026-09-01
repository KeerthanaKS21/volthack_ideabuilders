# Fault Simulator Engine for GridLite

# Dictionary mapping machine_id -> Machine instance
_registered_machines = {}

def register_machines(machines):
    """
    Register the simulator's active machine instances to allow fault management.
    machines: list of Machine instances or dict mapping machine_id -> Machine
    """
    global _registered_machines
    if isinstance(machines, dict):
        _registered_machines = machines
    elif isinstance(machines, list):
        _registered_machines = {m.machine_id: m for m in machines}
    else:
        raise TypeError("machines must be a list or dictionary of Machine objects")

def inject_fault(machine_id, fault_type):
    """
    Inject a fault into a specific machine.
    Valid fault types: OVERLOAD, OVERHEATING, MECHANICAL_DEGRADATION, ELECTRICAL_ANOMALY
    """
    valid_faults = ["OVERLOAD", "OVERHEATING", "MECHANICAL_DEGRADATION", "ELECTRICAL_ANOMALY"]
    if fault_type not in valid_faults:
        raise ValueError(f"Invalid fault type: {fault_type}. Must be one of {valid_faults}")
        
    if machine_id not in _registered_machines:
        raise KeyError(f"Machine with ID '{machine_id}' is not registered.")
        
    machine = _registered_machines[machine_id]
    machine.inject_fault(fault_type)
    return f"Fault '{fault_type}' injected into machine '{machine_id}'."

def clear_fault(machine_id):
    """Clear any active fault on a machine."""
    if machine_id not in _registered_machines:
        raise KeyError(f"Machine with ID '{machine_id}' is not registered.")
        
    machine = _registered_machines[machine_id]
    machine.clear_fault()
    return f"Active faults cleared from machine '{machine_id}'."

def get_active_fault(machine_id):
    """Get the active fault type of a machine, or None if normal."""
    if machine_id not in _registered_machines:
        raise KeyError(f"Machine with ID '{machine_id}' is not registered.")
        
    return _registered_machines[machine_id].active_fault
