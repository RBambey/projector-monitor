"""Tkinter dashboard — DSKY phosphor-green aesthetic matching joystick-midi."""

from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from config import AppConfig, ProjectorConfig
    from poller import TempReading, TemperaturePoller

# DSKY / AGC palette (identical to joystick-midi/main.py)
_C = {
    "bg":      "#111111",
    "bg_disp": "#0a1a0a",
    "fg":      "#39ff14",
    "fg_dim":  "#1a6600",
    "ind_on":  "#39ff14",
    "ind_off": "#0d2d0d",
    "btn_bg":  "#1a1a1a",
    "sel_bg":  "#1a5c0f",
    "border":  "#2a4a2a",
    "warn":    "#ff8c00",
    "alert":   "#ff2222",
}

_BAR_CHARS = " ▁▂▃▄▅▆▇█"
_LOG_LINES = 120  # how many lines to keep in the scrollable log panel


def _temp_color(temp: float, threshold: float) -> str:
    if temp >= threshold:
        return _C["alert"]
    if temp >= threshold * 0.85:
        return _C["warn"]
    return _C["fg"]


def _sparkline(readings: List["TempReading"], threshold: float, width: int = 60) -> str:
    """Return a `width`-char string built from block elements."""
    temps = [r.temp_celsius for r in readings if r.temp_celsius is not None]
    if not temps:
        return " " * width

    # take the last `width` samples
    temps = temps[-width:]
    max_val = max(threshold * 1.5, max(temps))
    chars = []
    for t in temps:
        idx = int(t / max_val * (len(_BAR_CHARS) - 1))
        idx = max(0, min(idx, len(_BAR_CHARS) - 1))
        chars.append(_BAR_CHARS[idx])
    # left-pad with spaces if fewer samples than width
    return " " * (width - len(chars)) + "".join(chars)


