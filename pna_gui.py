"""Tkinter entry point for editing and running PNA measurement plans."""

import json
import copy
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

import yaml

from pna_config import (
    AVERAGING_FACTOR,
    CAL_VERIFICATION_PLAN,
    CHANNEL_CAL_STATUS_MAP,
    CONFIGURATION,
    CONFIG_FILE,
    EXPORT_DIRECTORY,
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
        task_scroll = ttk.Scrollbar(self, orient="horizontal", command=self.task_list.xview)
        task_scroll.grid(row=8, column=0, sticky="ew", padx=(0, 8))
        self.task_list.configure(xscrollcommand=task_scroll.set)

        fields = ttk.Frame(self)
        fields.grid(row=0, column=1, columnspan=3, sticky="ew")
        self.description = tk.StringVar()
        self.prompt = tk.StringVar()
        self.base_name = tk.StringVar()
        self.finished = tk.BooleanVar(value=False)
        for row, (label, variable) in enumerate((
            ("Description", self.description),
            ("User prompt", self.prompt),
            ("Default base name", self.base_name),
        )):
            ttk.Label(fields, text=label).grid(row=row, column=0, sticky="w", pady=2)
            ttk.Entry(fields, textvariable=variable, width=75).grid(row=row, column=1, sticky="ew", pady=2)
        fields.columnconfigure(1, weight=1)
        ttk.Checkbutton(fields, text="Finished (skip this task)", variable=self.finished).grid(
            row=3, column=1, sticky="w", pady=2
        )

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
        ttk.Button(self, text="Load YAML...", command=self._load_yaml).grid(row=6, column=3, sticky="e", pady=10)
        ttk.Button(self, text="Save YAML...", command=self._save_yaml).grid(row=7, column=3, sticky="e")
        ttk.Button(self, text="Move up", command=lambda: self._move_task(-1)).grid(row=7, column=1, sticky="w")
        ttk.Button(self, text="Move down", command=lambda: self._move_task(1)).grid(row=7, column=2, sticky="w")

        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)
        self.columnconfigure(3, weight=1)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

    def _refresh_tasks(self):
        self.task_list.delete(0, "end")
        for task in self.plan:
            marker = "[finished] " if task.get("finished", False) else ""
            self.task_list.insert("end", marker + task.get("description", "Unnamed task"))

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
        self.finished.set(bool(task.get("finished", False)))
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
        task["finished"] = self.finished.get()
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
            "finished": False,
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

    def _move_task(self, direction):
        selection = self.task_list.curselection()
        if not selection:
            return
        index = selection[0]
        new_index = index + direction
        if not 0 <= new_index < len(self.plan):
            return
        self._collect_task(index)
        self.selected_index = None
        self.plan[index], self.plan[new_index] = self.plan[new_index], self.plan[index]
        self._refresh_tasks()
        self.task_list.selection_set(new_index)
        self._load_task(new_index)

    def _load_yaml(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Load measurement plan",
            filetypes=(("YAML files", "*.yml *.yaml"), ("All files", "*.*")),
        )
        if not path:
            return
        self._load_yaml_file(path)

    def _load_yaml_file(self, path):
        try:
            with open(path, "r", encoding="utf-8") as stream:
                plan = yaml.safe_load(stream)
            if not isinstance(plan, list):
                raise ValueError("The YAML root must be a list of tasks.")
            for index, task in enumerate(plan, start=1):
                if not isinstance(task, dict):
                    raise ValueError(f"Task {index} must be a mapping.")
                for required in ("description", "prompt", "port_combinations", "subfolders"):
                    if required not in task:
                        raise ValueError(f"Task {index} is missing '{required}'.")
                task["subfolders"] = {
                    int(channel): folder
                    for channel, folder in task["subfolders"].items()
                }
                for combination in task["port_combinations"]:
                    if (not isinstance(combination, dict)
                            or not combination.get("ports")
                            or not combination.get("base_name")):
                        raise ValueError(f"Task {index} contains an invalid port combination.")
                task["finished"] = bool(task.get("finished", False))
            self.plan = plan
            self.selected_index = None
            self._refresh_tasks()
            if self.plan:
                self.task_list.selection_set(0)
                self._load_task(0)
        except (OSError, TypeError, ValueError, yaml.YAMLError) as error:
            messagebox.showerror("Could not load YAML", str(error), parent=self)

    def _save_yaml(self):
        if self.selected_index is not None:
            self._collect_task(self.selected_index)
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save measurement plan",
            defaultextension=".yml",
            filetypes=(("YAML files", "*.yml *.yaml"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as stream:
                yaml.safe_dump(self.plan, stream, sort_keys=False)
            messagebox.showinfo("Plan saved", f"Saved measurement plan to:\n{path}", parent=self)
        except OSError as error:
            messagebox.showerror("Could not save YAML", str(error), parent=self)

    def get_plan(self):
        if self.selected_index is not None:
            self._collect_task(self.selected_index)
        for index, task in enumerate(self.plan, start=1):
            if not task["description"] or not task["prompt"] or not task["port_combinations"] or not task["subfolders"]:
                raise ValueError(f"Task {index} is incomplete.")
        return copy.deepcopy(self.plan)

    def update_task_status(self, index, state):
        if 0 <= index < len(self.plan) and state == "finished":
            self.plan[index]["finished"] = True
            self._refresh_tasks()
            if self.selected_index == index:
                self.finished.set(True)


def main():
    root = tk.Tk()
    root.title("Keysight PNA Measurement")
    root.geometry("1050x950")

    form = ttk.Frame(root, padding=10)
    form.pack(fill="x")
    values = {
        "PNA address": tk.StringVar(value=VISA_ADDRESS),
        "PNA data directory": tk.StringVar(value=PNA_BASE_DIRECTORY),
        "PC data directory": tk.StringVar(value=PC_BASE_DIRECTORY),
        "Export directory": tk.StringVar(value=EXPORT_DIRECTORY),
        "Timeout (ms)": tk.StringVar(value=str(TIMEOUT_MS)),
        "Averaging factor": tk.StringVar(value=str(AVERAGING_FACTOR)),
        "Channel calibration map": tk.StringVar(value=json.dumps(CHANNEL_CAL_STATUS_MAP)),
    }
    for row, (label, value) in enumerate(values.items()):
        ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
        ttk.Entry(form, textvariable=value, width=90).grid(row=row, column=1, sticky="ew", pady=3)
    form.columnconfigure(1, weight=1)

    def browse_export_directory():
        path = filedialog.askdirectory(parent=root, title="Select export directory")
        if path:
            values["Export directory"].set(path)

    export_row = list(values).index("Export directory")
    ttk.Button(form, text="Browse...", command=browse_export_directory).grid(
        row=export_row, column=2, padx=(5, 0)
    )

    config_buttons = ttk.Frame(form)
    config_buttons.grid(row=len(values), column=1, sticky="w", pady=(5, 0))

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True, padx=10, pady=(8, 0))
    calibration_editor = PlanEditor(notebook, "Calibration verification", CAL_VERIFICATION_PLAN)
    raw_editor = PlanEditor(notebook, "Raw measurement", RAW_MEASUREMENT_PLAN)
    notebook.add(calibration_editor, text="Calibration verification")
    notebook.add(raw_editor, text="Raw measurement")

    def apply_configuration(configuration):
        values["PNA address"].set(configuration["visa_address"])
        values["PNA data directory"].set(configuration["pna_base_directory"])
        values["PC data directory"].set(configuration["pc_base_directory"])
        values["Export directory"].set(configuration.get("export_directory", "exports"))
        values["Timeout (ms)"].set(str(configuration["timeout_ms"]))
        values["Averaging factor"].set(str(configuration["averaging_factor"]))
        values["Channel calibration map"].set(json.dumps({
            int(channel): status
            for channel, status in configuration["channel_cal_status_map"].items()
        }))

    def load_configuration_file():
        path = filedialog.askopenfilename(
            parent=root,
            title="Load PNA configuration",
            initialfile=CONFIG_FILE.name,
            filetypes=(("YAML files", "*.yml *.yaml"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as stream:
                configuration = yaml.safe_load(stream)
            required = ("visa_address", "pna_base_directory", "pc_base_directory",
                        "timeout_ms", "averaging_factor", "channel_cal_status_map")
            missing = [key for key in required if key not in configuration]
            if missing:
                raise ValueError(f"Configuration is missing: {', '.join(missing)}")
            apply_configuration(configuration)
            plan_files = configuration.get("plan_files", {})
            config_dir = Path(path).parent
            for plan_key, editor in (("calibration", calibration_editor), ("raw", raw_editor)):
                plan_file = plan_files.get(plan_key)
                if plan_file:
                    plan_path = Path(plan_file)
                    if not plan_path.is_absolute():
                        plan_path = config_dir / plan_path
                    editor._load_yaml_file(str(plan_path))
            status.set(f"Loaded configuration: {path}")
        except (OSError, TypeError, ValueError, yaml.YAMLError) as error:
            messagebox.showerror("Could not load configuration", str(error), parent=root)

    def save_configuration_file():
        path = filedialog.asksaveasfilename(
            parent=root,
            title="Save PNA configuration",
            initialfile=CONFIG_FILE.name,
            defaultextension=".yml",
            filetypes=(("YAML files", "*.yml *.yaml"), ("All files", "*.*")),
        )
        if not path:
            return
        try:
            configuration = copy.deepcopy(CONFIGURATION)
            configuration.update({
                "pna_base_directory": values["PNA data directory"].get(),
                "pc_base_directory": values["PC data directory"].get(),
                "export_directory": values["Export directory"].get(),
                "visa_address": values["PNA address"].get(),
                "timeout_ms": int(values["Timeout (ms)"].get()),
                "averaging_factor": int(values["Averaging factor"].get()),
                "channel_cal_status_map": {
                    int(channel): value
                    for channel, value in json.loads(values["Channel calibration map"].get()).items()
                },
            })
            with open(path, "w", encoding="utf-8") as stream:
                yaml.safe_dump(configuration, stream, sort_keys=False)
            messagebox.showinfo("Configuration saved", f"Saved configuration to:\n{path}", parent=root)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            messagebox.showerror("Could not save configuration", str(error), parent=root)

    def export_configuration_bundle():
        directory = values["Export directory"].get().strip()
        if not directory:
            messagebox.showerror("Invalid export directory", "Enter an export directory first.", parent=root)
            return
        try:
            calibration_plan = calibration_editor.get_plan()
            raw_plan = raw_editor.get_plan()
            export_dir = Path(directory)
            plans_dir = export_dir / "plans"
            plans_dir.mkdir(parents=True, exist_ok=True)

            configuration = copy.deepcopy(CONFIGURATION)
            configuration.update({
                "pna_base_directory": values["PNA data directory"].get(),
                "pc_base_directory": values["PC data directory"].get(),
                "export_directory": directory,
                "visa_address": values["PNA address"].get(),
                "timeout_ms": int(values["Timeout (ms)"].get()),
                "averaging_factor": int(values["Averaging factor"].get()),
                "channel_cal_status_map": {
                    int(channel): value
                    for channel, value in json.loads(values["Channel calibration map"].get()).items()
                },
                "plan_files": {
                    "calibration": "plans/calibration_plan.yml",
                    "raw": "plans/raw_measurement_plan.yml",
                },
            })
            with (export_dir / "config.yml").open("w", encoding="utf-8") as stream:
                yaml.safe_dump(configuration, stream, sort_keys=False)
            with (plans_dir / "calibration_plan.yml").open("w", encoding="utf-8") as stream:
                yaml.safe_dump(calibration_plan, stream, sort_keys=False)
            with (plans_dir / "raw_measurement_plan.yml").open("w", encoding="utf-8") as stream:
                yaml.safe_dump(raw_plan, stream, sort_keys=False)
            messagebox.showinfo(
                "Export complete",
                f"Exported configuration and plans to:\n{export_dir}",
                parent=root,
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            messagebox.showerror("Could not export configuration", str(error), parent=root)

    ttk.Button(config_buttons, text="Load config...", command=load_configuration_file).pack(side="left", padx=(0, 5))
    ttk.Button(config_buttons, text="Save config...", command=save_configuration_file).pack(side="left")
    ttk.Button(config_buttons, text="Export all...", command=export_configuration_bundle).pack(side="left", padx=5)

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
        dialog.geometry("650x240")
        dialog.resizable(True, True)
        dialog.minsize(420, 150)
        prompt_font = tkfont.Font(root=dialog, size=14)
        message_label = ttk.Label(dialog, text=message, font=prompt_font, wraplength=500, padding=20)
        message_label.pack(fill="both", expand=True)
        dialog.bind(
            "<Configure>",
            lambda event: (
                message_label.configure(wraplength=max(300, event.width - 40)),
                prompt_font.configure(size=max(11, min(24, event.width // 45))),
            ),
        )

        def finish(continue_measurement):
            nonlocal prompt_dialog
            result["continue"] = continue_measurement
            if dialog.winfo_exists():
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
                elif event_type == "task":
                    editor, index, state, description, task_total = payload
                    editor.update_task_status(index, state)
                    status.set(
                        f"{state.title()}: task {index + 1}/{task_total} - {description}"
                    )
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
            plans.append((calibration_editor, calibration_plan))
        if mode.get() in ("Raw measurement", "Both sequentially"):
            plans.append((raw_editor, raw_plan))

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
                for editor, plan in plans:
                    events.put(("status", "Running measurement plan..."))
                    controller.run_plan(
                        pna_data_directory,
                        pc_data_directory,
                        plan,
                        channel_map,
                        average_factor,
                        _wait_for_prompt,
                        cancel_event,
                        lambda index, state, description, total, editor=editor:
                            events.put(("task", editor, index, state, description, total)),
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
