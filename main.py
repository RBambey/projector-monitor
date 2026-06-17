#!/usr/bin/env python3
"""Projector Temperature Monitor — entry point."""

from __future__ import annotations

import queue
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

# Run from the projector-monitor/ directory so relative imports work cleanly
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

from config import load_config, save_config
from logger import DataLogger
from poller import TemperaturePoller
from ui import MonitorApp, _C


def _startup_dialog(cfg_threshold: float) -> float | None:
    """Show a small startup dialog asking for the alert threshold.

    Returns the chosen threshold, or None if the user cancelled.
    """
    root = tk.Tk()
    root.title("Projector Monitor — Setup")
    root.configure(bg=_C["bg"])
    root.resizable(False, False)

    result: list[float | None] = [None]

    pad = {"padx": 12, "pady": 6}

    tk.Label(root, text="PROJECTOR MONITOR",
             font=("Courier", 14, "bold"), fg=_C["fg"], bg=_C["bg"]
             ).pack(**pad)

    tk.Frame(root, bg=_C["border"], height=1).pack(fill="x", padx=12)

    tk.Label(root,
             text="Set the temperature alert threshold.\n"
                  "An alert file will be saved when any projector\n"
                  "exceeds this temperature.",
             font=("Courier", 9), fg=_C["fg_dim"], bg=_C["bg"], justify="left"
             ).pack(**pad)

    row = tk.Frame(root, bg=_C["bg"])
    row.pack(**pad)
    tk.Label(row, text="Alert threshold (°C):",
             font=("Courier", 10), fg=_C["fg"], bg=_C["bg"]
             ).pack(side="left")
    var = tk.StringVar(value=str(cfg_threshold))
    entry = tk.Entry(row, textvariable=var, font=("Courier", 12, "bold"),
                     bg=_C["bg_disp"], fg=_C["fg"],
                     insertbackground=_C["fg"], relief="flat",
                     highlightthickness=1, highlightbackground=_C["border"],
                     width=8)
    entry.pack(side="left", padx=6)
    entry.focus_set()
    entry.select_range(0, "end")

    def _ok(event=None) -> None:
        try:
            val = float(var.get())
        except ValueError:
            messagebox.showerror("Error", "Enter a number (e.g. 70.0)", parent=root)
            return
        result[0] = val
        root.destroy()

    def _cancel() -> None:
        root.destroy()

    root.bind("<Return>", _ok)
    root.bind("<Escape>", lambda e: _cancel())

    btn_row = tk.Frame(root, bg=_C["bg"])
    btn_row.pack(pady=(0, 12))
    tk.Button(btn_row, text="START MONITORING",
              font=("Courier", 10, "bold"),
              bg=_C["btn_bg"], fg=_C["fg"],
              activebackground=_C["sel_bg"], activeforeground=_C["fg"],
              relief="flat", bd=0, padx=14, pady=6,
              cursor="hand2", command=_ok
              ).pack(side="left", padx=6)
    tk.Button(btn_row, text="QUIT",
              font=("Courier", 10, "bold"),
              bg=_C["btn_bg"], fg=_C["fg_dim"],
              activebackground="#3a0000", activeforeground=_C["alert"],
              relief="flat", bd=0, padx=14, pady=6,
              cursor="hand2", command=_cancel
              ).pack(side="left", padx=6)

    root.mainloop()
    return result[0]


def main() -> None:
    cfg = load_config()

    threshold = _startup_dialog(cfg.temp_threshold)
    if threshold is None:
        sys.exit(0)

    cfg.temp_threshold = threshold
    save_config(cfg)

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
