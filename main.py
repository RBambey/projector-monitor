#!/usr/bin/env python3
"""Projector Temperature Monitor — entry point."""

from __future__ import annotations

import gc
import queue
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

from config import AppConfig, ProjectorConfig, load_config, save_config
from logger import DataLogger
from poller import TemperaturePoller
from ui import MonitorApp, _C


class SetupWindow(tk.Tk):
    """Full-page setup screen: manage projectors and settings before monitoring."""

    def __init__(self, cfg: AppConfig) -> None:
        super().__init__()
        self._cfg = cfg
        self._result: AppConfig | None = None
        self._proj_rows: list[dict] = []

        self.title("PROJECTOR MONITOR — SETUP")
        self.configure(bg=_C["bg"])
        self.resizable(False, False)
        self._build()

    def run(self) -> AppConfig:
        self.mainloop()
        if self._result is None:
            sys.exit(0)
        return self._result

    # ------------------------------------------------------------------

    def _build(self) -> None:
        pad = {"padx": 14, "pady": 6}

        tk.Label(self, text="PROJECTOR MONITOR",
                 font=("Courier", 16, "bold"), fg=_C["fg"], bg=_C["bg"]
                 ).pack(**pad)
        tk.Frame(self, bg=_C["fg_dim"], height=1).pack(fill="x", padx=14)

        # ── Projector list ──────────────────────────────────────────────
        tk.Label(self, text="PROJECTORS",
                 font=("Courier", 10, "bold"), fg=_C["fg"], bg=_C["bg"]
                 ).pack(anchor="w", padx=14, pady=(10, 2))

        list_outer = tk.Frame(self, bg="#1e1e1e",
                              highlightbackground=_C["fg_dim"], highlightthickness=1)
        list_outer.pack(fill="x", padx=14, pady=(0, 4))

        self._list_frame = tk.Frame(list_outer, bg="#1e1e1e")
        self._list_frame.pack(fill="x", padx=4, pady=4)

        for proj in self._cfg.projectors:
            self._append_proj_row(proj)

        # ── Inline Add form ─────────────────────────────────────────────
        tk.Frame(self, bg=_C["fg_dim"], height=1).pack(fill="x", padx=14)
        tk.Label(self, text="ADD PROJECTOR",
                 font=("Courier", 10, "bold"), fg=_C["fg"], bg=_C["bg"]
                 ).pack(anchor="w", padx=14, pady=(8, 2))

        add_frame = tk.Frame(self, bg=_C["bg"])
        add_frame.pack(fill="x", padx=14, pady=(0, 4))

        self._add_vars: dict[str, tk.StringVar] = {}

        def _entry_row(parent, fields):
            row = tk.Frame(parent, bg=_C["bg"])
            row.pack(fill="x", pady=2)
            for lbl, key, default, w in fields:
                tk.Label(row, text=f"{lbl}:", font=("Courier", 10),
                         fg=_C["fg"], bg=_C["bg"], width=10, anchor="e"
                         ).pack(side="left")
                var = tk.StringVar(value=default)
                tk.Entry(row, textvariable=var, font=("Courier", 10),
                         bg="#2a2a2a", fg=_C["fg"],
                         insertbackground=_C["fg"], relief="flat",
                         highlightthickness=1, highlightbackground=_C["fg_dim"],
                         width=w
                         ).pack(side="left", padx=(2, 14))
                self._add_vars[key] = var
            return row

        _entry_row(add_frame, [
            ("Label", "label", "Projector", 14),
            ("IP",    "ip",    "",          16),
        ])
        _entry_row(add_frame, [
            ("Username", "web_username", "", 12),
            ("Password", "web_password", "", 14),
        ])

        row_add = tk.Frame(add_frame, bg=_C["bg"])
        row_add.pack(fill="x", pady=2)
        tk.Label(row_add, text="(web login — used for temperature polling)",
                 font=("Courier", 8), fg=_C["fg_dim"], bg=_C["bg"]
                 ).pack(side="left", padx=(6, 0))

        row3 = tk.Frame(add_frame, bg=_C["bg"])
        row3.pack(fill="x", pady=(4, 2))
        tk.Button(row3, text="+ ADD",
                  font=("Courier", 10, "bold"),
                  bg=_C["btn_bg"], fg=_C["fg"],
                  activebackground=_C["sel_bg"], activeforeground=_C["fg"],
                  relief="flat", bd=0, padx=10, pady=4,
                  cursor="hand2", command=self._on_add
                  ).pack(side="left")

        # ── Settings ────────────────────────────────────────────────────
        tk.Frame(self, bg=_C["fg_dim"], height=1).pack(fill="x", padx=14, pady=(6, 0))
        tk.Label(self, text="SETTINGS",
                 font=("Courier", 10, "bold"), fg=_C["fg"], bg=_C["bg"]
                 ).pack(anchor="w", padx=14, pady=(8, 2))

        settings_frame = tk.Frame(self, bg=_C["bg"])
        settings_frame.pack(fill="x", padx=14, pady=(0, 4))

        self._threshold_var = tk.StringVar(value=str(self._cfg.temp_threshold))
        self._poll_var = tk.StringVar(value=str(self._cfg.poll_interval))

        for lbl, var, unit in [
            ("Alert threshold", self._threshold_var, "°C"),
            ("Poll interval",   self._poll_var,      "seconds"),
        ]:
            row = tk.Frame(settings_frame, bg=_C["bg"])
            row.pack(fill="x", pady=2)
            tk.Label(row, text=f"{lbl}:", font=("Courier", 10),
                     fg=_C["fg"], bg=_C["bg"], width=18, anchor="e"
                     ).pack(side="left")
            tk.Entry(row, textvariable=var, font=("Courier", 11, "bold"),
                     bg="#2a2a2a", fg=_C["fg"],
                     insertbackground=_C["fg"], relief="flat",
                     highlightthickness=1, highlightbackground=_C["fg_dim"],
                     width=8
                     ).pack(side="left", padx=(4, 6))
            tk.Label(row, text=unit, font=("Courier", 10),
                     fg=_C["fg"], bg=_C["bg"]
                     ).pack(side="left")

        # ── Action buttons ───────────────────────────────────────────────
        tk.Frame(self, bg=_C["fg_dim"], height=1).pack(fill="x", padx=14, pady=(6, 0))
        btn_row = tk.Frame(self, bg=_C["bg"])
        btn_row.pack(fill="x", padx=14, pady=12)

        tk.Button(btn_row, text="START MONITORING",
                  font=("Courier", 12, "bold"),
                  bg=_C["btn_bg"], fg=_C["fg"],
                  activebackground=_C["sel_bg"], activeforeground=_C["fg"],
                  relief="flat", bd=0, padx=16, pady=8,
                  cursor="hand2", command=self._on_start
                  ).pack(side="left")

        tk.Button(btn_row, text="QUIT",
                  font=("Courier", 12, "bold"),
                  bg=_C["btn_bg"], fg=_C["fg_dim"],
                  activebackground="#3a0000", activeforeground=_C["alert"],
                  relief="flat", bd=0, padx=16, pady=8,
                  cursor="hand2", command=self.destroy
                  ).pack(side="right")

        self.bind("<Return>", lambda e: self._on_start())

    # ------------------------------------------------------------------

    def _append_proj_row(self, proj: ProjectorConfig) -> None:
        row = tk.Frame(self._list_frame, bg="#1e1e1e")
        row.pack(fill="x", pady=1)

        tk.Label(row, text="●", font=("Courier", 9),
                 fg=_C["fg"], bg="#1e1e1e"
                 ).pack(side="left", padx=(4, 2))
        tk.Label(row, text=f"{proj.label:<18}", font=("Courier", 10, "bold"),
                 fg=_C["fg"], bg="#1e1e1e"
                 ).pack(side="left")
        tk.Label(row, text=f"{proj.ip:<18}", font=("Courier", 10),
                 fg=_C["fg"], bg="#1e1e1e"
                 ).pack(side="left")
        tk.Label(row, text=f"port {proj.port}", font=("Courier", 9),
                 fg=_C["fg_dim"], bg="#1e1e1e"
                 ).pack(side="left", padx=8)

        entry = {"proj": proj, "frame": row}
        self._proj_rows.append(entry)

        tk.Button(row, text="REMOVE",
                  font=("Courier", 8, "bold"),
                  bg=_C["btn_bg"], fg=_C["warn"],
                  activebackground="#3a0000", activeforeground=_C["alert"],
                  relief="flat", bd=0, padx=6, pady=2,
                  cursor="hand2",
                  command=lambda e=entry: self._on_remove(e)
                  ).pack(side="right", padx=4)

    def _on_add(self) -> None:
        ip = self._add_vars["ip"].get().strip()
        if not ip:
            messagebox.showerror("Missing IP", "Enter an IP address.", parent=self)
            return
        label = self._add_vars["label"].get().strip() or ip
        proj = ProjectorConfig(
            label=label,
            ip=ip,
            web_username=self._add_vars["web_username"].get().strip(),
            web_password=self._add_vars["web_password"].get(),
        )
        self._cfg.projectors.append(proj)
        self._append_proj_row(proj)
        self._add_vars["ip"].set("")
        self._add_vars["label"].set("Projector")

    def _on_remove(self, entry: dict) -> None:
        entry["frame"].destroy()
        self._proj_rows = [r for r in self._proj_rows if r is not entry]
        self._cfg.projectors = [p for p in self._cfg.projectors if p is not entry["proj"]]

    def _on_start(self) -> None:
        if not self._cfg.projectors:
            messagebox.showerror("No projectors",
                                 "Add at least one projector before starting.",
                                 parent=self)
            return
        try:
            self._cfg.temp_threshold = float(self._threshold_var.get())
        except ValueError:
            messagebox.showerror("Bad threshold",
                                 "Alert threshold must be a number.", parent=self)
            return
        try:
            self._cfg.poll_interval = int(self._poll_var.get())
        except ValueError:
            messagebox.showerror("Bad interval",
                                 "Poll interval must be a whole number.", parent=self)
            return
        save_config(self._cfg)
        self._result = self._cfg
        self.destroy()


def main() -> None:
    cfg = load_config()
    _setup = SetupWindow(cfg)
    cfg = _setup.run()
    # SetupWindow is a tk.Tk subclass with widget circular refs. Force GC on the
    # main thread NOW — before poller threads start — so Tcl_Panic can't occur
    # when the cyclic GC runs on a background thread and tries to dealloc Tkapp.
    del _setup
    gc.collect()

    event_queue: queue.Queue = queue.Queue(maxsize=2000)
    poller = TemperaturePoller(cfg, event_queue)
    logger = DataLogger(cfg, poller, event_queue)

    poller.start()
    logger.start()

    app = MonitorApp(cfg, poller)
    try:
        app.mainloop()
    finally:
        poller.stop()
        logger.stop()


if __name__ == "__main__":
    main()
