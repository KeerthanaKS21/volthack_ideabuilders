# GridLite Industrial Machine Simulator

This directory contains the **Phase 2** industrial machine simulator for GridLite. The simulator acts as a realistic data source, generating continuous, physically correlated telemetry streams for multiple virtual factory machines.

---

## Architecture Overview

The simulator is designed as a standalone, modular **data source**. It does not perform anomaly detection, database persistence, or AI analysis. 

```text
Machine Simulator (Phase 2)
        ↓  (Generates JSON telemetry streams)
GridLite Backend (Future Phases)
        ↓
Database / Storage
        ↓
AI / ML Anomaly Detection Engine
        ↓
React Dashboard
```

---

## Simulated Machines

Six virtual machines are simulated with unique physical profiles:

| Machine ID | Type | Location | Primary Operational Profile |
| :--- | :--- | :--- | :--- |
| **MOTOR-01** | Motor | Production Line A | ~2.0 kW, 35–50 °C, Vib: 0.08–0.20, PF: ~0.91 |
| **MOTOR-02** | Motor | Production Line A | ~2.0 kW, 35–50 °C, Vib: 0.08–0.20, PF: ~0.91 |
| **PUMP-01** | Pump | Production Line B | ~1.5 kW, 35–48 °C, Vib: 0.08–0.22, PF: ~0.89 |
| **PUMP-02** | Pump | Production Line B | ~1.5 kW, 35–48 °C, Vib: 0.08–0.22, PF: ~0.89 |
| **COMPRESSOR-01** | Compressor | Utility Area | ~3.0 kW, 40–60 °C, Vib: 0.10–0.25, PF: ~0.87 |
| **CONVEYOR-01** | Conveyor | Production Line A | ~1.3 kW, 30–45 °C, Vib: 0.05–0.18, PF: ~0.91 |

---

## Operating States

Each machine follows a realistic state-machine transition flow (unless manually overridden):

```text
  ┌──────┐     Startup (3s)     ┌─────────┐
  │ OFF  │ ───────────────────> │STARTING │
  └──────┘                      └─────────┘
     ▲                               │
     │ Idle / Shutdown               │ Operation
     │ (State Durations:             ▼
  ┌──────┐   Randomized Timers) ┌─────────┐
  │ IDLE │ <───────────────────>│ RUNNING │
  └──────┘                      └─────────┘
```

- **OFF:** Drawing 0 kW power, 0 A current, cooling down toward ambient room temperature.
- **STARTING:** Drawing ~2.2x nominal power (inrush current spike), high startup vibration.
- **IDLE:** Running warm but drawing minimal power (~15% nominal load), degraded power factor.
- **RUNNING:** Active production, operating within nominal design specification limits.

---

## Physics & Correlation Modeling

To keep data realistic, the generator avoids random independent numbers:
1. **Electrical Correlation:** Power, Voltage, Current, and Power Factor are mathematically bound:
   $$\text{Power (kW)} = \frac{\text{Voltage (V)} \times \text{Current (A)} \times \text{Power Factor}}{1000}$$
   $$\text{Current (A)} = \frac{\text{Power (kW)} \times 1000}{\text{Voltage (V)} \times \text{Power Factor}}$$
2. **Thermal Inertia:** Temperature shifts gradually over time using exponential smoothing rather than jumping instantly.
3. **Vibration Smoothing:** Mechanical oscillation ramps up or decays smoothly following state changes.

---

## Fault Simulation

Four future fault scenarios can be injected manually. Injections apply changes **gradually** (simulating degradation) rather than instantaneously:

1. **OVERLOAD:** Draw power and current rise linearly over time. Temperature climbs as a consequence.
2. **OVERHEATING:** Temperature rises to critical thresholds (e.g. 80–100 °C) without a proportional load increase.
3. **MECHANICAL_DEGRADATION:** Vibration rises dramatically (up to 4x nominal levels) due to friction. Power and temperature follow.
4. **ELECTRICAL_ANOMALY:** Unstable voltage fluctuations (spikes/dips), causing power factor degradation and current spikes.

---

## How to Run

Execute the simulator from the **GridLite root directory**:

```bash
python simulator/main.py
```

### Interactive CLI Commands
While running, you can enter commands in the terminal directly:
* `status` - Displays a live status table of all machines, states, and active faults.
* `inject <machine_id> <fault_type>` - Inject a fault (e.g., `inject MOTOR-01 OVERLOAD`).
* `clear <machine_id>` - Resolves active faults, letting parameters decay back to normal.
* `state <machine_id> <state>` - Override state manually (e.g., `state MOTOR-02 RUNNING`).
* `help` - Lists available commands.
* `exit` - Shuts down background loops and closes the program.

---

## Example JSON Record

Telemetry generated matches the standard schema:
```json
{
  "timestamp": "2026-08-29T18:20:01.124567",
  "machine_id": "MOTOR-01",
  "machine_type": "Motor",
  "location": "Production Line A",
  "voltage": 230.4,
  "current": 8.24,
  "power": 1.92,
  "temperature": 42.8,
  "vibration": 0.124,
  "power_factor": 0.93,
  "operating_state": "RUNNING"
}
```

---

## Verification Testing

Run the automated test suite verifying physical math, JSON structures, and fault transitions:
```bash
python simulator/tests.py
```
