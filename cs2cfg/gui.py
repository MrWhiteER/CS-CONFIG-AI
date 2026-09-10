"""Tkinter front end.

Deliberately thin: it collects choices, calls the same functions the CLI
calls, and prints the same report. Any behaviour that only exists in the GUI
is behaviour that cannot be scripted or reviewed, so there is none.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Dict, List, Optional

from . import __version__, backup, emit, steam
from .hardware import Machine, ProbeError, detect
from .kb import KnowledgeBase, KnowledgeError
from .profile import Profile, build_profile, plan_launch_options

MONO = ("Consolas", 10)
PAD = 10


class App(ttk.Frame):
    def __init__(self, master: tk.Tk, args: Any) -> None:
        super().__init__(master, padding=PAD)
        self.master = master
        self.args = args
        self.grid(sticky="nsew")

        self.kb = KnowledgeBase()
        self.machine: Optional[Machine] = None
        self.profile: Optional[Profile] = None
        self.users: List[steam.SteamUser] = []
        self.user: Optional[steam.SteamUser] = None
        self.steam_root: Optional[Path] = None
        self.cs2_install: Optional[Path] = None
        self.launch_plan = None

        self.events: "queue.Queue[tuple]" = queue.Queue()
        self.busy = False

        self._build_layout()
        self.after(100, self._drain)
        self.run_async("Detecting hardware", self._task_scan)

    # -- layout -----------------------------------------------------------
    def _build_layout(self) -> None:
        self.master.columnconfigure(0, weight=1)
        self.master.rowconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)

        side = ttk.Frame(self)
        side.grid(row=0, column=0, sticky="ns", padx=(0, PAD))

        hardware = ttk.LabelFrame(side, text="Detected", padding=PAD)
        hardware.grid(row=0, column=0, sticky="ew")
        self.hw_labels: Dict[str, ttk.Label] = {}
        for row, key in enumerate(("CPU", "GPU", "Memory", "Display", "Power")):
            ttk.Label(hardware, text=key, width=8).grid(row=row, column=0, sticky="w")
            label = ttk.Label(hardware, text="...", wraplength=250, justify="left")
            label.grid(row=row, column=1, sticky="w")
            self.hw_labels[key] = label

        account = ttk.LabelFrame(side, text="Steam account", padding=PAD)
        account.grid(row=1, column=0, sticky="ew", pady=(PAD, 0))
        self.account_var = tk.StringVar()
        self.account_box = ttk.Combobox(account, textvariable=self.account_var, state="readonly", width=34)
        self.account_box.grid(row=0, column=0, sticky="ew")
        self.account_box.bind("<<ComboboxSelected>>", lambda _e: self._pick_account())

        options = ttk.LabelFrame(side, text="Optimise for", padding=PAD)
        options.grid(row=2, column=0, sticky="ew", pady=(PAD, 0))
        self.intent_var = tk.StringVar(value=getattr(self.args, "intent", "balanced") or "balanced")
        for row, (value, caption) in enumerate((
            ("competitive", "Competitive  - frames and clarity"),
            ("balanced", "Balanced  - the default"),
            ("quality", "Quality  - best picture that still keeps up"),
        )):
            ttk.Radiobutton(
                options, text=caption, value=value, variable=self.intent_var,
                command=self._invalidate,
            ).grid(row=row, column=0, sticky="w")

        target = ttk.Frame(options)
        target.grid(row=3, column=0, sticky="ew", pady=(PAD, 0))
        ttk.Label(target, text="Target fps").grid(row=0, column=0, sticky="w")
        self.target_var = tk.StringVar(value=str(getattr(self.args, "target_fps", "") or ""))
        entry = ttk.Entry(target, textvariable=self.target_var, width=8)
        entry.grid(row=0, column=1, sticky="w", padx=(6, 0))
        entry.bind("<FocusOut>", lambda _e: self._invalidate())
        ttk.Label(target, text="blank = refresh rate", foreground="#777").grid(row=0, column=2, padx=(6, 0))

        writes = ttk.LabelFrame(side, text="Write", padding=PAD)
        writes.grid(row=3, column=0, sticky="ew", pady=(PAD, 0))
        self.write_video = tk.BooleanVar(value=True)
        self.write_cfg = tk.BooleanVar(value=True)
        self.write_launch = tk.BooleanVar(value=True)
        self.link_autoexec = tk.BooleanVar(value=False)
        for row, (var, caption) in enumerate((
            (self.write_video, "Picture quality (cs2_video.txt)"),
            (self.write_cfg, "Generated .vcfg config"),
            (self.write_launch, "Steam launch options"),
            (self.link_autoexec, "Add exec line to autoexec.vcfg"),
        )):
            ttk.Checkbutton(writes, text=caption, variable=var).grid(row=row, column=0, sticky="w")

        buttons = ttk.Frame(side)
        buttons.grid(row=4, column=0, sticky="ew", pady=(PAD, 0))
        self.plan_btn = ttk.Button(buttons, text="Preview changes", command=self.on_plan)
        self.plan_btn.grid(row=0, column=0, sticky="ew", pady=2)
        self.apply_btn = ttk.Button(buttons, text="Apply", command=self.on_apply, state="disabled")
        self.apply_btn.grid(row=1, column=0, sticky="ew", pady=2)
        self.revert_btn = ttk.Button(buttons, text="Undo last apply", command=self.on_revert)
        self.revert_btn.grid(row=2, column=0, sticky="ew", pady=2)
        ttk.Button(buttons, text="Rescan hardware", command=lambda: self.run_async("Detecting hardware", self._task_scan)).grid(row=3, column=0, sticky="ew", pady=2)
        buttons.columnconfigure(0, weight=1)

        # Output pane
        right = ttk.Frame(self)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(0, weight=1)

        self.text = tk.Text(right, wrap="none", font=MONO, height=30, width=88,
                            background="#12151a", foreground="#d8dee9",
                            insertbackground="#d8dee9", borderwidth=0, padx=10, pady=8)
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(right, orient="vertical", command=self.text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scroll.set, state="disabled")

        for tag, colour in (("head", "#88c0d0"), ("good", "#a3be8c"), ("warn", "#ebcb8b"),
                            ("bad", "#bf616a"), ("dim", "#6c7686")):
            self.text.tag_configure(tag, foreground=colour)
        self.text.tag_configure("head", foreground="#88c0d0", font=("Consolas", 10, "bold"))

        self.status = ttk.Label(self, text=f"cs2-autoconfig {__version__}", anchor="w")
        self.status.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(PAD, 0))

    # -- output -----------------------------------------------------------
    def write(self, text: str = "", tag: Optional[str] = None) -> None:
        self.text.configure(state="normal")
        self.text.insert("end", text + "\n", tag or ())
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")

    def section(self, title: str) -> None:
        self.write()
        self.write(title, "head")
        self.write("-" * max(len(title), 20), "dim")

    # -- async plumbing ---------------------------------------------------
    def run_async(self, label: str, fn) -> None:
        if self.busy:
            return
        self.busy = True
        self.status.configure(text=f"{label}...")
        self._set_buttons("disabled")

        def worker() -> None:
            try:
                fn()
            except Exception as exc:  # surfaced in the UI, never swallowed
                self.events.put(("error", exc))
            finally:
                self.events.put(("done", label))

        threading.Thread(target=worker, daemon=True).start()

    def _set_buttons(self, state: str) -> None:
        self.plan_btn.configure(state=state)
        self.revert_btn.configure(state=state)
        if state == "disabled":
            self.apply_btn.configure(state="disabled")
        elif self.profile is not None:
            self.apply_btn.configure(state="normal")

    def _drain(self) -> None:
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "line":
                self.write(*payload)
            elif kind == "section":
                self.section(payload)
            elif kind == "clear":
                self.clear()
            elif kind == "hardware":
                self._show_hardware(payload)
            elif kind == "accounts":
                self._show_accounts(payload)
            elif kind == "status":
                self.status.configure(text=payload)
            elif kind == "error":
                self.write(f"\n  {payload}", "bad")
                self.status.configure(text="Failed")
            elif kind == "done":
                self.busy = False
                self._set_buttons("normal")
                if "Failed" not in self.status.cget("text"):
                    self.status.configure(text="Ready")
        self.after(100, self._drain)

    def emit(self, text: str = "", tag: Optional[str] = None) -> None:
        self.events.put(("line", (text, tag)))

    # -- panels -----------------------------------------------------------
    def _show_hardware(self, machine: Machine) -> None:
        cpu = machine.cpu
        gpu = machine.gpu
        display = machine.primary_display
        self.hw_labels["CPU"].configure(
            text=f"{cpu.name}\n{cpu.cores}C / {cpu.threads}T" if cpu else "not detected")
        self.hw_labels["GPU"].configure(
            text=f"{gpu.name}\n{gpu.vram_gb:g} GB VRAM" if gpu else "not detected")
        self.hw_labels["Memory"].configure(text=f"{machine.ram_gb:g} GB")
        self.hw_labels["Display"].configure(
            text=f"{display.width}x{display.height} @ {display.refresh} Hz" if display else "not detected")
        self.hw_labels["Power"].configure(text=machine.power_plan or "unknown")

    def _show_accounts(self, users: List[steam.SteamUser]) -> None:
        self.users = users
        labels = [u.label for u in users]
        self.account_box.configure(values=labels)
        if labels:
            index = 0
            if self.user:
                index = next((i for i, u in enumerate(users) if u.account_id == self.user.account_id), 0)
            self.account_box.current(index)
            self.user = users[index]

    def _pick_account(self) -> None:
        index = self.account_box.current()
        if 0 <= index < len(self.users):
            self.user = self.users[index]
            self._invalidate()

    def _invalidate(self) -> None:
        self.profile = None
        self.apply_btn.configure(state="disabled")

    def _target_fps(self) -> Optional[int]:
        raw = self.target_var.get().strip()
        return int(raw) if raw.isdigit() else None

    # -- tasks ------------------------------------------------------------
    def _task_scan(self) -> None:
        self.events.put(("clear", None))
        self.emit("  Probing hardware...", "dim")
        machine = detect()
        self.machine = machine
        self.events.put(("hardware", machine))

        try:
            self.steam_root = Path(self.args.steam_root) if getattr(self.args, "steam_root", None) else steam.find_steam_root()
            self.cs2_install = steam.find_cs2_install(self.steam_root)
            users = steam.list_users(self.steam_root)
            self.events.put(("accounts", users))
        except steam.SteamError as exc:
            self.emit(f"  Steam: {exc}", "warn")
            users = []

        self.events.put(("section", "Hardware"))
        if machine.cpu:
            hybrid = "  (hybrid P/E cores)" if machine.cpu.likely_hybrid else ""
            self.emit(f"  CPU       {machine.cpu.name}{hybrid}")
        if machine.gpu:
            self.emit(f"  GPU       {machine.gpu.name}  ({machine.gpu.vram_gb:g} GB)")
            self.emit(f"            driver {machine.gpu.driver_version}  {machine.gpu.driver_date or ''}", "dim")
        self.emit(f"  Memory    {machine.ram_gb:g} GB")
        for display in machine.displays:
            mark = "*" if display.primary else " "
            note = "" if display.confident_refresh else "   (from EDID; may understate)"
            self.emit(f"  Display {mark} {display.width}x{display.height} @ {display.refresh} Hz{note}")
        self.emit(f"  OS        {machine.os_caption} build {machine.os_build}")
        self.emit(f"  Power     {machine.power_plan or 'unknown'}")

        if self.cs2_install:
            self.emit(f"  CS2       {self.cs2_install}  [{machine.media_type_for(self.cs2_install)}]")
        if users:
            self.events.put(("section", "Steam accounts"))
            for user in users:
                self.emit(f"  {user.label}")
        self.emit()
        self.emit("  Ready. Choose what to optimise for, then Preview changes.", "dim")

    def _task_plan(self, apply_after: bool = False) -> None:
        if self.machine is None or self.user is None:
            self.emit("  Run a scan first, and make sure a Steam account is selected.", "warn")
            return

        current_video = steam.read_video_cfg(self.user)
        current_launch = steam.read_launch_options(self.user)

        profile = build_profile(
            self.machine, self.kb,
            intent=self.intent_var.get(),
            target_fps=self._target_fps(),
            current_video=current_video,
        )
        self.profile = profile

        folder = getattr(self.args, "cfg_folder", "mrwhiteer")
        name = getattr(self.args, "cfg_name", "autoperf.vcfg")
        self.launch_plan = plan_launch_options(
            current_launch, self.machine, self.kb,
            exec_path=f"{folder}\\{name}",
            want_console=None,
        )

        self.events.put(("clear", None))
        self.events.put(("section", "Assessment"))
        self.emit(f"  CPU score      {profile.cpu_match.index:.0f}"
                  + ("" if profile.cpu_match.exact else f"   ({profile.cpu_match.note})"))
        self.emit(f"  GPU score      {profile.gpu_match.index:.0f}"
                  + ("" if profile.gpu_match.exact else f"   ({profile.gpu_match.note})"))
        self.emit(f"  CPU ceiling    ~{profile.cpu_ceiling} fps")
        self.emit(f"  GPU ceiling    ~{profile.gpu_ceiling} fps at these settings")
        self.emit(f"  Limited by     {profile.bottleneck}")
        tag = "good" if profile.headroom >= 1.15 else "warn" if profile.headroom >= 0.85 else "bad"
        self.emit(f"  Estimate       ~{profile.estimated_fps} fps  "
                  f"({profile.headroom:.2f}x your {profile.target_fps} Hz target)", tag)
        self.emit(f"  Tier           {profile.tier}   with the {profile.intent} profile")
        self.emit()
        self.emit("  " + self.kb.video["intents"][profile.intent]["description"], "dim")

        self.events.put(("section", "Picture quality  (cs2_video.txt)"))
        changed = 0
        for key in sorted(profile.video):
            value = profile.video[key]
            before = current_video.get(key)
            label = self.kb.label(key, value)
            ui = self.kb.ui_name(key)
            if before is None:
                self.emit(f"  {ui:<32} {label}   (new)", "good")
                changed += 1
            elif str(value) != before:
                try:
                    before_label = self.kb.label(key, int(before))
                except ValueError:
                    before_label = before
                self.emit(f"  {ui:<32} {before_label}  ->  {label}", "good")
                changed += 1
            else:
                self.emit(f"  {ui:<32} {label}   (unchanged)", "dim")
        self.emit()
        self.emit(f"  {changed} setting(s) would change.", "dim")

        self.events.put(("section", "Steam launch options"))
        self.emit(f"  current:  {current_launch or '(none set)'}", "dim")
        self.emit()
        self.emit(f"  {self.launch_plan.line}", "good")
        for option, reason in self.launch_plan.removed:
            self.emit(f"    removed  {option}", "bad")
            self.emit(f"             {reason}", "dim")
        for option, reason in self.launch_plan.added:
            self.emit(f"    added    {option}", "good")
            self.emit(f"             {reason}", "dim")

        if profile.advisories:
            self.events.put(("section", "Worth knowing"))
            for advisory in profile.advisories:
                self.emit(f"  {'!' if advisory.level == 'warn' else 'i'} {advisory.title}",
                          "warn" if advisory.level == "warn" else None)
                self.emit(f"    {advisory.detail}", "dim")

        if steam.steam_running() and self.write_launch.get():
            self.emit()
            self.emit("  ! Steam is running. Close it before applying, or Steam will", "warn")
            self.emit("    overwrite the launch options when it exits.", "warn")

        self.emit()
        self.emit("  Nothing has been written. Press Apply to commit.", "dim")

    def _task_apply(self) -> None:
        profile = self.profile
        if profile is None or self.user is None:
            return

        if self.write_launch.get() and steam.steam_running():
            self.emit()
            self.emit("  Steam is running; launch options were not written.", "bad")
            self.emit("  Close Steam and apply again, or untick the launch options box.", "dim")
            return

        session = backup.BackupSession(note=f"gui apply {profile.intent}/tier {profile.tier}")
        self.events.put(("section", "Writing"))

        if self.write_video.get():
            try:
                diff = steam.write_video_cfg(self.user, profile.video, session)
                self.emit(f"  ok   cs2_video.txt   ({len(diff)} setting(s) changed)", "good")
            except steam.SteamError as exc:
                self.emit(f"  --   cs2_video.txt: {exc}", "bad")

        folder = getattr(self.args, "cfg_folder", "mrwhiteer")
        name = getattr(self.args, "cfg_name", "autoperf.vcfg")
        if self.write_cfg.get() and self.cs2_install:
            root = steam.cfg_dir(self.cs2_install)
            target = root / folder / name
            emit.write_text_file(target, emit.render_cfg(profile, self.kb, name), session)
            self.emit(f"  ok   {name}", "good")
            self.emit(f"       {target}", "dim")

            notes = root / folder / "launch_options_generated.txt"
            emit.write_text_file(
                notes,
                emit.render_launch_notes(profile, self.launch_plan.line,
                                         self.launch_plan.removed, self.launch_plan.added),
                session,
            )
            self.emit("  ok   launch_options_generated.txt", "good")

            if self.link_autoexec.get():
                result = emit.ensure_exec_line(root / folder / "autoexec.vcfg", f"{folder}/{name}", session)
                self.emit(f"  ok   autoexec.vcfg   ({result})", "good")
        elif self.write_cfg.get():
            self.emit("  --   CS2 install not found; no config written", "warn")

        if self.write_launch.get():
            try:
                action = steam.write_launch_options(self.user, self.launch_plan.line, session)
                self.emit(f"  ok   Steam launch options   ({action})", "good")
            except steam.SteamError as exc:
                self.emit(f"  --   launch options: {exc}", "bad")

        self.emit()
        if session.empty:
            self.emit("  Nothing existed to back up.", "dim")
        else:
            self.emit(f"  Backup {session.stamp} saved to {session.dir}", "dim")
            self.emit("  Undo it with the 'Undo last apply' button.", "dim")
        backup.prune()

    # -- button handlers --------------------------------------------------
    def on_plan(self) -> None:
        self.run_async("Building plan", self._task_plan)

    def on_apply(self) -> None:
        if self.profile is None:
            return
        summary = (
            f"Apply the tier {self.profile.tier} / {self.profile.intent} profile?\n\n"
            "Everything changed is backed up first and can be undone."
        )
        if not messagebox.askyesno("Apply changes", summary, parent=self.master):
            return
        self.run_async("Writing", self._task_apply)

    def on_revert(self) -> None:
        latest = backup.find_set("latest")
        if latest is None:
            messagebox.showinfo("Nothing to undo", "No backups have been taken yet.", parent=self.master)
            return
        if any("localconfig.vdf" in f for f in latest.files) and steam.steam_running():
            messagebox.showwarning(
                "Close Steam first",
                "This backup includes Steam's localconfig.vdf. Steam rewrites that file when it "
                "exits, so it would undo the restore. Close Steam and try again.",
                parent=self.master,
            )
            return

        listing = "\n".join(f"  {p}" for p in latest.originals)
        if not messagebox.askyesno(
            "Undo last apply",
            f"Restore the backup taken at {latest.when}?\n\n{listing}",
            parent=self.master,
        ):
            return

        def task() -> None:
            self.events.put(("section", f"Restoring {latest.stamp}"))
            for line in backup.restore(latest):
                self.emit(f"  {line}")

        self.run_async("Restoring", task)


def launch(args: Any) -> int:
    root = tk.Tk()
    root.title(f"cs2-autoconfig {__version__}")
    root.minsize(1040, 640)
    try:
        ttk.Style().theme_use("vista")
    except tk.TclError:
        pass
    App(root, args)
    root.mainloop()
    return 0