class _ProjectorPanel(tk.Frame):
    """One panel per projector — shows temp, status, and sparkline."""

    def __init__(self, parent: tk.Widget, proj: "ProjectorConfig",
                 cfg: "AppConfig") -> None:
        super().__init__(parent, bg=_C["bg"], bd=1, relief="flat",
                         highlightbackground=_C["border"], highlightthickness=1)
        self._proj = proj
        self._cfg = cfg
        self._build()

    def _build(self) -> None:
        # --- header row ---
        hdr = tk.Frame(self, bg=_C["bg"])
        hdr.pack(fill="x", padx=6, pady=(6, 0))

        self._ind = tk.Label(hdr, text="●", font=("Courier", 10),
                             fg=_C["fg_dim"], bg=_C["bg"])
        self._ind.pack(side="left")

        tk.Label(hdr, text=self._proj.label, font=("Courier", 10, "bold"),
                 fg=_C["fg"], bg=_C["bg"]).pack(side="left", padx=4)

        tk.Label(hdr, text=self._proj.ip, font=("Courier", 9),
                 fg=_C["fg_dim"], bg=_C["bg"]).pack(side="left")

        self._status = tk.Label(hdr, text="WAITING", font=("Courier", 9, "bold"),
                                fg=_C["fg_dim"], bg=_C["bg"])
        self._status.pack(side="right", padx=4)

        # --- large temperature display ---
        disp = tk.Frame(self, bg=_C["bg_disp"],
                        highlightbackground=_C["border"], highlightthickness=1)
        disp.pack(fill="x", padx=6, pady=4)

        self._temp_var = tk.StringVar(value="--.-°C")
        self._temp_lbl = tk.Label(disp, textvariable=self._temp_var,
                                  font=("Courier", 32, "bold"),
                                  fg=_C["fg_dim"], bg=_C["bg_disp"])
        self._temp_lbl.pack(side="left", padx=10, pady=6)

        self._sensors_var = tk.StringVar(value="")
        tk.Label(disp, textvariable=self._sensors_var,
                 font=("Courier", 9), fg=_C["fg_dim"], bg=_C["bg_disp"],
                 justify="left").pack(side="left", padx=4)

        self._ts_var = tk.StringVar(value="")
        tk.Label(disp, textvariable=self._ts_var,
                 font=("Courier", 8), fg=_C["fg_dim"], bg=_C["bg_disp"]
                 ).pack(side="right", padx=6)

        # --- sparkline ---
        spark_frame = tk.Frame(self, bg=_C["bg_disp"],
                               highlightbackground=_C["border"], highlightthickness=1)
        spark_frame.pack(fill="x", padx=6, pady=(0, 6))

        self._spark = tk.Text(spark_frame, height=1, font=("Courier", 9),
                              bg=_C["bg_disp"], fg=_C["fg"],
                              relief="flat", state="disabled",
                              cursor="arrow", takefocus=False,
                              wrap="none")
        self._spark.pack(fill="x", padx=4, pady=2)
        self._spark.tag_configure("alert", foreground=_C["alert"])

    def update(self, readings: List["TempReading"]) -> None:
        if not readings:
            return

        # Find the most recent successful reading across all sensors
        latest_temps = {}
        for r in reversed(readings):
            if r.temp_celsius is not None and r.sensor_index not in latest_temps:
                latest_temps[r.sensor_index] = r

        latest_error = None
        for r in reversed(readings):
            if r.error:
                latest_error = r
                break

        latest_ts = readings[-1].timestamp

        if latest_temps:
            max_sensor = max(latest_temps.values(), key=lambda r: r.temp_celsius)
            max_temp = max_sensor.temp_celsius
            color = _temp_color(max_temp, self._cfg.temp_threshold)
            self._temp_var.set(f"{max_temp:.1f}°C")
            self._temp_lbl.config(fg=color)
            self._ind.config(fg=color)

            if len(latest_temps) > 1:
                sensor_lines = "\n".join(
                    f"S{i}: {r.temp_celsius:.1f}°C"
                    for i, r in sorted(latest_temps.items())
                )
                self._sensors_var.set(sensor_lines)
            else:
                self._sensors_var.set("")

            self._status.config(text="ONLINE", fg=_C["fg"])
        elif latest_error:
            err = latest_error.error or "ERR"
            self._status.config(text=err, fg=_C["warn"])
            self._ind.config(fg=_C["warn"])
            self._temp_var.set("--.-°C")
            self._temp_lbl.config(fg=_C["fg_dim"])

        self._ts_var.set(latest_ts.strftime("%H:%M:%S"))

        # Sparkline — use max sensor value per timestamp bucket
        by_ts: Dict = {}
        for r in readings:
            if r.temp_celsius is not None:
                key = r.timestamp
                if key not in by_ts or r.temp_celsius > by_ts[key]:
                    by_ts[key] = r.temp_celsius

        spark_readings_proxy = [
            type("R", (), {"temp_celsius": v})()
            for v in by_ts.values()
        ]
        line = _sparkline(spark_readings_proxy, self._cfg.temp_threshold, width=60)

        self._spark.config(state="normal")
        self._spark.delete("1.0", "end")
        threshold = self._cfg.temp_threshold
        spark_temps = list(by_ts.values())[-60:]
        char_list = list(line.lstrip(" "))
        leading = len(line) - len(line.lstrip(" "))

        self._spark.insert("end", " " * leading)
        for i, ch in enumerate(char_list):
            idx = leading + len(line.lstrip()) - len(char_list) + i
            actual_temp = spark_temps[i] if i < len(spark_temps) else 0
            tag = "alert" if actual_temp >= threshold else ""
            self._spark.insert("end", ch, tag)
        self._spark.config(state="disabled")


