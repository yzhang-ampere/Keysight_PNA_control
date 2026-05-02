import pyvisa
import time
import matplotlib.pyplot as plt
import numpy as np

class PNAController:
    # ... (All other methods remain the same) ...
    def __init__(self, visa_address):
        self.visa_address = visa_address; self.rm = pyvisa.ResourceManager(); self.instrument = None
        try:
            self.instrument = self.rm.open_resource(self.visa_address)
            self.instrument.timeout = 120000; self.instrument.write_termination = '\n'; self.instrument.read_termination = '\n' # Increased timeout for long averages
            print(f"Connected to: {self.identify()}"); self.reset_and_clear()
        except pyvisa.errors.VisaIOError as e: raise ConnectionError(f"Could not connect to {self.visa_address}: {e}")
    def __enter__(self): return self
    def __exit__(self, exc_type, exc_val, exc_tb): self.close()
    def identify(self): return self.instrument.query('*IDN?').strip()
    def check_errors(self):
        errors_found = []
        while True:
            error_string = self.instrument.query('SYST:ERR?').strip()
            if error_string.startswith('+0,'): break
            else: errors_found.append(error_string)
        if errors_found: print("\n--- PNA Errors ---\n" + "\n".join(errors_found) + "\n----------------\n")
        return errors_found
    def reset_and_clear(self): print("Resetting instrument..."); self.instrument.write('*RST;*CLS'); self.instrument.query('*OPC?'); self.check_errors(); print("Reset complete.")
    def setup_sweep_plan(self, start_hz, stop_hz, points, if_bw_hz, power_dbm, params=['S11', 'S21']):
        print("1. Setting up sweep plan..."); self.instrument.write(f'SENS1:FREQ:STAR {start_hz}'); self.instrument.write(f'SENS1:FREQ:STOP {stop_hz}'); self.instrument.write(f'SENS1:SWE:POIN {points}'); self.instrument.write(f'SENS1:BAND {if_bw_hz}'); self.instrument.write(f'SOUR1:POW {power_dbm}'); self.instrument.write('CALC1:PAR:DEL:ALL')
        for i, param in enumerate(params, 1):
            meas_name = f"My{param}"; print(f"  - Creating measurement: {param}"); self.instrument.write(f"CALC1:PAR:DEF '{meas_name}', '{param}'"); self.instrument.write(f"DISP:WIND1:TRAC{i}:FEED '{meas_name}'")
        self.check_errors(); print("Sweep plan setup complete.")
    def guided_solt_calibration(self):
        print("\n2. Starting Guided 2-Port SOLT Calibration..."); self.instrument.write("SENS1:CORR:COLL:METH:SOLT2 1,2")
        input("--> Connect OPEN to Port 1 & press Enter"); self.instrument.write("SENS1:CORR:COLL:OPEN 1"); self.instrument.query("*OPC?"); self.check_errors()
        input("--> Connect SHORT to Port 1 & press Enter"); self.instrument.write("SENS1:CORR:COLL:SHOR 1"); self.instrument.query("*OPC?"); self.check_errors()
        input("--> Connect LOAD to Port 1 & press Enter"); self.instrument.write("SENS1:CORR:COLL:LOAD 1"); self.instrument.query("*OPC?"); self.check_errors()
        input("\n--> Connect OPEN to Port 2 & press Enter"); self.instrument.write("SENS1:CORR:COLL:OPEN 2"); self.instrument.query("*OPC?"); self.check_errors()
        input("--> Connect SHORT to Port 2 & press Enter"); self.instrument.write("SENS1:CORR:COLL:SHOR 2"); self.instrument.query("*OPC?"); self.check_errors()
        input("--> Connect LOAD to Port 2 & press Enter"); self.instrument.write("SENS1:CORR:COLL:LOAD 2"); self.instrument.query("*OPC?"); self.check_errors()
        input("\n--> Connect Port 1 to Port 2 (THRU) & press Enter"); self.instrument.write("SENS1:CORR:COLL:THRU 1,2"); self.instrument.query("*OPC?"); self.check_errors()
        print("\nSaving and applying calibration..."); self.instrument.write("SENS1:CORR:COLL:SAVE"); self.instrument.query("*OPC?"); self.check_errors(); print("Calibration complete.")

    # === THE CORRECTED FUNCTION ===
    def perform_averaged_sweep(self, average_count=20):
        """
        Turns on averaging, triggers a single measurement cycle that completes
        all averages, and waits deterministically for completion.
        """
        print(f"\n3. Performing measurement with averaging ({average_count} sweeps)...")
        self.instrument.write("SENS1:AVER:STAT ON")
        self.instrument.write(f"SENS1:AVER:COUN {average_count}")
        self.instrument.write("INIT1:CONT OFF")
        self.instrument.write("SENS1:AVER:CLE")
        
        print("  - Waiting for averaging to complete. This may take some time...")
        # This single line triggers the entire averaging process and waits for it to finish.
        self.instrument.query("INIT1:IMM; *OPC?")
        
        self.check_errors()
        print("Averaged measurement complete.")
    
    def retrieve_all_formatted_data(self):
        print("4. Retrieving data from PNA..."); catalog_str = self.instrument.query("CALC1:PAR:CAT:EXT?").strip().replace('"', '')
        if not catalog_str: return None, None
        meas_names = catalog_str.split(','); frequencies = self._get_stimulus_axis()
        self.instrument.write('FORM:DATA ASC,0'); all_data = {}
        for name in meas_names:
            print(f"  - Fetching {name}..."); self.instrument.write(f"CALC1:PAR:SEL '{name}'")
            data_str = self.instrument.query("CALC1:DATA? FDATA"); all_data[name] = np.fromstring(data_str, sep=',')
        return frequencies, all_data
    def _get_stimulus_axis(self):
        self.instrument.write('FORM:DATA ASC,0'); freq_str = self.instrument.query("CALC1:X?"); return np.fromstring(freq_str, sep=',')
    def save_touchstone(self, n_ports, filename, directory):
        print(f"\nSaving results to Touchstone file: {filename}");
        if n_ports <= 0: raise ValueError("Number of ports must be positive.")
        clean_directory = directory.replace('/', '\\').rstrip('\\') + '\\'; pna_filepath = clean_directory + filename
        ports_str = ",".join(map(str, range(1, n_ports + 1))); self.instrument.write(f"CALC1:DATA:SNP:PORTs '{ports_str}'")
        print(f"  - Saving on PNA at path: {pna_filepath}"); self.instrument.write(f"MMEM:STOR:SNP '{pna_filepath}'"); self.instrument.query("*OPC?"); self.check_errors(); print("File saved successfully on the PNA.")
    def close(self):
        if self.instrument: self.instrument.close(); print("\nConnection closed.")

