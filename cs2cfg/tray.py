"""A notification-area icon, so closing the window does not stop the app.

Pressing X on a launcher that is watching a game, holding the desktop mode it
borrowed and waiting to give it back, should not end the launcher. It should
put it out of the way. So the window hides and this keeps the application
present in the notification area, where it can be brought back.

Written against the Win32 API directly rather than with pystray, which would
drag in Pillow -- tens of megabytes into a twenty megabyte download, to draw
one sixteen-pixel icon that is already on disk as a .ico file.

The one rule that matters more than any of it: **if this cannot be set up,
the window must close normally.** An application that refuses to close and has
no icon to close it from is not a minor bug, it is a program somebody has to
open Task Manager to be rid of. Every failure path here returns False and the
caller goes back to closing on X.

The icon owns a thread, because a notification icon needs a window to receive
its clicks and a window needs a message loop to pump them. The loop is this
thread's whole job.
"""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from pathlib import Path
from typing import Callable, Optional

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# --- the Win32 vocabulary this needs ---------------------------------------

NIM_ADD, NIM_MODIFY, NIM_DELETE, NIM_SETVERSION = 0, 1, 2, 4
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO, NIF_SHOWTIP = 0x01, 0x02, 0x04, 0x10, 0x80
NOTIFYICON_VERSION_4 = 4
NIIF_NONE, NIIF_INFO, NIIF_USER, NIIF_LARGE_ICON = 0x00, 0x01, 0x04, 0x20

# Which icon Windows wants, measured rather than assumed: a notification area
# icon is the small metric, a balloon's own icon is the large one. They differ
# with the display's scaling, so neither is hardcoded.
SM_CXICON, SM_CYICON, SM_CXSMICON, SM_CYSMICON = 11, 12, 49, 50

WM_DESTROY, WM_COMMAND, WM_CLOSE, WM_NULL = 0x0002, 0x0111, 0x0010, 0x0000
WM_LBUTTONUP, WM_CONTEXTMENU, WM_RBUTTONUP = 0x0202, 0x007B, 0x0205
WM_APP = 0x8000
TRAY_MESSAGE = WM_APP + 17
NIN_SELECT = 0x0400
NIN_KEYSELECT = 0x0401

MF_STRING, MF_SEPARATOR = 0x0000, 0x0800
TPM_RIGHTBUTTON, TPM_RETURNCMD = 0x0002, 0x0100

IMAGE_ICON = 1
LR_LOADFROMFILE, LR_DEFAULTSIZE, LR_SHARED = 0x0010, 0x0040, 0x8000
IDI_APPLICATION = 32512

CS_VREDRAW, CS_HREDRAW = 0x0001, 0x0002
HWND_MESSAGE = wintypes.HWND(-3)

ID_OPEN, ID_QUIT = 1001, 1002

WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_byte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD), ("pt", POINT)]


# Every handle crossing this boundary is declared, in both directions.
#
# ctypes assumes a 32-bit int for anything undeclared, and a handle on 64-bit
# Windows is 64 bits. Undeclared *returns* are silently truncated, which works
# for as long as the handles happen to be small and then does not; undeclared
# *arguments* raise outright once a handle is genuinely large, which is how
# this was found. Both halves have to be said.
UINT_PTR = ctypes.c_size_t

kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]

user32.DefWindowProcW.restype = ctypes.c_long
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                  wintypes.WPARAM, wintypes.LPARAM]
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.LoadImageW.restype = wintypes.HANDLE
user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                              ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.LoadIconW.restype = wintypes.HICON
user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.CreatePopupMenu.argtypes = []
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, UINT_PTR,
                               wintypes.LPCWSTR]
user32.TrackPopupMenu.restype = ctypes.c_int
user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                  wintypes.LPVOID]
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                wintypes.WPARAM, wintypes.LPARAM]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.c_void_p]


