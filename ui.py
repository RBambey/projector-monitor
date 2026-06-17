"""Tkinter dashboard — DSKY phosphor-green aesthetic matching joystick-midi."""

from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import messagebox
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

_BAR_CHARS  = " ▁▂▃▄▅▆▇█"
_LOG_LINES  = 120
_PROJ_COLORS = ["#39ff14", "#00d4ff", "#ff8c00", "#cc88ff", "#ffdd00"]


def _temp_color(temp: float, threshold: float) -> str:
    if temp >= threshold:
        return _C["alert"]
    if temp >= threshold * 0.85:
        return _C["warn"]
    return _C["fg"]


def _sparkline(readings: List["TempReading"], threshold: float, width: int = 60) -> str:
    temps = [r.temp_celsius for r in readings if r.temp_celsius is not None]
    if not temps:
        return " " * width
    temps = temps[-width:]
    max_val = max(threshold * 1.5, max(temps))
    chars = []
    for t in temps:
        idx = int(t / max_val * (len(_BAR_CHARS) - 1))
        chars.append(_BAR_CHARS[max(0, min(idx, len(_BAR_CHARS) - 1))])
    return " " * (width - len(chars)) + "".join(chars)


# ---------------------------------------------------------------------------
# Per-projector panel (dashboard tile)
# ---------------------------------------------------------------------------

class _ProjectorPanel(tk.Frame):
    def __init__(self, parent: tk.Widget, proj: "ProjectorConfig",
                 cfg: "AppConfig") -> None:
        super().__init__(parent, bg=_C["bg"], bd=1, relief="flat",
                         highlightbackground=_C["border"], highlightthickness=1)
        self._proj = proj
        self._cfg = cfg
        self._build()

    def _build(self) -> None:
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

        spark_frame = tk.Frame(self, bg=_C["bg_disp"],
                               highlightbackground=_C["border"], highlightthickness=1)
        spark_frame.pack(fill="x", padx=6, pady=(0, 6))

        self._spark = tk.Text(spark_frame, height=1, font=("Courier", 9),
                              bg=_C["bg_disp"], fg=_C["fg"],
                              relief="flat", state="disabled",
                              cursor="arrow", takefocus=False, wrap="none")
        self._spark.pack(fill="x", padx=4, pady=2)
        self._spark.tag_configure("alert", foreground=_C["alert"])

    def update(self, readings: List["TempReading"]) -> None:
        if not readings:
            return

        latest_temps: Dict = {}
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
                self._sensors_var.set("\n".join(
                    f"S{i}: {r.temp_celsius:.1f}°C"
                    for i, r in sorted(latest_temps.items())
                ))
            else:
                self._sensors_var.set("")
            self._status.config(text="ONLINE", fg=_C["fg"])
        elif latest_error:
            self._status.config(text=latest_error.error or "ERR", fg=_C["warn"])
            self._ind.config(fg=_C["warn"])
            self._temp_var.set("--.-°C")
            self._temp_lbl.config(fg=_C["fg_dim"])

        self._ts_var.set(latest_ts.strftime("%H:%M:%S"))

        by_ts: Dict = {}
        for r in readings:
            if r.temp_celsius is not None:
                if r.timestamp not in by_ts or r.temp_celsius > by_ts[r.timestamp]:
                    by_ts[r.timestamp] = r.temp_celsius

        proxy = [type("R", (), {"temp_celsius": v})() for v in by_ts.values()]
        line = _sparkline(proxy, self._cfg.temp_threshold, width=60)

        self._spark.config(state="normal")
        self._spark.delete("1.0", "end")
        threshold = self._cfg.temp_threshold
        spark_temps = list(by_ts.values())[-60:]
        char_list = list(line.lstrip(" "))
        leading = len(line) - len(line.lstrip(" "))
        self._spark.insert("end", " " * leading)
        for i, ch in enumerate(char_list):
            actual = spark_temps[i] if i < len(spark_temps) else 0
            self._spark.insert("end", ch, "alert" if actual >= threshold else "")
        self._spark.config(state="disabled")


# ---------------------------------------------------------------------------
# Graph window
# ---------------------------------------------------------------------------

