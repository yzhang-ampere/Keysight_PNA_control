"""Shared defaults and YAML-backed measurement plans."""

from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parent
PLANS_DIR = CONFIG_DIR / "plans"
CONFIG_FILE = CONFIG_DIR / "config.yml"


def load_configuration(path=CONFIG_FILE):
    with Path(path).open("r", encoding="utf-8") as stream:
        configuration = yaml.safe_load(stream)
    if not isinstance(configuration, dict):
        raise ValueError(f"Configuration file {path} must contain a YAML mapping.")
    return configuration


def load_plan(filename):
    """Load and minimally validate a measurement plan from YAML."""
    configured_path = Path(filename)
    path = configured_path if configured_path.is_absolute() else CONFIG_DIR / configured_path
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


CONFIGURATION = load_configuration()
PNA_BASE_DIRECTORY = CONFIGURATION["pna_base_directory"]
PC_BASE_DIRECTORY = CONFIGURATION["pc_base_directory"]
EXPORT_DIRECTORY = CONFIGURATION.get("export_directory", "exports")
VISA_ADDRESS = CONFIGURATION["visa_address"]
TIMEOUT_MS = int(CONFIGURATION["timeout_ms"])
AVERAGING_FACTOR = int(CONFIGURATION["averaging_factor"])
CHANNEL_CAL_STATUS_MAP = {
    int(channel): status
    for channel, status in CONFIGURATION["channel_cal_status_map"].items()
}

CALIBRATION_PLAN_FILE = CONFIGURATION["plan_files"]["calibration"]
RAW_PLAN_FILE = CONFIGURATION["plan_files"]["raw"]
CAL_VERIFICATION_PLAN = load_plan(CALIBRATION_PLAN_FILE)
RAW_MEASUREMENT_PLAN = load_plan(RAW_PLAN_FILE)
