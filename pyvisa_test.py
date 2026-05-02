import pyvisa
import os
import time

def discover_active_channels(pyVNA):
    """Queries the PNA to find all currently active channels."""
    print("\n--- Discovering Active Channels ---")
    channel_list_str = pyVNA.query("SYST:CHAN:CAT?").strip().strip('"')
    if not channel_list_str:
        print("ERROR: No active channels found on the PNA. Exiting.")
        return []
    
    active_channels = [int(ch) for ch in channel_list_str.split(',')]
    print(f"Discovered Active Channels: {active_channels}")
    return active_channels

def setup_sweep_plan(pyVNA, channel, start_freq, stop_freq, num_points, if_bandwidth, power_level, sweep_type='LIN'):
    """ Configures the sweep parameters for a specific PNA channel. """
    print(f"\n--- Setting up sweep plan for Channel {channel} ---")
    pyVNA.write(f"SENS{channel}:SWE:TYPE {sweep_type}")
    pyVNA.write(f"SENS{channel}:FREQ:STAR {start_freq}")
    pyVNA.write(f"SENS{channel}:FREQ:STOP {stop_freq}")
    pyVNA.write(f"SENS{channel}:SWE:POIN {num_points}")
    pyVNA.write(f"SENS{channel}:BWID {if_bandwidth}")
    pyVNA.write(f"SOUR{channel}:POW {power_level}")
    print(f"Channel {channel} Sweep Plan Set: {start_freq}-{stop_freq}, {num_points}pts, IFBW {if_bandwidth}, {power_level}dBm")

def perform_averaged_sweep(pyVNA,CHANNEL_LIST,avg_factor):
    print(f"Connected to: {pyVNA.query('*IDN?')}")
    for CHANNEL in CHANNEL_LIST:
        # 2. Configure Averaging
        pyVNA.write(f"SENS{CHANNEL}:AVER:COUN {avg_factor}")  # Set average factor
        pyVNA.write(f"SENS{CHANNEL}:AVER:STAT ON")             # Turn averaging ON
        pyVNA.write(f"SENS{CHANNEL}:AVER:CLE")                 # Clear existing averages

        # 3. Setup Triggering for Averaging
        # Set trigger mode to 'Hold' to stop continuous sweeping
        pyVNA.write(f"SENS{CHANNEL}:SWE:MODE HOLD")
        pyVNA.write(f'SENS{CHANNEL}:AVER:CLE') # Clear previous average data

        # Set the number of sweeps to match the average factor
        pyVNA.write(f"SENS{CHANNEL}:SWE:GRO:COUN {avg_factor}")
        pyVNA.write(f"SENS{CHANNEL}:SWE:MODE GRO")

        # 4. Execute and Wait
        print(f"Starting {avg_factor} averaged sweeps on channel {CHANNEL}...")

    # Send 'Group' trigger and wait for completion using *OPC?
    # This keeps the script busy until all sweeps are done
    pyVNA.query('*OPC?')
    print("Data acquisition complete.")

def save_files_for_task(pyVNA, pna_base_dir, task, active_channels, channel_cal_map):
    """
    Saves SNP files for a specific measurement task, using the user's exact SCPI syntax.
    """
    print(f"--- Preparing to Save Files for: {task['description']} ---")
    timestamp = time.strftime("%Y%m%d")

    # This loop handles saving data for each active channel
    for ch in active_channels:
        if ch not in channel_cal_map:
            print(f"  - Warning: Channel {ch} not in CHANNEL_CAL_STATUS_MAP. Skipping.")
            continue

        # Determine the correct subfolder for the current channel
        subfolder = task['subfolders'].get(ch)
        if not subfolder:
            print(f"  - Warning: No subfolder defined for Channel {ch} in this task. Skipping.")
            continue

        pna_data_folder = os.path.join(pna_base_dir, subfolder)
        cal_status = channel_cal_map[ch]

        # LOGIC FOR CALIBRATION VERIFICATION (.s1p files)
        if task['type'] == 'cal_verification':
            for port in task['ports']:
                dut_name = f"port{port}_{task['base_name']}"
                filename = f"{dut_name}_{cal_status}_{timestamp}.s1p"
                full_path_on_pna = os.path.join(pna_data_folder, filename)
                
                # Using your exact syntax for a single port
                command = f"calculate{ch}:measure{ch}:data:snp:ports:save '{port}', '{full_path_on_pna}'"
                print(f"  - Ch {ch}: Saving Port {port} to '{full_path_on_pna}'")
                pyVNA.write(command)

        # LOGIC FOR RAW DUT MEASUREMENT (.sNp files)
        elif task['type'] == 'raw_measurement':
            ports_to_save = ','.join(map(str,task['ports']))
            snp_suffix = f'.s{len(ports_to_save)}p'
            dut_name = task['base_name']
            filename = f"{dut_name}_{cal_status}_{timestamp}{snp_suffix}"
            full_path_on_pna = os.path.join(pna_data_folder, filename)

            # Using your exact syntax for multiple ports
            command = f"calculate{ch}:measure{ch}:data:snp:ports:save '{ports_to_save}', '{full_path_on_pna}'"
            print(f"  - Ch {ch}: Saving Ports {ports_to_save} to '{full_path_on_pna}'")
            pyVNA.write(command)

    # Wait for all save operations to complete
    pyVNA.query('*OPC?')
    print("--- Save operations complete. ---")