# --- Main Execution Block ---
if __name__ == '__main__':
    PNA_VISA_ADDRESS = 'TCPIP0::10.76.79.222::inst0::INSTR'
    SWEEP_PLAN = { 'start_hz': 20e6, 'stop_hz': 50e9, 'points': 2500, 'if_bw_hz': 1000, 'power_dbm': -5, 'params': ['S11', 'S21', 'S12', 'S22'] }
    AVERAGE_COUNT = 20; SAVE_DIRECTORY = "D:\\PSIG_remote_share_folder\\"; OUTPUT_FILENAME = "dut_50GHz_2500pts.s2p"
    try:
        with PNAController(PNA_VISA_ADDRESS) as pna:
            pna.setup_sweep_plan(**SWEEP_PLAN)
            # pna.guided_solt_calibration()
            pna.perform_averaged_sweep(average_count=AVERAGE_COUNT)
            frequencies, s_param_data = pna.retrieve_all_formatted_data()
            if frequencies is not None and s_param_data:
                print("5. Plotting results for review. Please close the plot window to continue.")
                fig, axs = plt.subplots(2, 2, figsize=(15, 10)); fig.suptitle('S-Parameter Measurement Results', fontsize=16)
                meas_names = list(s_param_data.keys())
                axs[0, 0].plot(frequencies / 1e9, s_param_data.get(meas_names[0], [])); axs[0, 0].set_title('S11'); axs[0, 0].set_ylabel('dB'); axs[0, 0].grid(True)
                axs[0, 1].plot(frequencies / 1e9, s_param_data.get(meas_names[1], [])); axs[0, 1].set_title('S21'); axs[0, 1].set_ylabel('dB'); axs[0, 1].grid(True)
                axs[1, 0].plot(frequencies / 1e9, s_param_data.get(meas_names[2], [])); axs[1, 0].set_title('S12'); axs[1, 0].set_xlabel('GHz'); axs[1, 0].set_ylabel('dB'); axs[1, 0].grid(True)
                axs[1, 1].plot(frequencies / 1e9, s_param_data.get(meas_names[3], [])); axs[1, 1].set_title('S22'); axs[1, 1].set_xlabel('GHz'); axs[1, 1].set_ylabel('dB'); axs[1, 1].grid(True)
                plt.tight_layout(rect=[0, 0.03, 1, 0.95]); plt.show()
                choice = input("--> Do you want to save these results? (y/n): ").lower()
                if choice == 'y': pna.save_touchstone(n_ports=2, filename=OUTPUT_FILENAME, directory=SAVE_DIRECTORY)
                else: print("Save operation cancelled by user.")
            else: print("Could not retrieve data to plot.")
            print("\n--- Full Measurement Procedure Complete! ---")
    except ConnectionError as e: print(f"Connection Error: {e}")
    except pyvisa.errors.VisaIOError as e: print(f"VISA Communication Error: {e}")
    except Exception as e: print(f"An unexpected error occurred: {e}")