class Tray:
    """One notification-area icon, on its own thread."""

    def __init__(self, title: str, icon: Optional[Path],
                 on_open: Callable[[], None], on_quit: Callable[[], None]) -> None:
        self.title = title
        self.icon_path = icon
        self.on_open = on_open
        self.on_quit = on_quit

        self._hwnd: Optional[int] = None
        self._hicon = None            # small: the icon in the tray itself
        self._hicon_large = None      # large: the icon on the balloon
        self._ready = threading.Event()
        self._ok = False
        self._thread: Optional[threading.Thread] = None
        # Held as an attribute, not a local: a WNDPROC that gets collected
        # while Windows still has the pointer is a crash in somebody else's
        # stack trace, and a confusing one.
        self._proc = WNDPROC(self._dispatch)
        self._class = None

    # -- lifecycle ---------------------------------------------------------

    def start(self, timeout: float = 5.0) -> bool:
        """Put the icon in the tray. False if that did not work, for any
        reason at all -- the caller then leaves X closing the window."""
        self._thread = threading.Thread(target=self._run, name="cs2cfg-tray",
                                        daemon=True)
        self._thread.start()
        self._ready.wait(timeout)
        return self._ok

    def stop(self) -> None:
        if self._hwnd:
            try:
                self._remove()
                user32.PostMessageW(wintypes.HWND(self._hwnd), WM_DESTROY, 0, 0)
            except Exception:
                pass

    # -- the thread --------------------------------------------------------

    def _run(self) -> None:
        try:
            self._make_window()
            self._load_icon()
            self._add()
            self._ok = True
        except Exception:
            self._ok = False
            self._ready.set()
            return
        self._ready.set()

        message = MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))

    def _make_window(self) -> None:
        instance = kernel32.GetModuleHandleW(None)
        name = f"cs2cfg-tray-{id(self)}"
        cls = WNDCLASSW()
        cls.style = CS_VREDRAW | CS_HREDRAW
        cls.lpfnWndProc = self._proc
        cls.hInstance = instance
        cls.lpszClassName = name
        if not user32.RegisterClassW(ctypes.byref(cls)):
            raise OSError(f"RegisterClassW failed ({ctypes.get_last_error()})")
        self._class = cls          # keep it alive alongside the proc

        # Message-only: it exists to receive the icon's clicks and must never
        # appear anywhere itself.
        hwnd = user32.CreateWindowExW(0, name, name, 0, 0, 0, 0, 0,
                                      HWND_MESSAGE, None, instance, None)
        if not hwnd:
            raise OSError(f"CreateWindowExW failed ({ctypes.get_last_error()})")
        self._hwnd = hwnd

    def _load_icon(self) -> None:
        """Load the mark twice, at the two sizes Windows asks for.

        Loading it once at the default size -- which is the large one -- and
        using that for both is what the first version did, and it was wrong
        twice over. The tray then showed a 32 px icon squashed into 16, which
        is the difference between a crisp mark and a smudge; and the balloon
        refused it outright with "incorrect size argument", so every
        notification fell back to the generic blue information icon.
        """
        if self.icon_path and Path(self.icon_path).exists():
            path = str(self.icon_path)
            self._hicon = user32.LoadImageW(
                None, path, IMAGE_ICON, user32.GetSystemMetrics(SM_CXSMICON),
                user32.GetSystemMetrics(SM_CYSMICON), LR_LOADFROMFILE)
            self._hicon_large = user32.LoadImageW(
                None, path, IMAGE_ICON, user32.GetSystemMetrics(SM_CXICON),
                user32.GetSystemMetrics(SM_CYICON), LR_LOADFROMFILE)
            if self._hicon:
                return
        # Better a generic icon than no icon: no icon means no way back.
        self._hicon = user32.LoadIconW(None, wintypes.LPCWSTR(IDI_APPLICATION))

    def _data(self, flags: int) -> NOTIFYICONDATAW:
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self._hwnd
        data.uID = 1
        data.uFlags = flags
        data.uCallbackMessage = TRAY_MESSAGE
        if self._hicon:
            data.hIcon = self._hicon
        data.szTip = self.title[:127]
        return data

    def _add(self) -> None:
        data = self._data(NIF_MESSAGE | NIF_ICON | NIF_TIP | NIF_SHOWTIP)
        if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data)):
            raise OSError("Shell_NotifyIconW(NIM_ADD) failed")
        version = self._data(0)
        version.uVersion = NOTIFYICON_VERSION_4
        shell32.Shell_NotifyIconW(NIM_SETVERSION, ctypes.byref(version))

    def _remove(self) -> None:
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self._hwnd
        data.uID = 1
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(data))

    # -- behaviour ---------------------------------------------------------

    def notify(self, title: str, body: str) -> bool:
        """The balloon in the corner. Never worth failing over."""
        if not self._ok or not self._hwnd:
            return False
        try:
            # Windows is particular about which icon goes with which flag,
            # and says only "incorrect size argument" when it is not happy.
            # NIIF_USER on its own wants the small icon; the large one needs
            # NIIF_LARGE_ICON to go with it. The large pairing is tried first
            # because it is the one that fills the notification properly, and
            # the plain information icon is the last resort rather than the
            # first -- getting that order wrong is why every notification
            # showed a generic blue "i" instead of the application's mark.
            attempts = (
                (NIIF_USER | NIIF_LARGE_ICON, self._hicon_large),
                (NIIF_USER, self._hicon),
                (NIIF_INFO, None),
            )
            for flags, balloon in attempts:
                if flags != NIIF_INFO and not balloon:
                    continue
                data = self._data(NIF_INFO | NIF_ICON | NIF_TIP)
                data.szInfoTitle = title[:63]
                data.szInfo = body[:255]
                data.dwInfoFlags = flags
                if balloon:
                    data.hBalloonIcon = balloon
                if shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(data)):
                    return True
            return False
        except Exception:
            return False

    def _menu(self) -> None:
        menu = user32.CreatePopupMenu()
        if not menu:
            return
        try:
            user32.AppendMenuW(menu, MF_STRING, ID_OPEN, f"Open {self.title}")
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, ID_QUIT, "Quit")
            point = POINT()
            user32.GetCursorPos(ctypes.byref(point))
            # Without this the menu will not close when clicked away from --
            # a documented quirk of popup menus owned by a background window.
            user32.SetForegroundWindow(wintypes.HWND(self._hwnd))
            chosen = user32.TrackPopupMenu(
                menu, TPM_RIGHTBUTTON | TPM_RETURNCMD, point.x, point.y,
                0, wintypes.HWND(self._hwnd), None)
            user32.PostMessageW(wintypes.HWND(self._hwnd), WM_NULL, 0, 0)
            if chosen == ID_OPEN:
                self._safely(self.on_open)
            elif chosen == ID_QUIT:
                self._safely(self.on_quit)
        finally:
            user32.DestroyMenu(menu)

    @staticmethod
    def _safely(action: Callable[[], None]) -> None:
        """A callback that raises must not take the message loop with it: the
        loop is the only way back to the window."""
        try:
            action()
        except Exception:
            pass

    def _dispatch(self, hwnd, message, wparam, lparam):
        if message == TRAY_MESSAGE:
            event = lparam & 0xFFFF
            if event in (NIN_SELECT, NIN_KEYSELECT, WM_LBUTTONUP):
                self._safely(self.on_open)
            elif event in (WM_CONTEXTMENU, WM_RBUTTONUP):
                self._menu()
            return 0
        if message == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(wintypes.HWND(hwnd), message,
                                     wintypes.WPARAM(wparam),
                                     wintypes.LPARAM(lparam))
