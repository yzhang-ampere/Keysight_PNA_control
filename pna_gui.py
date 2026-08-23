"""Tkinter entry point for editing and running PNA measurement plans."""

import json
import threading
import tkinter as tk
from tkinter import messagebox, ttk

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


def _normalize_plan(widget):
    plan = json.loads(widget.get("1.0", "end"))
    if not isinstance(plan, list):
        raise ValueError("The plan must be a JSON list of tasks.")
    for task in plan:
        if not isinstance(task, dict):
            raise ValueError("Each task must be a JSON object.")
        if "port_combinations" not in task:
            raise ValueError("Each task must define port_combinations.")
        task["subfolders"] = {
            int(channel): folder
            for channel, folder in task["subfolders"].items()
        }
    return plan


def main():
    root = tk.Tk()
    root.title("Keysight PNA Measurement")
    root.geometry("1050x850")

    form = ttk.Frame(root, padding=10)
    form.pack(fill="x")
    values = {
        "PNA address": tk.StringVar(value=VISA_ADDRESS),
        "PNA data directory": tk.StringVar(value=PNA_BASE_DIRECTORY),
        "PC data directory": tk.StringVar(value=PC_BASE_DIRECTORY),
        "Timeout (ms)": tk.StringVar(value=str(TIMEOUT_MS)),
        "Averaging factor": tk.StringVar(value=str(AVERAGING_FACTOR)),
        "Channel calibration map": tk.StringVar(value=json.dumps(CHANNEL_CAL_STATUS_MAP)),
    }
    for row, (label, value) in enumerate(values.items()):
        ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(form, textvariable=value, width=90).grid(row=row, column=1, sticky="ew", pady=3)
    form.columnconfigure(1, weight=1)

    def add_plan_editor(title, plan):
        ttk.Label(root, text=title).pack(anchor="w", padx=10)
        editor = tk.Text(root, height=12, width=120, wrap="none")
        editor.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        editor.insert("1.0", json.dumps(plan, indent=2))
        return editor

    calibration_editor = add_plan_editor("Calibration verification plan (JSON)", CAL_VERIFICATION_PLAN)
    raw_editor = add_plan_editor("Raw measurement plan (JSON)", RAW_MEASUREMENT_PLAN)

    controls = ttk.Frame(root, padding=10)
    controls.pack(fill="x")
    ttk.Label(controls, text="Run:").pack(side="left")
    mode = tk.StringVar(value="Raw measurement")
    ttk.Combobox(
        controls, textvariable=mode, state="readonly", width=22,
        values=("Calibration verification", "Raw measurement", "Both sequentially"),
    ).pack(side="left", padx=8)
    status = tk.StringVar(value="Ready")
    ttk.Label(controls, textvariable=status).pack(side="left", padx=15)

    def prompt_callback(message, event):
        messagebox.showinfo("Measurement action required", message, parent=root)
        event.set()

    def start():
        try:
            channel_map = {
                int(channel): value
                for channel, value in json.loads(values["Channel calibration map"].get()).items()
            }
            calibration_plan = _normalize_plan(calibration_editor)
            raw_plan = _normalize_plan(raw_editor)
            timeout = int(values["Timeout (ms)"].get())
            average_factor = int(values["Averaging factor"].get())
            visa_address = values["PNA address"].get()
            pna_data_directory = values["PNA data directory"].get()
            pc_data_directory = values["PC data directory"].get()
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            messagebox.showerror("Invalid input", str(error), parent=root)
            return

        plans = []
        if mode.get() in ("Calibration verification", "Both sequentially"):
            plans.append(calibration_plan)
        if mode.get() in ("Raw measurement", "Both sequentially"):
            plans.append(raw_plan)

        start_button.config(state="disabled")

        def worker():
            controller = None
            try:
                root.after(0, status.set, "Connecting to PNA...")
                controller = PNAController.connect(visa_address, timeout)
                for plan in plans:
                    root.after(0, status.set, "Running measurement plan...")
                    controller.run_plan(
                        pna_data_directory,
                        pc_data_directory,
                        plan,
                        channel_map,
                        average_factor,
                        lambda message: _wait_for_prompt(root, message),
                    )
                root.after(0, status.set, "Completed successfully")
            except Exception as error:
                error_message = str(error)
                root.after(0, status.set, "Failed")
                root.after(0, lambda: messagebox.showerror(
                    "Measurement error", error_message, parent=root
                ))
            finally:
                if controller:
                    controller.close()
                root.after(0, start_button.config, {"state": "normal"})

    def _wait_for_prompt(window, message):
        event = threading.Event()
        window.after(0, prompt_callback, message, event)
        event.wait()

    start_button = ttk.Button(controls, text="Start", command=start)
    start_button.pack(side="right")
    ttk.Button(controls, text="Quit", command=root.destroy).pack(side="right", padx=8)
    root.mainloop()


if __name__ == "__main__":
    main()