# --- Main Orchestration Function ---

def run_measurement_plan(pyVNA, pna_base_dir, pc_base_dir, plan, channel_cal_map, avg_factor):
    """
    Executes a list of measurement tasks, prompting the user between each step.
    """
    active_channels = discover_active_channels(pyVNA)
    if not active_channels:
        return

    for i, task in enumerate(plan):
        print("\n" + "="*50)
        print(f"STEP {i+1}/{len(plan)}: {task['description']}")
        print("="*50)

        # Create local directories for all potential subfolders in the task
        for subfolder in set(task['subfolders'].values()):
            pc_data_folder = os.path.join(pc_base_dir, subfolder)
            os.makedirs(pc_data_folder, exist_ok=True)
        
        # --- User Interaction ---
        input(f"--> ACTION: {task['prompt']}. Press Enter to continue...")

        # --- Measurement ---
        perform_averaged_sweep(pyVNA, active_channels, avg_factor)
        
        # --- Data Saving ---
        save_files_for_task(pyVNA, pna_base_dir, task, active_channels, channel_cal_map)

    print("\n" + "="*50)
    print("Measurement plan completed successfully!")
    print("="*50)


# --- Configuration and Execution ---

if __name__ == "__main__":
    # --- IMPORTANT ---
    # Make sure the sweep plan and calibrations are set up on the PNA before running.
    
    # --- 1. DEFINE BASE DIRECTORIES ---
    PNA_BASE_DIRECTORY = 'D:\\PSIG_remote_share_folder\\temp_autosave_data'
    PC_BASE_DIRECTORY = 'Z:\\temp_autosave_data'

    # --- 2. DEFINE CHANNEL-TO-CALIBRATION MAPPING ---
    CHANNEL_CAL_STATUS_MAP = {
        1: 'calToProbe',
        2: 'calToCable',
        3: 'calToCableDeembedProbe',
    }
    
    # --- 3. DEFINE AVERAGING PARAMETER ---
    AVERAGING_FACTOR = 20

    # --- 4. DEFINE THE MEASUREMENT PLANS ---
    cal_ports = [3]
    # PLAN A: For verifying probe calibration standards
    CAL_VERIFICATION_PLAN = [
        # {
        #     "description": "Probe in Air",
        #     "prompt": "Keep the probe in the air",
        #     "type": "cal_verification",
        #     "base_name": "openAir",
        #     "ports": cal_ports, # The ports to measure one by one
        #     "subfolders": {1: "verify_probe_calibration", 2: "fixture"}
        # },
        {
            "description": "Probe on Substrate OPEN",
            "prompt": "Touch the OPEN standard on the calibration substrate",
            "type": "cal_verification",
            "base_name": "open",
            "ports": cal_ports,
            "subfolders": {1: "verify_probe_calibration", 2: "fixture"}
        },
        # {
        #     "description": "Probe on Substrate SHORT",
        #     "prompt": "Touch the SHORT standard on the calibration substrate",
        #     "type": "cal_verification",
        #     "base_name": "short",
        #     "ports": cal_ports,
        #     "subfolders": {1: "verify_probe_calibration", 2: "fixture"}
        # },
        {
            "description": "Probe on Substrate LOAD",
            "prompt": "Touch the LOAD standard on the calibration substrate",
            "type": "cal_verification",
            "base_name": "load",
            "ports": cal_ports,
            "subfolders": {1: "verify_probe_calibration", 2: "fixture"}
        },
    ]
    
    # PLAN B: For measuring an actual N-port DUT
    RAW_MEASUREMENT_PLAN = [
        {
            "description": "Measure DDR7 Substrate",
            "prompt": "Place probes on the DDR7_CB_A_7_substrate DUT",
            "type": "raw_measurement",
            "base_name": "DDR7_CB_A_7_substrate",
            "ports": [1, 2, 3, 4], # The ports for the .sNp file
            "subfolders": {1: "raw_measure", 2: "raw_measure", 3: "raw_measure"}
        },
    ]

    # --- 5. CONNECT AND RUN THE SELECTED PLAN ---
    VISA_ADDRESS = "TCPIP0::10.76.79.222::inst0::INSTR"
    TIMEOUT_MS = 600000

    pyVNA = None
    try:
        print("Connecting to PNA...")
        pyVNA = pyvisa.ResourceManager().open_resource(VISA_ADDRESS)
        pyVNA.timeout = TIMEOUT_MS
        print(f"Connected to: {pyVNA.query('*IDN?').strip()}")
        
        # *** CHOOSE WHICH PLAN TO RUN HERE by uncommenting one line ***
        run_measurement_plan(pyVNA, PNA_BASE_DIRECTORY, PC_BASE_DIRECTORY, CAL_VERIFICATION_PLAN, CHANNEL_CAL_STATUS_MAP, AVERAGING_FACTOR)
        # run_measurement_plan(pyVNA, PNA_BASE_DIRECTORY, PC_BASE_DIRECTORY, RAW_MEASUREMENT_PLAN, CHANNEL_CAL_STATUS_MAP, AVERAGING_FACTOR)

    except pyvisa.errors.VisaIOError as e:
        print(f"\nVISA Error: {e}")
        print("Could not connect to the PNA. Check the address and network connection.")
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}")
    finally:
        if pyVNA:
            print("\nClosing connection.")
            pyVNA.close()