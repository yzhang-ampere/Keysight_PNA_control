"""Shared defaults and measurement plans for the PNA applications."""

PNA_BASE_DIRECTORY = r"D:\PSIG_remote_share_folder\temp_autosave_data"
PC_BASE_DIRECTORY = r"Z:\temp_autosave_data"
VISA_ADDRESS = "TCPIP0::10.76.79.222::inst0::INSTR"
TIMEOUT_MS = 1_000_000
AVERAGING_FACTOR = 20

CHANNEL_CAL_STATUS_MAP = {
    1: "calToCable",
    2: "calToProbe",
    3: "calToCableDeembedProbe",
}


def _single_port_standards(name, ports=(1, 3)):
    return [
        {"ports": [port], "base_name": f"port{port}_{name}"}
        for port in ports
    ]


CAL_VERIFICATION_PLAN = [
    {
        "description": "Port 1 and 2 thru",
        "prompt": "Connect port 1 and 2 through adapters",
        "base_name": "port1_unknownThru_port2",
        "port_combinations": [{"ports": [1, 2], "base_name": "port1_unknownThru_port2"}],
        "subfolders": {1: "verify_probe_calibration", 2: "fixture"},
    },
    {
        "description": "Port 1 and 3 thru",
        "prompt": "Connect port 1 and 3 through adapters",
        "base_name": "port1_unknownThru_port3",
        "port_combinations": [{"ports": [1, 3], "base_name": "port1_unknownThru_port3"}],
        "subfolders": {1: "verify_probe_calibration", 2: "fixture"},
    },
    {
        "description": "Port 3 and 4 thru",
        "prompt": "Connect port 3 and 4 through adapters",
        "base_name": "port3_unknownThru_port4",
        "port_combinations": [{"ports": [3, 4], "base_name": "port3_unknownThru_port4"}],
        "subfolders": {1: "verify_probe_calibration", 2: "fixture"},
    },
]

for standard, prompt in (
    ("openAir", "Keep the probe in the air"),
    ("open", "Touch the OPEN standard on the calibration substrate"),
    ("short", "Touch the SHORT standard on the calibration substrate"),
    ("load", "Touch the LOAD standard on the calibration substrate"),
):
    CAL_VERIFICATION_PLAN.append({
        "description": f"Probe [1, 3] on {standard}",
        "prompt": prompt,
        "base_name": standard,
        "port_combinations": _single_port_standards(standard),
        "subfolders": {1: "verify_probe_calibration", 2: "fixture"},
    })


RAW_MEASUREMENT_PLAN = [
    {
        "description": "Measure 2xThru of DDR5_10_DQS_A_4 on PCB1",
        "prompt": "Connect the PCB1 N and P 2xThru paths to ports 1-2 and 3-4",
        "base_name": "2xThur_DDR5_10_DQS_A_4_pcb1",
        "port_combinations": [
            {"ports": [1, 2], "base_name": "2xThur_DDR5_10_DQS_A_4_pcb1_N"},
            {"ports": [3, 4], "base_name": "2xThur_DDR5_10_DQS_A_4_pcb1_P"},
        ],
        "subfolders": {1: "fixture", 2: "raw_measure", 3: "raw_measure"},
    },
    {
        "description": "Measure 2xThru of DDR5_10_DQS_A_4 on PCB2",
        "prompt": "Connect the PCB2 N and P 2xThru paths to ports 1-2 and 3-4",
        "base_name": "2xThur_DDR5_10_DQS_A_4_pcb2",
        "port_combinations": [
            {"ports": [1, 2], "base_name": "2xThur_DDR5_10_DQS_A_4_pcb2_N"},
            {"ports": [3, 4], "base_name": "2xThur_DDR5_10_DQS_A_4_pcb2_P"},
        ],
        "subfolders": {1: "fixture", 2: "raw_measure", 3: "raw_measure"},
    },
]
