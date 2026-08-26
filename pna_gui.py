"""Tkinter entry point for editing and running PNA measurement plans."""

import json
import copy
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


class PlanEditor(ttk.LabelFrame):
    """Human-readable editor for one YAML measurement plan."""

    def __init__(self, parent, title, plan):
        super().__init__(parent, text=title, padding=8)
        self.plan = copy.deepcopy(plan)
        self.selected_index = None
        self._build_widgets()
        self._refresh_tasks()
        if self.plan:
            self.task_list.selection_set(0)
            self._load_task(0)

    def _build_widgets(self):
        self.task_list = tk.Listbox(self, width=38, height=16, exportselection=False)
        self.task_list.grid(row=0, column=0, rowspan=8, sticky="nsew", padx=(0, 8))
        self.task_list.bind("<<ListboxSelect>>", self._task_selected)

        fields = ttk.Frame(self)
        fields.grid(row=0, column=1, columnspan=3, sticky="ew")
        self.description = tk.StringVar()
        self.prompt = tk.StringVar()
        self.base_name = tk.StringVar()
        for row, (label, variable) in enumerate((
            ("Description", self.description),
            ("User prompt", self.prompt),
            ("Default base name", self.base_name),
        )):
            ttk.Label(fields, text=label).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(fields, textvariable=variable, width=75).grid(row=row, column=1, sticky="ew", pady=2)
        fields.columnconfigure(1, weight=1)

        ttk.Label(self, text="Port combinations").grid(row=1, column=1, columnspan=3, sticky="w", pady=(10, 2))
        self.combinations = ttk.Treeview(self, columns=("ports", "base_name"), show="headings", height=5)
        self.combinations.heading("ports", text="Ports")
        self.combinations.heading("base_name", text="Output base name")
        self.combinations.column("ports", width=120)
        self.combinations.column("base_name", width=360)
        self.combinations.grid(row=2, column=1, columnspan=3, sticky="nsew")

        combo_fields = ttk.Frame(self)
        combo_fields.grid(row=3, column=1, columnspan=3, sticky="ew", pady=4)
        self.combo_ports = tk.StringVar()
        self.combo_base_name = tk.StringVar()
        ttk.Label(combo_fields, text="Ports").pack(side="left")
        ttk.Entry(combo_fields, textvariable=self.combo_ports, width=16).pack(side="left", padx=4)
        ttk.Label(combo_fields, text="Base name").pack(side="left")
        ttk.Entry(combo_fields, textvariable=self.combo_base_name, width=35).pack(side="left", padx=4)
        ttk.Button(combo_fields, text="Add / Update", command=self._add_combination).pack(side="left", padx=4)
        ttk.Button(combo_fields, text="Remove", command=self._remove_combination).pack(side="left")
        self.combinations.bind("<<TreeviewSelect>>", self._combination_selected)

        ttk.Label(self, text="Subfolders (channel=folder; channel=folder)").grid(row=4, column=1, columnspan=3, sticky="w", pady=(8, 2))
        self.subfolders = tk.StringVar()
        ttk.Entry(self, textvariable=self.subfolders, width=75).grid(row=5, column=1, columnspan=3, sticky="ew")
        ttk.Button(self, text="Add task", command=self._add_task).grid(row=6, column=1, sticky="w", pady=10)
        ttk.Button(self, text="Remove task", command=self._remove_task).grid(row=6, column=2, sticky="w", pady=10)

        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)
        self.columnconfigure(3, weight=1)
        self.rowconfigure(2, weight=1)

    def _refresh_tasks(self):
        self.task_list.delete(0, "end")
        for task in self.plan:
            self.task_list.insert("end", task.get("description", "Unnamed task"))

    def _task_selected(self, _event=None):
        selection = self.task_list.curselection()
        if not selection:
            return
        index = selection[0]
        if self.selected_index is not None:
            self._collect_task(self.selected_index)
        self._load_task(index)

    def _load_task(self, index):
        self.selected_index = index
        task = self.plan[index]
        self.description.set(task.get("description", ""))
        self.prompt.set(task.get("prompt", ""))
        self.base_name.set(task.get("base_name", ""))
        subfolders = task.get("subfolders", {})
        self.subfolders.set("; ".join(f"{channel}={folder}" for channel, folder in sorted(subfolders.items())))
        self.combinations.delete(*self.combinations.get_children())
        for combination in task.get("port_combinations", []):
            self.combinations.insert("", "end", values=(
                ", ".join(map(str, combination["ports"])), combination["base_name"]
            ))
        self.combo_ports.set("")
        self.combo_base_name.set("")

    def _collect_task(self, index):
        task = self.plan[index]
        task["description"] = self.description.get().strip()
        task["prompt"] = self.prompt.get().strip()
        task["base_name"] = self.base_name.get().strip()
        subfolders = {}
        for item in self.subfolders.get().split(";"):
            item = item.strip()
            if item:
                channel, folder = item.split("=", 1)
                subfolders[int(channel.strip())] = folder.strip()
        task["subfolders"] = subfolders
        task["port_combinations"] = [
            {"ports": [int(port.strip()) for port in self.combinations.item(item, "values")[0].split(",")],
             "base_name": self.combinations.item(item, "values")[1]}
            for item in self.combinations.get_children()
        ]

    def _add_combination(self):
        ports = self.combo_ports.get().strip()
        base_name = self.combo_base_name.get().strip()
        if not ports or not base_name:
            messagebox.showerror("Invalid combination", "Enter ports and an output base name.", parent=self)
            return
        try:
            normalized_ports = ", ".join(str(int(port.strip())) for port in ports.split(","))
        except ValueError:
            messagebox.showerror("Invalid ports", "Ports must be comma-separated integers.", parent=self)
            return
        selection = self.combinations.selection()
        if selection:
            self.combinations.item(selection[0], values=(normalized_ports, base_name))
        else:
            self.combinations.insert("", "end", values=(normalized_ports, base_name))
        self.combo_ports.set("")
        self.combo_base_name.set("")

    def _combination_selected(self, _event=None):
        selection = self.combinations.selection()
        if selection:
            ports, base_name = self.combinations.item(selection[0], "values")
            self.combo_ports.set(ports)
            self.combo_base_name.set(base_name)

    def _remove_combination(self):
        for item in self.combinations.selection():
            self.combinations.delete(item)
        self.combo_ports.set("")
        self.combo_base_name.set("")

    def _add_task(self):
        if self.selected_index is not None:
            self._collect_task(self.selected_index)
        self.plan.append({
            "description": "New measurement task",
            "prompt": "",
            "base_name": "new_measurement",
            "port_combinations": [],
            "subfolders": {},
        })
        self._refresh_tasks()
        index = len(self.plan) - 1
        self.task_list.selection_set(index)
        self._load_task(index)

    def _remove_task(self):
        selection = self.task_list.curselection()
        if not selection:
            return
        del self.plan[selection[0]]
        self.selected_index = None
        self._refresh_tasks()
        if self.plan:
            self.task_list.selection_set(0)
            self._load_task(0)

    def get_plan(self):
        if self.selected_index is not None:
            self._collect_task(self.selected_index)
        for index, task in enumerate(self.plan, start=1):
            if not task["description"] or not task["prompt"] or not task["port_combinations"] or not task["subfolders"]:
                raise ValueError(f"Task {index} is incomplete.")
        return copy.deepcopy(self.plan)


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

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=10, pady=(8, 0))
    calibration_editor = PlanEditor(notebook, "Calibration verification", CAL_VERIFICATION_PLAN)
    raw_editor = PlanEditor(notebook, "Raw measurement", RAW_MEASUREMENT_PLAN)
    notebook.add(calibration_editor, text="Calibration verification")
    notebook.add(raw_editor, text="Raw measurement")

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
            calibration_plan = calibration_editor.get_plan()
            raw_plan = raw_editor.get_plan()
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
