"""The native file and folder pickers, in their modern form.

Windows has two folder pickers. The old one -- ``FolderBrowserDialog``, which
.NET Framework still gives you -- is the cramped tree with no search, no
address bar and no Quick access. The modern one is the ordinary Explorer
window with all of that, and it is what people mean when they say "the file
picker". It is reached through ``IFileOpenDialog`` with the pick-folders
option set, which .NET Framework does not expose, so the interface is declared
here and called directly.

The file picker needs none of that: ``OpenFileDialog`` has been the modern
dialog since Vista.

Both run in a separate PowerShell process. A file dialog requires a single
threaded apartment, which the web server's worker threads are not, and running
it elsewhere keeps that requirement from leaking into the rest of the
application. It also means a dialog that hangs cannot take the server with it.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Optional

TIMEOUT = 600.0

# What a configuration is allowed to be, for the file picker's filter.
CONFIG_FILTER = ("CS2 configs (*.vcfg;*.cfg)|*.vcfg;*.cfg"
                 "|All files (*.*)|*.*")


def _literal(value: str) -> str:
    """A PowerShell single-quoted string; the only escape inside one is ''."""
    return "'" + str(value or "").replace("'", "''") + "'"


# The modern dialog, declared because .NET Framework does not offer it.
# IFileOpenDialog is the same object Explorer itself uses, so this is the real
# window -- search, Quick access, address bar, resizable -- not an imitation.
_FOLDER_CSHARP = r'''
using System;
using System.Runtime.InteropServices;

public static class ModernFolderPicker
{
    [ComImport, Guid("42f85136-db7e-439c-85f1-e4075d135fc8"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IFileDialog
    {
        [PreserveSig] int Show(IntPtr parent);
        void SetFileTypes(uint count, IntPtr filters);
        void SetFileTypeIndex(uint index);
        void GetFileTypeIndex(out uint index);
        void Advise(IntPtr sink, out uint cookie);
        void Unadvise(uint cookie);
        void SetOptions(uint options);
        void GetOptions(out uint options);
        void SetDefaultFolder(IShellItem item);
        void SetFolder(IShellItem item);
        void GetFolder(out IShellItem item);
        void GetCurrentSelection(out IShellItem item);
        void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string name);
        void GetFileName([MarshalAs(UnmanagedType.LPWStr)] out string name);
        void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string title);
        void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string text);
        void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string label);
        void GetResult(out IShellItem item);
        void AddPlace(IShellItem item, int alignment);
        void SetDefaultExtension([MarshalAs(UnmanagedType.LPWStr)] string ext);
        void Close(int result);
        void SetClientGuid(ref Guid guid);
        void ClearClientData();
        void SetFilter(IntPtr filter);
    }

    [ComImport, Guid("43826d1e-e718-42ee-bc55-a1e261c37bfe"),
     InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
    private interface IShellItem
    {
        void BindToHandler(IntPtr bc, ref Guid bhid, ref Guid riid, out IntPtr v);
        void GetParent(out IShellItem parent);
        void GetDisplayName(uint sigdn, [MarshalAs(UnmanagedType.LPWStr)] out string name);
        void GetAttributes(uint mask, out uint attributes);
        void Compare(IShellItem other, uint hint, out int order);
    }

    [ComImport, Guid("DC1C5A9C-E88A-4dde-A5A1-60F82A20AEF7")]
    private class FileOpenDialog { }

    [DllImport("shell32.dll", CharSet = CharSet.Unicode, PreserveSig = false)]
    private static extern void SHCreateItemFromParsingName(
        string path, IntPtr bc, ref Guid riid,
        [MarshalAs(UnmanagedType.Interface)] out object item);

    // Pick folders, insist on real filesystem paths, and start where asked
    // rather than wherever the dialog was last left.
    private const uint FOS_PICKFOLDERS     = 0x00000020;
    private const uint FOS_FORCEFILESYSTEM = 0x00000040;
    private const uint SIGDN_FILESYSPATH   = 0x80058000;

    public static string Pick(string title, string start)
    {
        IFileDialog dialog = (IFileDialog)(new FileOpenDialog());
        dialog.SetOptions(FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM);
        if (!String.IsNullOrEmpty(title)) { dialog.SetTitle(title); }

        if (!String.IsNullOrEmpty(start) && System.IO.Directory.Exists(start))
        {
            Guid shellItemId = new Guid("43826d1e-e718-42ee-bc55-a1e261c37bfe");
            object folder;
            try
            {
                SHCreateItemFromParsingName(start, IntPtr.Zero, ref shellItemId, out folder);
                dialog.SetFolder((IShellItem)folder);
            }
            catch (Exception) { /* a start that will not resolve is not fatal */ }
        }

        // S_OK is 0; anything else means it was cancelled or closed.
        if (dialog.Show(IntPtr.Zero) != 0) { return null; }

        IShellItem chosen;
        dialog.GetResult(out chosen);
        string path;
        chosen.GetDisplayName(SIGDN_FILESYSPATH, out path);
        return path;
    }
}
'''


def _run(script: str) -> Optional[str]:
    """Run a dialog script in its own STA process and return what it printed."""
    handle = tempfile.NamedTemporaryFile(
        "w", suffix=".ps1", delete=False, encoding="utf-8")
    try:
        handle.write(script)
        handle.close()
        done = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass",
             "-File", handle.name],
            capture_output=True, text=True, timeout=TIMEOUT,
            stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        try:
            Path(handle.name).unlink()
        except OSError:
            pass

    chosen = (done.stdout or "").strip()
    return chosen or None


def pick_folder(initial: str = "", title: str = "Choose a configuration folder") -> Optional[str]:
    """The Explorer folder picker: search, Quick access, address bar."""
    script = (
        "$ErrorActionPreference = 'Stop'\n"
        "Add-Type -TypeDefinition @'\n" + _FOLDER_CSHARP + "\n'@\n"
        f"$picked = [ModernFolderPicker]::Pick({_literal(title)}, {_literal(initial)})\n"
        "if ($picked) { [Console]::Out.Write($picked) }\n"
    )
    return _run(script)


SETUP_FILTER = "Saved setup (*.cs2setup)|*.cs2setup|All files (*.*)|*.*"


def save_file(suggested: str = "", title: str = "Save",
              filter_spec: str = SETUP_FILTER) -> Optional[str]:
    """Where to write something. Returns a path, or None if nothing was chosen.

    SaveFileDialog does the overwrite question itself, in the words Windows
    already uses for it, which is better than asking again in ours.
    """
    script = (
        "Add-Type -AssemblyName System.Windows.Forms\n"
        "$d = New-Object System.Windows.Forms.SaveFileDialog\n"
        f"$d.Title = {_literal(title)}\n"
        f"$d.Filter = {_literal(filter_spec)}\n"
        f"$d.FileName = {_literal(suggested)}\n"
        "$d.OverwritePrompt = $true\n"
        "$d.RestoreDirectory = $true\n"
        "if ($d.ShowDialog() -eq 'OK') { [Console]::Out.Write($d.FileName) }\n"
    )
    return _run(script)


def pick_file(initial: str = "", title: str = "Choose a configuration file") -> Optional[str]:
    """The Explorer file picker, filtered to configurations.

    OpenFileDialog has been the modern dialog since Vista, so this one needs
    no help.
    """
    script = (
        "Add-Type -AssemblyName System.Windows.Forms\n"
        "$d = New-Object System.Windows.Forms.OpenFileDialog\n"
        f"$d.Title = {_literal(title)}\n"
        f"$d.Filter = {_literal(CONFIG_FILTER)}\n"
        "$d.CheckFileExists = $true\n"
        "$d.Multiselect = $false\n"
        "$d.RestoreDirectory = $true\n"
        f"$start = {_literal(initial)}\n"
        "if ($start) {\n"
        "  if (Test-Path -PathType Container $start) { $d.InitialDirectory = $start }\n"
        "  elseif (Test-Path $start) {\n"
        "    $d.InitialDirectory = Split-Path -Parent $start\n"
        "    $d.FileName = Split-Path -Leaf $start\n"
        "  }\n"
        "}\n"
        "$top = New-Object System.Windows.Forms.Form\n"
        "$top.TopMost = $true\n"
        "if ($d.ShowDialog($top) -eq [System.Windows.Forms.DialogResult]::OK) "
        "{ [Console]::Out.Write($d.FileName) }\n"
        "$top.Dispose(); $d.Dispose()\n"
    )
    return _run(script)