class MonitorApp(tk.Tk):
    def __init__(self, cfg: "AppConfig", poller: "TemperaturePoller") -> None:
        super().__init__()
        self._cfg = cfg
        self._poller = poller
        self._panels: Dict[str, _ProjectorPanel] = {}
        self._log_lines: List[str] = []

        self.title("PROJECTOR MONITOR")
        self.configure(bg=_C["bg"])
        self.resizable(True, True)

        self._build()
        self._refresh()

    # ------------------------------------------------------------------

    def _build(self) -> None:
        # Header
        hdr = tk.Frame(self, bg=_C["bg"])
        hdr.pack(fill="x", padx=8, pady=(8, 4))
        tk.Label(hdr, text="PROJECTOR MONITOR",
                 font=("Courier", 14, "bold"), fg=_C["fg"], bg=_C["bg"]
                 ).pack(side="left")
        tk.Label(hdr,
                 text=f"threshold: {self._cfg.temp_threshold:.1f}°C  "
                      f"poll: {self._cfg.poll_interval}s",
                 font=("Courier", 9), fg=_C["fg_dim"], bg=_C["bg"]
                 ).pack(side="right")

        # Separator
        tk.Frame(self, bg=_C["border"], height=1).pack(fill="x", padx=8)

        # Projector panels (scrollable if many projectors)
        self._panels_frame = tk.Frame(self, bg=_C["bg"])
        self._panels_frame.pack(fill="x", padx=8, pady=4)

        for proj in self._cfg.projectors:
            if proj.enabled:
                self._add_panel(proj)

        # Separator
        tk.Frame(self, bg=_C["border"], height=1).pack(fill="x", padx=8)

        # Log panel
        log_frame = tk.Frame(self, bg=_C["bg"])
        log_frame.pack(fill="both", expand=True, padx=8, pady=(4, 0))

        tk.Label(log_frame, text="RECENT READINGS",
                 font=("Courier", 9, "bold"), fg=_C["fg_dim"], bg=_C["bg"]
                 ).pack(anchor="w")

        self._log_box = tk.Listbox(
            log_frame,
            font=("Courier", 9),
            bg=_C["bg_disp"], fg=_C["fg"],
            selectbackground=_C["sel_bg"],
            activestyle="none",
            relief="flat",
            highlightthickness=1,
            highlightbackground=_C["border"],
            height=8,
        )
        scrollbar = tk.Scrollbar(log_frame, orient="vertical",
                                  command=self._log_box.yview)
        self._log_box.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._log_box.pack(fill="both", expand=True)

        # Button strip
        btn_frame = tk.Frame(self, bg=_C["bg"])
        btn_frame.pack(fill="x", padx=8, pady=8)

        for label, cmd in [
            ("ADD PROJECTOR", self._on_add_projector),
            ("OPEN LOG DIR",  self._on_open_log_dir),
            ("CLEAR LOG",     self._on_clear_log),
        ]:
            tk.Button(
                btn_frame, text=label,
                font=("Courier", 9, "bold"),
                bg=_C["btn_bg"], fg=_C["fg"],
                activebackground=_C["sel_bg"], activeforeground=_C["fg"],
                relief="flat", bd=0, padx=10, pady=4,
                cursor="hand2", command=cmd,
            ).pack(side="left", padx=(0, 6))

    def _add_panel(self, proj: "ProjectorConfig") -> None:
        panel = _ProjectorPanel(self._panels_frame, proj, self._cfg)
        panel.pack(fill="x", pady=2)
        self._panels[proj.ip] = panel

    # ------------------------------------------------------------------

    def _refresh(self) -> None:
        for ip, panel in self._panels.items():
            readings = self._poller.get_buffer(ip)
            panel.update(readings)
            if readings:
                r = readings[-1]
                ts = r.timestamp.strftime("%H:%M:%S")
                if r.temp_celsius is not None:
                    line = (f"{ts}  {r.projector_label:<20}  "
                            f"S{r.sensor_index}: {r.temp_celsius:.1f}°C")
                else:
                    line = (f"{ts}  {r.projector_label:<20}  {r.error}")
                self._append_log(line)

        self.after(1000, self._refresh)

    def _append_log(self, line: str) -> None:
        self._log_lines.append(line)
        if len(self._log_lines) > _LOG_LINES:
            self._log_lines = self._log_lines[-_LOG_LINES:]
        self._log_box.insert("end", line)
        # trim listbox to keep it snappy
        while self._log_box.size() > _LOG_LINES:
            self._log_box.delete(0)
        self._log_box.see("end")

    # ------------------------------------------------------------------
    # Button handlers

    def _on_add_projector(self) -> None:
        dlg = _AddProjectorDialog(self)
        self.wait_window(dlg)
        if dlg.result is None:
            return
        proj = dlg.result
        self._cfg.projectors.append(proj)
        from config import save_config
        save_config(self._cfg)
        self._poller.add_projector(proj)
        self._add_panel(proj)

    def _on_open_log_dir(self) -> None:
        log_path = Path(__file__).parent / self._cfg.log_dir
        log_path.mkdir(parents=True, exist_ok=True)
        if sys.platform == "darwin":
            subprocess.Popen(["open", str(log_path)])
        elif sys.platform == "win32":
            subprocess.Popen(["explorer", str(log_path)])
        else:
            subprocess.Popen(["xdg-open", str(log_path)])

    def _on_clear_log(self) -> None:
        if messagebox.askyesno("Clear Log", "Delete logs/temps.csv?",
                               parent=self):
            log_path = Path(__file__).parent / self._cfg.log_dir / "temps.csv"
            if log_path.exists():
                log_path.unlink()
            self._log_box.delete(0, "end")


