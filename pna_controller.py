"""Object-oriented Keysight PNA control and measurement execution."""

import os
import time


class PNAController:
    def __init__(self, resource, timeout_ms=1_000_000):
        self.resource = resource
        self.resource.timeout = timeout_ms

    @classmethod
    def connect(cls, visa_address, timeout_ms=1_000_000):
        import pyvisa
        resource = pyvisa.ResourceManager().open_resource(visa_address)
        controller = cls(resource, timeout_ms)
        print(f"Connected to: {controller.identification()}")
        return controller

    def close(self):
        if self.resource:
            self.resource.close()
            self.resource = None

    def identification(self):
        return self.resource.query("*IDN?").strip()

    def discover_active_channels(self):
        catalog = self.resource.query("SYST:CHAN:CAT?").strip().strip('"')
        if not catalog:
            raise RuntimeError("No active channels found on the PNA.")
        channels = [int(channel) for channel in catalog.split(",")]
        print(f"Discovered active channels: {channels}")
        return channels

    def setup_sweep_plan(self, channel, start_freq, stop_freq, num_points,
                         if_bandwidth, power_level, sweep_type="LIN"):
        self.resource.write(f"SENS{channel}:SWE:TYPE {sweep_type}")
        self.resource.write(f"SENS{channel}:FREQ:STAR {start_freq}")
        self.resource.write(f"SENS{channel}:FREQ:STOP {stop_freq}")
        self.resource.write(f"SENS{channel}:SWE:POIN {num_points}")
        self.resource.write(f"SENS{channel}:BWID {if_bandwidth}")
        self.resource.write(f"SOUR{channel}:POW {power_level}")

    def perform_averaged_sweep(self, channels, average_factor):
        for channel in channels:
            self.resource.write(f"SENS{channel}:AVER:COUN {average_factor}")
            self.resource.write(f"SENS{channel}:AVER:STAT ON")
            self.resource.write(f"SENS{channel}:AVER:CLE")
            self.resource.write(f"SENS{channel}:SWE:MODE HOLD")
            self.resource.write(f"SENS{channel}:SWE:GRO:COUN {average_factor}")
            self.resource.write(f"SENS{channel}:SWE:MODE GRO")
            print(f"Starting {average_factor} averaged sweeps on channel {channel}...")
        self.resource.query("*OPC?")
        print("Data acquisition complete.")

    def save_files_for_task(self, base_dir, task, active_channels, channel_cal_map):
        timestamp = time.strftime("%Y%m%d")
        combinations = []
        for combination in task["port_combinations"]:
            combinations.append((
                list(combination["ports"]),
                combination["base_name"],
            ))

        for channel in active_channels:
            if channel not in channel_cal_map:
                print(f"Warning: Channel {channel} has no calibration mapping; skipping.")
                continue
            catalog = self.resource.query(f"CALC{channel}:PAR:CAT?").strip().strip('"')
            if not catalog:
                print(f"Warning: Channel {channel} has no measurements; skipping.")
                continue
            measurement = catalog.split(",")[0]
            self.resource.write(f"CALC{channel}:PAR:SEL '{measurement}'")
            subfolder = task["subfolders"].get(channel)
            if not subfolder:
                print(f"Warning: No subfolder for channel {channel}; skipping.")
                continue

            data_folder = os.path.join(base_dir, subfolder)
            calibration_status = channel_cal_map[channel]
            for ports, base_name in combinations:
                port_list = ",".join(map(str, ports))
                filename = (
                    f"{base_name}_{calibration_status}_{timestamp}"
                    f".s{len(ports)}p"
                )
                path_on_pna = os.path.join(data_folder, filename)
                command = f"calculate{channel}:data:snp:ports:save '{port_list}', '{path_on_pna}'"
                print(f"Ch {channel}: saving ports {port_list} to '{path_on_pna}'")
                self.resource.write(command)
        self.resource.query("*OPC?")

    def reset_state(self, channels):
        for channel in channels:
            self.resource.write(f"SENS{channel}:AVER:STAT OFF")
            self.resource.write(f"SENS{channel}:SWE:MODE CONT")
        self.resource.query("*OPC?")

    def run_plan(self, pna_base_dir, pc_base_dir, plan, channel_cal_map,
                 average_factor, prompt_callback=None):
        channels = self.discover_active_channels()
        for task in plan:
            for subfolder in set(task["subfolders"].values()):
                os.makedirs(os.path.join(pc_base_dir, subfolder), exist_ok=True)
            prompt = f"{task['prompt']}. Press OK to continue..."
            if prompt_callback:
                prompt_callback(prompt)
            else:
                input(f"--> ACTION: {prompt}")
            self.perform_averaged_sweep(channels, average_factor)
            self.save_files_for_task(pna_base_dir, task, channels, channel_cal_map)
            self.reset_state(channels)
        return channels
