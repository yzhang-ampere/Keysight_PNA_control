"""Console entry point for Keysight PNA measurements."""

import argparse

from pna_config import (
    AVERAGING_FACTOR,
    CAL_VERIFICATION_PLAN,
    CHANNEL_CAL_STATUS_MAP,
    PC_BASE_DIRECTORY,
    PNA_BASE_DIRECTORY,
    RAW_MEASUREMENT_PLAN,
    TIMEOUT_MS,
    VISA_ADDRESS,
)
from pna_controller import PNAController


def main():
    parser = argparse.ArgumentParser(description="Run Keysight PNA measurements.")
    parser.add_argument(
        "--plan", choices=("calibration", "raw", "both"), default="raw",
        help="Plan to run (default: raw).",
    )
    args = parser.parse_args()

    plans = []
    if args.plan in ("calibration", "both"):
        plans.append(("Calibration verification", CAL_VERIFICATION_PLAN))
    if args.plan in ("raw", "both"):
        plans.append(("Raw measurement", RAW_MEASUREMENT_PLAN))

    controller = None
    try:
        print("Connecting to PNA...")
        controller = PNAController.connect(VISA_ADDRESS, TIMEOUT_MS)
        for name, plan in plans:
            print(f"\nStarting {name} plan...")
            controller.run_plan(
                PNA_BASE_DIRECTORY,
                PC_BASE_DIRECTORY,
                plan,
                CHANNEL_CAL_STATUS_MAP,
                AVERAGING_FACTOR,
            )
    except Exception as error:
        print(f"\nMeasurement failed: {error}")
    finally:
        if controller:
            print("Closing connection.")
            controller.close()


if __name__ == "__main__":
    main()
