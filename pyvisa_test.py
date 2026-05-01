import pyvisa
import os
import time

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

def sweep_and_save(pyVNA,data_folder,DUT_name,ports,channel_cal_status_map):
    # --- Dynamic Channel Discovery ---
    print("\n--- Discovering Active Channels ---")
    channel_list_str = pyVNA.query("SYST:CHAN:CAT?").rstrip().strip('"')
    if not channel_list_str:
        print("No active channels found on the PNA. Exiting.")
        
    # Convert the comma-separated string of channels to a list of integers
    active_channels = [int(ch) for ch in channel_list_str.split(',')]
    print(f"Discovered Active Channels: {active_channels}")

    # # --- Setup the Sweep Plan ---
    # for channel_to_setup in active_channels:
    #     setup_sweep_plan(
    #         pyVNA=pyVNA,
    #         channel=channel_to_setup,
    #         start_freq='20MHz',
    #         stop_freq='50GHz',
    #         num_points=2500,
    #         if_bandwidth='1kHz',
    #         power_level=-5.0
    #     )

    # measure with average sweeps
    perform_averaged_sweep(pyVNA,active_channels,20)

    # Save snp file from specified channel and measurement number
    # ch# specifies the channel of the data, <measurement#> specifies the number within the channel, for a 2-Port case, s2p includes all 4 S-Parameters, so selecting either measurement within the channel will work
    # SCPI: calculate<ch#>:measure<measurement#>:data:snp:ports:save '<select ports>', '<absolute path of file>'
    # Format the ports list into a string like '1,3'
    ports_str = ','.join(map(str, ports))
    timestamp = time.strftime("%Y%m%d") # Use current date for timestamp
    filename = DUT_name+'_'+timestamp
    snp_suffix = f'.s{len(ports)}p'
    for ch in active_channels:
        if ch in channel_cal_status_map:
            cal_status = channel_cal_status_map[ch]
            pyVNA.write(f"calculate{ch}:measure{ch}:data:snp:ports:save '{ports}', '{os.path.join(data_folder,filename+'_'+cal_status+snp_suffix)}'")


if __name__ == "__main__":
    directory_PNA =  os.path.abspath('D:\\PSIG_remote_share_folder\\temp_autosave_data')
    directory_PC = os.path.abspath('Z:\\temp_autosave_data')


    # DUT_name = 'DDR7_CB_A_7_substrate'
    # subfolder = 'raw_measure'
    # ports = [1,3]

    DUT_name = 'port1_calToCable'
    subfolder = 'fixture'
    ports = [1]
    # subfolder = 'verify_probe_calibration'

    channel_cal_status_map = {
        1: 'calToProbe',
        2: 'calToCable',
        3: 'calToCableDeembedProbe',
    }

    data_folder_PC = os.path.join(directory_PC,subfolder)
    if not os.path.exists(data_folder_PC):
        os.makedirs(data_folder_PC)
        print(f"Directory created: {data_folder_PC}")
    else:
        print(f"Directory already exists: {data_folder_PC}")

    data_folder_PNA = os.path.join(directory_PNA,subfolder)

    visaAddress = "TCPIP0::10.76.79.222::inst0::INSTR"
    pyVNA = pyvisa.ResourceManager().open_resource(visaAddress)
    # 300,000 milliseconds = 300 seconds = 5 minutes
    TIMEOUT_MS = 600000 
    pyVNA.timeout = TIMEOUT_MS
    print(pyVNA.query("*idn?").rstrip())
    sweep_and_save(pyVNA,data_folder_PNA,DUT_name,ports,channel_cal_status_map)