class _AddProjectorDialog(tk.Toplevel):
    """Small dialog for adding a new projector."""

    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent)
        self.title("Add Projector")
        self.configure(bg=_C["bg"])
        self.resizable(False, False)
        self.result = None
        self._build()
        self.grab_set()

    def _build(self) -> None:
        pad = {"padx": 10, "pady": 4}
        fields = [
            ("Label",     "Projector 2"),
            ("IP Address",""),
            ("Port",      "4352"),
            ("Password",  ""),
            ("Threshold °C", ""),
        ]
        self._vars = {}
        for label, default in fields:
            row = tk.Frame(self, bg=_C["bg"])
            row.pack(fill="x", **pad)
            tk.Label(row, text=f"{label}:", font=("Courier", 10),
                     fg=_C["fg"], bg=_C["bg"], width=14, anchor="e"
                     ).pack(side="left")
            var = tk.StringVar(value=default)
            tk.Entry(row, textvariable=var, font=("Courier", 10),
                     bg=_C["bg_disp"], fg=_C["fg"],
                     insertbackground=_C["fg"], relief="flat",
                     highlightthickness=1,
                     highlightbackground=_C["border"], width=20
                     ).pack(side="left", padx=4)
            self._vars[label] = var

        btns = tk.Frame(self, bg=_C["bg"])
        btns.pack(pady=8)
        for txt, cmd in [("ADD", self._on_add), ("CANCEL", self.destroy)]:
            tk.Button(btns, text=txt, font=("Courier", 9, "bold"),
                      bg=_C["btn_bg"], fg=_C["fg"],
                      activebackground=_C["sel_bg"], activeforeground=_C["fg"],
                      relief="flat", bd=0, padx=10, pady=4,
                      cursor="hand2", command=cmd,
                      ).pack(side="left", padx=6)

    def _on_add(self) -> None:
        from config import ProjectorConfig
        try:
            port = int(self._vars["Port"].get() or "4352")
        except ValueError:
            messagebox.showerror("Error", "Port must be a number.", parent=self)
            return
        ip = self._vars["IP Address"].get().strip()
        if not ip:
            messagebox.showerror("Error", "IP address is required.", parent=self)
            return
        self.result = ProjectorConfig(
            label=self._vars["Label"].get().strip() or ip,
            ip=ip,
            port=port,
            auth_password=self._vars["Password"].get(),
        )
        self.destroy()
