"""Shared defaults and YAML-backed measurement plans."""

from pathlib import Path

import yaml

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

CONFIG_DIR = Path(__file__).resolve().parent
PLANS_DIR = CONFIG_DIR / "plans"


def load_plan(filename):
    """Load and minimally validate a measurement plan from YAML."""
    path = PLANS_DIR / filename
    with path.open("r", encoding="utf-8") as stream:
        plan = yaml.safe_load(stream)
    if not isinstance(plan, list):
        raise ValueError(f"Plan file {path} must contain a YAML list.")
    for index, task in enumerate(plan, start=1):
        if not isinstance(task, dict):
            raise ValueError(f"Task {index} in {path} must be a YAML mapping.")
        for required in ("description", "prompt", "port_combinations", "subfolders"):
            if required not in task:
                raise ValueError(f"Task {index} in {path} is missing '{required}'.")
        task["subfolders"] = {
            int(channel): folder for channel, folder in task["subfolders"].items()
        }
        task["finished"] = bool(task.get("finished", False))
    return plan


CAL_VERIFICATION_PLAN = load_plan("calibration_plan.yml")
RAW_MEASUREMENT_PLAN = load_plan("raw_measurement_plan.yml")
