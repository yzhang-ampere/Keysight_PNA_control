"""Tkinter entry point for editing and running PNA measurement plans."""

import json
import queue
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
from pna_controller import MeasurementCancelled, PNAController


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

    ttk.Label(root, text="Progress log").pack(anchor="w", padx=10)
    log_text = tk.Text(root, height=8, width=120, state="disabled", wrap="word")
    log_text.pack(fill="both", expand=True, padx=10, pady=(0, 8))

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
    progress = ttk.Progressbar(controls, mode="indeterminate", length=180)
    progress.pack(side="left", padx=8)
    events = queue.Queue()
    cancel_event = threading.Event()
    running = False
    closing_requested = False
    prompt_dialog = None
    prompt_cancel = None

    def prompt_callback(message, event, result):
        nonlocal prompt_dialog, prompt_cancel
        dialog = tk.Toplevel(root)
        prompt_dialog = dialog
        dialog.title("Measurement action required")
        dialog.transient(root)
        dialog.grab_set()
        ttk.Label(dialog, text=message, wraplength=500, padding=20).pack()

        def finish(continue_measurement):
            nonlocal prompt_dialog
            result["continue"] = continue_measurement
            if dialog.winfo_exists():
                dialog.grab_release()
                dialog.destroy()
            prompt_dialog = None
            prompt_cancel = None
            event.set()

        buttons = ttk.Frame(dialog, padding=(10, 0, 10, 10))
        buttons.pack()
        ttk.Button(buttons, text="Continue", command=lambda: finish(True)).pack(side="left", padx=5)
        ttk.Button(buttons, text="Cancel", command=lambda: finish(False)).pack(side="left", padx=5)
        dialog.protocol("WM_DELETE_WINDOW", lambda: finish(False))
        prompt_cancel = lambda: finish(False)

    def poll_events():
        nonlocal running, prompt_dialog
        try:
            while True:
                event_type, *payload = events.get_nowait()
                if event_type == "status":
                    status.set(payload[0])
                elif event_type == "log":
                    log_text.config(state="normal")
                    log_text.insert("end", payload[0] + "\n")
                    log_text.see("end")
                    log_text.config(state="disabled")
                elif event_type == "prompt":
                    message, event, result = payload
                    prompt_callback(message, event, result)
                elif event_type == "error":
                    status.set("Failed")
                    messagebox.showerror("Measurement error", payload[0], parent=root)
                elif event_type == "cancelled":
                    status.set("Cancelled")
                elif event_type == "finished":
                    running = False
                    if payload[0]:
                        status.set("Completed successfully")
                    progress.stop()
                    start_button.config(state="normal")
                    if closing_requested:
                        root.destroy()
        except queue.Empty:
            pass
        root.after(100, poll_events)

    def start():
        nonlocal running
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
        cancel_event.clear()
        running = True
        progress.start(10)
        log_text.config(state="normal")
        log_text.delete("1.0", "end")
        log_text.config(state="disabled")

        def worker():
            controller = None
            succeeded = False
            try:
                events.put(("status", "Connecting to PNA..."))
                controller = PNAController.connect(
                    visa_address,
                    timeout,
                    logger=lambda message: events.put(("log", message)),
                )
                for plan in plans:
                    events.put(("status", "Running measurement plan..."))
                    controller.run_plan(
                        pna_data_directory,
                        pc_data_directory,
                        plan,
                        channel_map,
                        average_factor,
                        _wait_for_prompt,
                        cancel_event,
                    )
                succeeded = True
            except MeasurementCancelled as error:
                events.put(("log", str(error)))
                events.put(("cancelled",))
            except Exception as error:
                events.put(("log", f"ERROR: {error}"))
                events.put(("error", str(error)))
            finally:
                if controller:
                    controller.close()
                events.put(("finished", succeeded))

        threading.Thread(target=worker, daemon=True).start()

    def _wait_for_prompt(message):
        event = threading.Event()
        result = {"continue": False}
        events.put(("prompt", message, event, result))
        event.wait()
        return result["continue"]

    def close_window():
        nonlocal closing_requested
        if running:
            closing_requested = True
            cancel_event.set()
            if prompt_cancel:
                prompt_cancel()
            status.set("Cancelling...")
        else:
            root.destroy()

    def cancel_run():
        if running:
            cancel_event.set()
            if prompt_cancel:
                prompt_cancel()
            status.set("Cancelling...")

    start_button = ttk.Button(controls, text="Start", command=start)
    start_button.pack(side="right")
    ttk.Button(controls, text="Cancel", command=cancel_run).pack(side="right", padx=8)
    ttk.Button(controls, text="Close", command=close_window).pack(side="right", padx=8)
    root.protocol("WM_DELETE_WINDOW", close_window)
    root.after(100, poll_events)
    root.mainloop()


if __name__ == "__main__":
    main()
