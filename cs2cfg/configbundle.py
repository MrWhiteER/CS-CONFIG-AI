"""App-owned, account-scoped configs. No helper calls and no startup threads.

Preparation is separate from installation: a refused/missing game folder never
prevents the app copy from being built. Only the explicit wizard consent permits
installation. Imported originals are read once into a bounded snapshot.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import replace
from pathlib import Path

from . import backup, cfgformat, cfglang, cfgscan, starter
from .paths import user_data_dir

MAX_FILES = 256
MAX_BYTES = 4 * 1024 * 1024
IMPORTED = "mainsettings/imported.vcfg"
PROFILES = "imported_profiles"


def safe_relative(value):
    value = str(value).replace("\\", "/")
    parts = value.split("/")
    if (not value or any(p in ("", ".", "..") for p in parts)
            or any(c in value for c in ':";\r\n\0') or value.startswith("/")):
        raise ValueError("Use a relative config folder or file name.")
    return value


def linked(path):
    """Windows junctions are reparse points too, not always Python symlinks."""
    try:
        return path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & 0x400)
    except FileNotFoundError:
        return False


def storage(account, folder="mrwhiteer"):
    key = hashlib.sha256(str(account or "local").encode()).hexdigest()[:16]
    return user_data_dir() / "generated" / key / "cfg" / safe_relative(folder)


def write_changed(root, files, note):
    """Back up *all* changed destinations before the first replacement."""
    changed = []
    for relative, text in files.items():
        path = root / safe_relative(relative)
        if linked(path) or any(linked(p) for p in path.parents):
            raise ValueError("Config destinations cannot be links.")
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            changed.append((path, text))
    session = backup.BackupSession(note)
    for path, _ in changed:
        session.add(path)  # failure here means nothing gets overwritten
    for path, text in changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Replace a complete file, never leave a truncated config on failure.
        handle, name = tempfile.mkstemp(prefix=".cs2cfg-", dir=str(path.parent))
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(text)
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    return {"changed": len(changed), "backup": session.stamp if changed else None}


def prepare(account, folder, name, performance, notes):
    folder, name = safe_relative(folder), safe_relative(name)
    root = storage(account, folder)
    pieces = starter._pieces()
    files = {p.relative: p.content for p in pieces if not (root / p.relative).exists()}
    # The app copy is editable too: never reset the player's binds/aliases.
    entry = starter._autoexec_text(folder, pieces)
    entry += f'\nexec "{folder}/{name}"\n'
    if (root / IMPORTED).is_file():
        entry += f'exec "{folder}/{IMPORTED}"\n'
    files.update({starter.AUTOEXEC: entry, name: performance,
                  "launch_options_generated.txt": notes})
    result = write_changed(root, files, "prepare app configs")
    result.update(root=str(root), files=sorted(p.relative_to(root).as_posix()
                  for p in root.rglob("*") if p.is_file()))
    return result


def install(root, cfg_root, folder):
    """Add missing starter files; refresh generated files; preserve user files.

    Existing autoexecs receive only missing exec links. This never replaces an
    existing personal layout with the app's empty template.
    """
    folder = safe_relative(folder)
    target = Path(cfg_root) / folder
    files = {}
    manifest = Path(root) / "_installed.json"
    previous = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
    if previous.get("target") != str(target.resolve()):
        previous = {}
    hashes, preserved = {}, []
    templates = {p.relative for p in starter._pieces()} | {starter.AUTOEXEC}
    for path in Path(root).rglob("*"):
        if not path.is_file() or path.name.startswith("_"):
            continue
        relative = path.relative_to(root).as_posix()
        if relative in templates and (target / relative).exists():
            continue
        text = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(text.encode()).hexdigest()
        before = previous.get("files", {}).get(relative)
        imported = relative == IMPORTED or relative.startswith(PROFILES + "/")
        if imported and before == digest and (target / relative).is_file():
            current = (target / relative).read_text(encoding="utf-8")
            if hashlib.sha256(current.encode()).hexdigest() != before:
                preserved.append(relative)
                hashes[relative] = before
                continue  # keep Keyboard/Settings edits made since installation
        files[relative] = text
        hashes[relative] = digest
    entry = target / starter.AUTOEXEC
    if entry.is_file():
        text = entry.read_text(encoding="utf-8")
        existing = {cfglang.normalise_exec_path(c.arg_text(0))
                    for c in cfglang.parse(text).commands() if c.lname in ("exec", "execifexists")}
        # Follow the prepared load order, independent of filesystem traversal.
        app_entry = (Path(root) / starter.AUTOEXEC).read_text(encoding="utf-8")
        for command in cfglang.parse(app_entry).commands():
            if command.lname != "exec":
                continue
            link = command.arg_text(0)
            relative = link.removeprefix(folder + "/")
            if relative in files and cfglang.normalise_exec_path(link) not in existing:
                text += f'\nexec "{link}"\n'
        files[starter.AUTOEXEC] = text
    source_list = Path(root) / "_import_sources.json"
    sources = json.loads(source_list.read_text(encoding="utf-8")) if source_list.exists() else []
    if any(str((target / rel).resolve()).casefold() in sources for rel in files):
        raise ValueError("Original files are in the destination. Your rebuilt copy stays in the app.")
    result = write_changed(target, files, "install ready configs")
    write_changed(Path(root), {"_installed.json": json.dumps({"target": str(target.resolve()), "files": hashes}, sort_keys=True)}, "config installation record")
    result["preserved"] = preserved
    return result


def snapshot(paths, folder=False):
    """Read only chosen scope, never follow links or external exec targets."""
    chosen = [Path(p).absolute() for p in paths]
    if not chosen:
        raise ValueError("Choose a config file or folder.")
    base = chosen[0] if folder else Path(os.path.commonpath([str(p.parent) for p in chosen]))
    # Use the scanner's cfg-relative resolution when the selected scope is in cfg/.
    cfg_root = cfgscan.find_cfg_root(base)
    candidates = base.rglob("*") if folder else chosen
    texts, total = {}, 0
    for index, path in enumerate(candidates):
        if index >= 10000:
            raise ValueError("Choose a smaller config folder (up to 10,000 entries).")
        if linked(path) or any(linked(p) for p in path.parents):
            raise ValueError("Choose original files rather than linked folders.")
        if not path.is_file() or path.suffix.lower() not in cfgscan.CONFIG_SUFFIXES:
            continue
        relative = safe_relative(path.relative_to(cfg_root).as_posix())
        size = path.stat().st_size
        if len(texts) >= MAX_FILES or total + size > MAX_BYTES:
            raise ValueError("Choose a smaller set (up to 256 files / 4 MiB).")
        raw = path.read_bytes()
        total += len(raw)
        if total > MAX_BYTES:
            raise ValueError("Choose a smaller set (up to 4 MiB).")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1252", errors="replace")
        texts[relative] = text
    if not texts:
        raise ValueError("No .cfg or .vcfg files found.")
    return texts


def rebuild(texts, entries, folder="mrwhiteer"):
    """Flatten explicitly chosen entry points in their exact execution order.

    No sorting/deduplication of commands: later overrides still win. Deferred
    execs retain their timing and point into an isolated, copied profile graph.
    Only immediate entry execs are flattened. Invalid/missing links are reported.
    Unknown console commands are kept; nothing is ever executed here.
    """
    folder = safe_relative(folder)
    if len(texts) > MAX_FILES or sum(len(t.encode("utf-8")) for t in texts.values()) > MAX_BYTES:
        raise ValueError("Choose a smaller set (up to 256 files / 4 MiB).")
    if not entries or len(entries) > MAX_FILES or any(not isinstance(e, str) or e not in texts for e in entries):
        raise ValueError("Choose at least one listed file to load.")
    with tempfile.TemporaryDirectory(prefix="cs2cfg-import-") as tmp:
        root = Path(tmp)
        for relative, text in texts.items():
            path = root / safe_relative(relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        scanner = cfgscan.Scanner(root, root)  # same scanner as Configuration studio
        scanned = scanner.scan()
        # Inspect layout definitions through the same backend as Keyboard.
        layout_count = len(cfgscan.layout_profiles(scanned))
    def resolve(name):
        return scanner._resolve(name)  # includes its unambiguous collection-tail fallback
    out, report, visited = [], [], set()
    kept, merged, dropped, expanded, rewritten_count = 0, 0, 0, 0, 0
    profile_paths, profile_files, pending, immediate_edges = {}, {}, [], {}
    definitions, bindings = {}, []

    def drop(file, line, reason):
        nonlocal dropped
        dropped += 1
        report.append({"kind": "dropped", "file": file, "line": line, "reason": reason})

    def profile_path(config):
        if any(c.isspace() for c in folder):
            raise ValueError("Runtime profile links need a config folder without spaces or tabs.")
        if config.relative not in profile_paths:
            # A safe readable name plus source identity avoids basename, case,
            # punctuation and file/directory collisions in the copied tree.
            stem = re.sub(r"[^a-zA-Z0-9_-]", "_", Path(config.relative).stem)[:32] or "profile"
            digest = hashlib.sha256(config.relative.encode()).hexdigest()[:12]
            name = f"{PROFILES}/{stem}-{digest}.cfg"
            suffix = 0
            used = {p.casefold() for p in profile_paths.values()}
            while name.casefold() in used:
                suffix += 1
                name = f"{PROFILES}/{stem}-{digest}-{suffix}.cfg"
            profile_paths[config.relative] = name
            pending.append(config)
        return f"{folder}/{profile_paths[config.relative]}"

    def reaches(start, end):
        todo, seen = [start], set()
        while todo:
            node = todo.pop()
            if node == end:
                return True
            if node not in seen:
                seen.add(node)
                todo.extend(immediate_edges.get(node, ()))
        return False

    def rewrite(command, file, line, context=(), depth=0):
        nonlocal rewritten_count
        rewritten_count += 1
        if rewritten_count > 20000:
            raise ValueError("Choose a smaller set (up to 20,000 commands, including deferred bodies).")
        if depth > 16:
            drop(file, line, "Deferred command nesting too deep")
            return None
        if command.lname in cfglang.EXEC_COMMANDS:
            if len(command.args) != 1:
                drop(file, line, "Exec arguments need review in Advanced")
                return None
            target = resolve(command.arg_text(0))
            if target is None:
                drop(file, line, "Exec target missing; choose its folder: " + command.arg_text(0))
                return None
            if not target.is_commands:
                drop(file, line, "Game-owned KeyValues file: " + target.relative)
                return None
            if not context:
                # Deferred switches may return to a profile on a later keypress.
                # Only an immediate exec cycle would recurse at runtime.
                if reaches(target.relative, file):
                    drop(file, line, "Exec loop in copied profiles: " + target.relative)
                    return None
                immediate_edges.setdefault(file, set()).add(target.relative)
            destination = profile_path(target)
            report.append({"kind": "profile", "file": file, "line": line,
                           "binding": " → ".join(context) or "exec",
                           "source": target.relative, "target": destination,
                           "reason": "Copied profile; runs when its exec is called"})
            # Bare paths inside a quoted bind/alias body avoid nested quotes,
            # which Source's console language does not escape.
            return cfglang.render_command(replace(command, tokens=[command.tokens[0],
                replace(command.args[0], text=destination, quoted=not context)]))
        if command.lname in cfglang.DEFERRING and len(command.args) >= 2:
            body = cfglang.tokenize_line(command.arg_text(1))
            if body.issues:
                drop(file, line, "Deferred syntax needs review in Advanced")
                return None
            label = command.lname + " " + command.arg_text(0)
            rewritten = [rewrite(c, file, line, context + (label,), depth + 1) for c in body.commands]
            value = "; ".join(c for c in rewritten if c is not None)
            if any(c is None for c in rewritten) or value != cfglang.render_commands(body.commands):
                tokens = list(command.tokens)
                tokens[2] = replace(tokens[2], text=value, quoted=True)
                command = replace(command, tokens=tokens)
        return cfglang.render_command(command)

    def keep(command, file, line, output):
        nonlocal kept
        rendered = rewrite(command, file, line)
        if rendered is None:
            return
        output.append(rendered)
        kept += 1
        if kept > 20000:
            raise ValueError("Choose a smaller set (up to 20,000 commands).")
        parsed = cfglang.parse_command_string(rendered)[0]
        if parsed.lname == "alias":
            definitions.setdefault(parsed.arg_text(0).lower(), []).append(parsed.arg_text(1))
        elif parsed.lname in ("bind", "bindtoggle"):
            bindings.append((file, line, parsed))

    def visit(relative, stack):
        nonlocal merged, expanded
        expanded += 1
        if expanded > 1024:
            raise ValueError("Too many repeated exec links. Choose a smaller set.")
        config = resolve(relative)
        if config is None:
            drop(relative, 0, "File not selected or missing")
            return
        if config.relative in stack or len(stack) >= 32:
            drop(config.relative, 0, "Exec loop or too deep")
            return
        if not config.is_commands:
            drop(config.relative, 0, "Game-owned KeyValues file")
            return
        visited.add(config.relative)
        out.append("// From " + config.relative)
        for line in config.document.lines:
            if line.issues or any(ord(c) < 32 and c != "\t" for c in line.raw):
                drop(config.relative, line.number, "Syntax needs review in Advanced")
                continue
            if not line.commands:
                out.append(line.raw)
            for command in line.commands:
                if command.lname in ("exec", "execifexists"):
                    if len(command.args) != 1:
                        drop(config.relative, line.number, "Exec arguments need review in Advanced")
                        continue
                    dest = command.arg_text(0)
                    target = resolve(dest)
                    if target:
                        merged += 1
                        visit(target.relative, stack + [config.relative])
                    else:
                        drop(config.relative, line.number, "Exec target missing; choose its folder")
                else:
                    keep(command, config.relative, line.number, out)

    for entry in entries:
        visit(entry, [])
    # Queue each copied source once, including deferred cycles. Never promote
    # these commands to the startup stream or read outside the snapshot.
    for config in pending:
        visited.add(config.relative)
        copied = ["// Copied profile from " + config.relative]
        for line in config.document.lines:
            if line.issues or any(ord(c) < 32 and c != "\t" for c in line.raw):
                drop(config.relative, line.number, "Syntax needs review in Advanced")
                continue
            if not line.commands:
                copied.append(line.raw)
            for command in line.commands:
                keep(command, config.relative, line.number, copied)
        profile_files[profile_paths[config.relative]] = "\n".join(copied) + "\n"

    # Explain indirect binds too, without executing aliases or following alias
    # cycles. Multiple definitions describe possible runtime targets.
    alias_links = 0
    for file, line, binding in bindings:
        todo = [(c, ()) for c in cfglang.parse_command_string(binding.arg_text(1))]
        seen, targets = set(), set()
        while todo:
            alias_links += 1
            if alias_links > 20000:
                raise ValueError("Too many repeated alias links. Choose a smaller set.")
            command, chain = todo.pop()
            if command.lname in cfglang.EXEC_COMMANDS and chain:
                targets.add((command.arg_text(0), chain))
            elif command.lname in definitions and command.lname not in seen:
                seen.add(command.lname)
                for body in definitions[command.lname]:
                    todo.extend((c, chain + (command.name,)) for c in cfglang.parse_command_string(body))
        for target, chain in sorted(targets):
            report.append({"kind": "profile", "file": file, "line": line,
                           "binding": binding.lname + " " + binding.arg_text(0) + " → " + " → ".join(chain),
                           "target": target, "reason": "Copied profile via alias chain"})
    text = "\n".join(out) + "\n"
    polished = cfgformat.polish(text, IMPORTED)
    if polished.safe:
        text = polished.formatted
    return {"text": text, "kept": kept, "merged": merged, "dropped": dropped,
            "profile_files": profile_files, "profiles": len(profile_files),
            "files": len(visited), "layouts": layout_count, "details": report,
            "note": "Order and later overrides kept. Originals stay untouched."}