class _GraphWindow(tk.Toplevel):
    """Floating line-chart window — 1-min / 10-min / 1-hr time windows."""

    _WINDOWS = [("1 MIN", 60), ("10 MIN", 600), ("1 HR", 3600)]
    _PL, _PR, _PT, _PB = 52, 14, 14, 38  # canvas padding: left/right/top/bottom

    def __init__(self, parent: tk.Widget, cfg: "AppConfig",
                 poller: "TemperaturePoller") -> None:
        super().__init__(parent)
        self.transient(parent)
        self.title("TEMPERATURE GRAPH")
        self.configure(bg=_C["bg"])
        self.resizable(True, True)
        self._cfg = cfg
        self._poller = poller
        self._window_secs = 60
        self._alive = True
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # Position below the main window
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        self.geometry(f"{max(pw, 720)}x380+{px}+{py + ph + 10}")
        self._refresh()

    def _build(self) -> None:
        ctrl = tk.Frame(self, bg=_C["bg"])
        ctrl.pack(fill="x", padx=10, pady=(8, 4))

        tk.Label(ctrl, text="WINDOW:", font=("Courier", 9, "bold"),
                 fg=_C["fg_dim"], bg=_C["bg"]).pack(side="left", padx=(0, 8))

        self._win_btns: Dict[int, tk.Button] = {}
        for label, secs in self._WINDOWS:
            btn = tk.Button(
                ctrl, text=label, font=("Courier", 9, "bold"),
                bg=_C["btn_bg"], fg=_C["fg_dim"],
                activebackground=_C["sel_bg"], activeforeground=_C["fg"],
                relief="flat", bd=0, padx=10, pady=3, cursor="hand2",
                command=lambda s=secs: self._set_window(s),
            )
            btn.pack(side="left", padx=2)
            self._win_btns[secs] = btn
        self._win_btns[60].config(bg=_C["sel_bg"], fg=_C["fg"])

        self._canvas = tk.Canvas(
            self, bg=_C["bg_disp"], bd=0,
            highlightthickness=1, highlightbackground=_C["border"],
            width=720, height=300,
        )
        self._canvas.pack(fill="both", expand=True, padx=10, pady=4)
        self._canvas.bind("<Configure>", lambda _e: self._draw())

        leg = tk.Frame(self, bg=_C["bg"])
        leg.pack(fill="x", padx=10, pady=(0, 8))
        self._legend = leg
        self._rebuild_legend()

    def _rebuild_legend(self) -> None:
        for w in self._legend.winfo_children():
            w.destroy()
        for i, proj in enumerate(p for p in self._cfg.projectors if p.enabled):
            color = _PROJ_COLORS[i % len(_PROJ_COLORS)]
            tk.Label(self._legend, text="━━", font=("Courier", 10, "bold"),
                     fg=color, bg=_C["bg"]).pack(side="left", padx=(0, 2))
            tk.Label(self._legend, text=proj.label, font=("Courier", 9),
                     fg=_C["fg"], bg=_C["bg"]).pack(side="left", padx=(0, 16))
        tk.Label(self._legend, text="- -", font=("Courier", 9),
                 fg=_C["alert"], bg=_C["bg"]).pack(side="left", padx=(0, 2))
        tk.Label(self._legend,
                 text=f"threshold  {self._cfg.temp_threshold:.0f}°C",
                 font=("Courier", 9), fg=_C["alert"], bg=_C["bg"]
                 ).pack(side="left")

    def _set_window(self, secs: int) -> None:
        self._window_secs = secs
        for s, btn in self._win_btns.items():
            btn.config(bg=_C["sel_bg"] if s == secs else _C["btn_bg"],
                       fg=_C["fg"]     if s == secs else _C["fg_dim"])
        self._draw()

    def _on_close(self) -> None:
        self._alive = False
        self.destroy()

    def _refresh(self) -> None:
        if not self._alive:
            return
        try:
            self._draw()
            self.after(1000, self._refresh)
        except tk.TclError:
            pass

    def _draw(self) -> None:
        c = self._canvas
        cw, ch = c.winfo_width(), c.winfo_height()
        if cw < 80 or ch < 60:
            return
        c.delete("all")

        pl, pr, pt, pb = self._PL, self._PR, self._PT, self._PB
        pw = cw - pl - pr   # plot width
        ph = ch - pt - pb   # plot height

        now = datetime.now()
        cutoff = now - timedelta(seconds=self._window_secs)
        threshold = self._cfg.temp_threshold

        # Gather {ts: max_temp} per projector
        proj_data: List[tuple] = []
        all_temps: List[float] = []
        for proj in self._cfg.projectors:
            if not proj.enabled:
                continue
            by_ts: Dict[datetime, float] = {}
            for r in self._poller.get_buffer(proj.ip):
                if r.timestamp < cutoff or r.temp_celsius is None:
                    continue
                if r.timestamp not in by_ts or r.temp_celsius > by_ts[r.timestamp]:
                    by_ts[r.timestamp] = r.temp_celsius
            proj_data.append((proj, by_ts))
            all_temps.extend(by_ts.values())

        # Y scale — snap to 10° grid
        if all_temps:
            y_lo = max(0, int((min(all_temps) - 5) // 10) * 10)
            y_hi = int((max(max(all_temps) + 5, threshold + 10) + 9) // 10) * 10
        else:
            y_lo, y_hi = 0, int((threshold + 10 + 9) // 10) * 10
        y_rng = y_hi - y_lo or 1

        def xp(ts: datetime) -> float:
            return pl + (1.0 - (now - ts).total_seconds() / self._window_secs) * pw

        def yp(temp: float) -> float:
            return pt + ph * (1.0 - (temp - y_lo) / y_rng)

        # Y grid lines + labels
        grid_step = 10 if y_rng <= 80 else 20
        y = y_lo
        while y <= y_hi:
            yy = yp(y)
            c.create_line(pl, yy, pl + pw, yy, fill=_C["border"])
            c.create_text(pl - 4, yy, text=f"{y}°",
                          font=("Courier", 8), fill=_C["fg_dim"], anchor="e")
            y += grid_step

        # Threshold dashed line
        yy_t = yp(threshold)
        c.create_line(pl, yy_t, pl + pw, yy_t,
                      fill=_C["alert"], dash=(6, 4), width=1)
        c.create_text(pl + pw - 2, yy_t - 4,
                      text=f"{threshold:.0f}°C",
                      font=("Courier", 7), fill=_C["alert"], anchor="e")

        # X axis ticks + time labels
        fmt = "%H:%M" if self._window_secs >= 600 else "%H:%M:%S"
        for i in range(5):
            frac = i / 4
            xx = pl + frac * pw
            lbl = (cutoff + timedelta(seconds=frac * self._window_secs)).strftime(fmt)
            c.create_line(xx, pt + ph, xx, pt + ph + 4, fill=_C["fg_dim"])
            c.create_text(xx, pt + ph + 6, text=lbl,
                          font=("Courier", 7), fill=_C["fg_dim"], anchor="n")

        # Plot border
        c.create_rectangle(pl, pt, pl + pw, pt + ph, outline=_C["border"])

        # Temperature lines, one per projector
        for idx, (proj, by_ts) in enumerate(proj_data):
            if not by_ts:
                continue
            color = _PROJ_COLORS[idx % len(_PROJ_COLORS)]
            coords: List[float] = []
            for ts, temp in sorted(by_ts.items()):
                coords += [xp(ts), yp(max(y_lo, min(y_hi, temp)))]
            if len(coords) >= 4:
                c.create_line(*coords, fill=color, width=2, smooth=True)
            elif len(coords) == 2:
                x0, y0 = coords
                c.create_oval(x0 - 3, y0 - 3, x0 + 3, y0 + 3,
                               fill=color, outline="")


# ---------------------------------------------------------------------------
# Main monitor dashboard
# ---------------------------------------------------------------------------

class MonitorApp(tk.Tk):
    def __init__(self, cfg: "AppConfig", poller: "TemperaturePoller") -> None:
        super().__init__()
        self._cfg = cfg
        self._poller = poller
        self._panels: Dict[str, _ProjectorPanel] = {}
        self._log_lines: List[str] = []
        self._graph_win: Optional[_GraphWindow] = None

        self.title("PROJECTOR MONITOR")
        self.configure(bg=_C["bg"])
        self.resizable(True, True)
        self._build()
        self._refresh()

    def _build(self) -> None:
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

        tk.Frame(self, bg=_C["border"], height=1).pack(fill="x", padx=8)

        self._panels_frame = tk.Frame(self, bg=_C["bg"])
        self._panels_frame.pack(fill="x", padx=8, pady=4)
        for proj in self._cfg.projectors:
            if proj.enabled:
                self._add_panel(proj)

        tk.Frame(self, bg=_C["border"], height=1).pack(fill="x", padx=8)

        log_frame = tk.Frame(self, bg=_C["bg"])
        log_frame.pack(fill="both", expand=True, padx=8, pady=(4, 0))
        tk.Label(log_frame, text="RECENT READINGS",
                 font=("Courier", 9, "bold"), fg=_C["fg_dim"], bg=_C["bg"]
                 ).pack(anchor="w")

        self._log_box = tk.Listbox(
            log_frame, font=("Courier", 9),
            bg=_C["bg_disp"], fg=_C["fg"],
            selectbackground=_C["sel_bg"], activestyle="none",
            relief="flat", highlightthickness=1,
            highlightbackground=_C["border"], height=8,
        )
        sb = tk.Scrollbar(log_frame, orient="vertical", command=self._log_box.yview)
        self._log_box.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._log_box.pack(fill="both", expand=True)

        btn_frame = tk.Frame(self, bg=_C["bg"])
        btn_frame.pack(fill="x", padx=8, pady=8)
        for label, cmd in [
            ("GRAPH",         self._on_graph),
            ("ADD PROJECTOR", self._on_add_projector),
            ("OPEN LOG DIR",  self._on_open_log_dir),
            ("CLEAR LOG",     self._on_clear_log),
        ]:
            tk.Button(
                btn_frame, text=label, font=("Courier", 9, "bold"),
                bg=_C["btn_bg"], fg=_C["fg"],
                activebackground=_C["sel_bg"], activeforeground=_C["fg"],
                relief="flat", bd=0, padx=10, pady=4,
                cursor="hand2", command=cmd,
            ).pack(side="left", padx=(0, 6))

    def _add_panel(self, proj: "ProjectorConfig") -> None:
        panel = _ProjectorPanel(self._panels_frame, proj, self._cfg)
        panel.pack(fill="x", pady=2)
        self._panels[proj.ip] = panel

    def _refresh(self) -> None:
        for ip, panel in self._panels.items():
            readings = self._poller.get_buffer(ip)
            panel.update(readings)
            if readings:
                r = readings[-1]
                ts = r.timestamp.strftime("%H:%M:%S")
                line = (f"{ts}  {r.projector_label:<20}  "
                        f"S{r.sensor_index}: {r.temp_celsius:.1f}°C"
                        if r.temp_celsius is not None
                        else f"{ts}  {r.projector_label:<20}  {r.error}")
                self._append_log(line)
        self.after(1000, self._refresh)

    def _append_log(self, line: str) -> None:
        self._log_lines.append(line)
        if len(self._log_lines) > _LOG_LINES:
            self._log_lines = self._log_lines[-_LOG_LINES:]
        self._log_box.insert("end", line)
        while self._log_box.size() > _LOG_LINES:
            self._log_box.delete(0)
        self._log_box.see("end")

    # Button handlers ---------------------------------------------------

    def _on_graph(self) -> None:
        if self._graph_win is not None:
            try:
                if self._graph_win.winfo_exists():
                    self._graph_win.lift()
                    return
            except tk.TclError:
                pass
        self._graph_win = _GraphWindow(self, self._cfg, self._poller)

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
        if not messagebox.askyesno("Clear Log", "Delete all temp log files?",
                                   parent=self):
            return
        log_dir = Path(__file__).parent / self._cfg.log_dir
        for f in log_dir.glob("temps_????????.csv"):
            f.unlink(missing_ok=True)
        old = log_dir / "temps.csv"   # pre-rotation legacy file
        if old.exists():
            old.unlink()
        self._log_box.delete(0, "end")


# ---------------------------------------------------------------------------
# Add-projector dialog (during live monitoring)
# ---------------------------------------------------------------------------

class _AddProjectorDialog(tk.Toplevel):
    def __init__(self, parent: tk.Widget) -> None:
        super().__init__(parent)
        self.transient(parent)
        self.title("Add Projector")
        self.configure(bg=_C["bg"])
        self.resizable(False, False)
        self.result = None
        self._build()
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_x()
        py = parent.winfo_y()
        w = self.winfo_width()
        h = self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")
        self.lift()
        self.focus_force()
        self.grab_set()

    def _build(self) -> None:
        pad = {"padx": 12, "pady": 5}
        fields = [("Label", "Projector"), ("IP Address", ""),
                  ("Port", "4352"), ("Password", "")]
        self._vars: Dict[str, tk.StringVar] = {}
        for label, default in fields:
            row = tk.Frame(self, bg=_C["bg"])
            row.pack(fill="x", **pad)
            tk.Label(row, text=f"{label}:", font=("Courier", 10),
                     fg=_C["fg"], bg=_C["bg"], width=12, anchor="e"
                     ).pack(side="left")
            var = tk.StringVar(value=default)
            entry = tk.Entry(row, textvariable=var, font=("Courier", 10),
                             bg=_C["bg_disp"], fg=_C["fg"],
                             insertbackground=_C["fg"], relief="flat",
                             highlightthickness=1,
                             highlightbackground=_C["border"], width=22)
            entry.pack(side="left", padx=4)
            if label == "IP Address":
                entry.focus_set()
            self._vars[label] = var

        btns = tk.Frame(self, bg=_C["bg"])
        btns.pack(pady=10)
        for txt, cmd in [("ADD", self._on_add), ("CANCEL", self.destroy)]:
            tk.Button(btns, text=txt, font=("Courier", 10, "bold"),
                      bg=_C["btn_bg"], fg=_C["fg"],
                      activebackground=_C["sel_bg"], activeforeground=_C["fg"],
                      relief="flat", bd=0, padx=12, pady=5,
                      cursor="hand2", command=cmd,
                      ).pack(side="left", padx=6)
        self.bind("<Return>", lambda e: self._on_add())
        self.bind("<Escape>", lambda e: self.destroy())

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
