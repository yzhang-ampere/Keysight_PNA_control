# Keysight PNA Measurement Tools

This project provides console and GUI applications for controlling a Keysight PNA, performing averaged sweeps, and saving Touchstone files for multiple port combinations.

## Files

- `pna_script.py` — console version.
- `pna_gui.py` — graphical version.
- `pna_controller.py` — shared PNA control class.
- `pna_config.py` — shared connection defaults and YAML loading.
- `config.yml` — session settings and plan-file locations.
- `plans/calibration_plan.yml` — calibration verification tasks.
- `plans/raw_measurement_plan.yml` — raw DUT measurement tasks.
- `pyvisa_test.py` — backward-compatible launcher.

## Installation

Use the Python environment on the workstation connected to the PNA:

```bash
python -m pip install -r requirements.txt
```

PyVISA also requires a VISA implementation/backend. Install the VISA backend appropriate for the workstation and Keysight installation, then verify that the PNA is reachable over the network.

## Configuration

Edit `config.yml` to define the session configuration:

- `pna_base_directory` — directory where the PNA saves data.
- `pc_base_directory` — local/shared directory used to create matching folders.
- `export_directory` — directory used by the GUI's **Export all...** action.
- `visa_address` — PNA VISA resource address.
- `timeout_ms` — VISA timeout.
- `averaging_factor` — number of sweeps per averaged measurement.
- `channel_cal_status_map` — channel-to-calibration status mapping.
- `plan_files` — paths to the calibration and raw plan YAML files.

Measurement tasks are configured in the YAML files under `plans/`. Each task contains a prompt, output folders, and one or more port combinations:

```yaml
- description: Measure a differential pair
  prompt: Connect the DUT
  finished: false
  base_name: differential_pair
  port_combinations:
    - ports: [1, 2]
      base_name: differential_pair_N
    - ports: [3, 4]
      base_name: differential_pair_P
  subfolders:
    1: raw_measure
    2: raw_measure
```

All listed port combinations are saved after the same averaged sweep.

The GUI can load and save `config.yml` from arbitrary paths. Loading a configuration updates the connection/session fields and loads the plan files listed under `plan_files`. This makes the configuration and plan files suitable for recording the setup and progress of a lab session.

## Console execution

Run one plan:

```bash
python pna_script.py --plan raw
python pna_script.py --plan calibration
```

Run both plans sequentially:

```bash
python pna_script.py --plan both
```

The console program pauses before each task and waits for Enter after the requested physical connection has been made.

## GUI execution

Launch the GUI with:

```bash
python pna_gui.py
```

The compatibility launcher also supports:

```bash
python pyvisa_test.py --gui
```

The GUI provides:

- Calibration and raw measurement plan tabs.
- Editable task descriptions, prompts, output names, folders, and port combinations.
- A `Load YAML...` button for replacing a plan with another YAML file.
- `Load config...` and `Save config...` buttons for session settings.
- `Save YAML...` buttons for preserving edited plans and finished-task flags.
- `Export all...` for creating a self-contained configuration bundle in the configured `export_directory`, containing `config.yml` and both plan files.
- A finished-task checkbox for skipping or re-measuring a task.
- A progress log and task status display.
- Continue, Cancel, and Close controls during measurement.

Select the required run mode and click **Start**. The GUI action prompt is non-modal, so the main window remains available while the user is preparing the physical connection.

## Finished tasks

Set this field in YAML to skip a task on startup:

```yaml
finished: true
```

In the GUI, select the task and enable **Finished (skip this task)**. Tasks completed during the current run are marked finished in the GUI for that session. To persist the state for future launches, update the YAML flag to `true`.

## Important measurement behavior

For each active task, the program:

1. Prompts the user to connect or position the DUT.
2. Performs one averaged sweep.
3. Saves every configured port combination from that sweep.
4. Resets the PNA sweep state.

The PNA must already have the required channels, measurements, calibration, and sweep setup available before starting.

## Troubleshooting

- **`ModuleNotFoundError: pyvisa`**: install the dependencies with `python -m pip install -r requirements.txt`.
- **VISA connection error**: verify the VISA address, network connectivity, PNA remote-control settings, and VISA backend installation.
- **No active channels found**: configure and activate the required PNA channels before running.
- **No measurements to save**: verify that each active channel contains at least one measurement trace.
- **Unexpected task skipped**: check the task's `finished` field in the YAML file or its GUI checkbox.
