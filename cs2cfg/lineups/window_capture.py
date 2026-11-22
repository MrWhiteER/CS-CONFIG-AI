"""External GDI capture for player-triggered practice pictures.

No game memory, input, hooks or injection. DirectX may return a blank frame;
that is a capture failure, not a successful cached picture. Foreground window
and process identity must still match after copying. Offline provenance and
GSI readiness must be established by the caller before invoking this backend.
"""
import ctypes
from ctypes import wintypes as w
from pathlib import PureWindowsPath


def rgba_frame(width, height, bgra):
    if (not 1 <= width <= 4096 or not 1 <= height <= 4096
            or len(bgra) != width * height * 4):
        raise ValueError('Picture size is unavailable')
    rgba = bytearray(bgra)
    rgba[0::4], rgba[2::4] = bgra[2::4], bgra[0::4]
    rgba[3::4] = bytes([255]) * (width * height)
    if all(rgba[channel::4] == bytes([rgba[channel]]) * (width * height)
           for channel in range(3)):
        raise ValueError('The game returned a blank picture')
    return width, height, bytes(rgba)


def capture_cs2():
    """Copy the visible CS2 client area only; never focus or activate a window."""
    user = ctypes.WinDLL('user32', use_last_error=True)
    gdi = ctypes.WinDLL('gdi32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)

    def bind(api, name, result, *args):
        fn = getattr(api, name)
        fn.restype, fn.argtypes = result, list(args)
        return fn

    foreground = bind(user, 'GetForegroundWindow', w.HWND)
    iconic = bind(user, 'IsIconic', w.BOOL, w.HWND)
    rect_for = bind(user, 'GetClientRect', w.BOOL, w.HWND, ctypes.POINTER(w.RECT))
    pid_for = bind(user, 'GetWindowThreadProcessId', w.DWORD, w.HWND, ctypes.POINTER(w.DWORD))
    open_process = bind(kernel, 'OpenProcess', w.HANDLE, w.DWORD, w.BOOL, w.DWORD)
    image_name = bind(kernel, 'QueryFullProcessImageNameW', w.BOOL, w.HANDLE,
                      w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD))
    close = bind(kernel, 'CloseHandle', w.BOOL, w.HANDLE)
    get_dc = bind(user, 'GetDC', w.HDC, w.HWND)
    release = bind(user, 'ReleaseDC', ctypes.c_int, w.HWND, w.HDC)
    compatible_dc = bind(gdi, 'CreateCompatibleDC', w.HDC, w.HDC)
    bitmap_for = bind(gdi, 'CreateCompatibleBitmap', w.HANDLE, w.HDC, ctypes.c_int, ctypes.c_int)
    select = bind(gdi, 'SelectObject', w.HANDLE, w.HDC, w.HANDLE)
    delete_object = bind(gdi, 'DeleteObject', w.BOOL, w.HANDLE)
    delete_dc = bind(gdi, 'DeleteDC', w.BOOL, w.HDC)
    blit = bind(gdi, 'BitBlt', w.BOOL, w.HDC, ctypes.c_int, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, w.HDC, ctypes.c_int, ctypes.c_int, w.DWORD)
    bits = bind(gdi, 'GetDIBits', ctypes.c_int, w.HDC, w.HANDLE, w.UINT, w.UINT,
                ctypes.c_void_p, ctypes.c_void_p, w.UINT)

    hwnd = foreground()
    pid = w.DWORD()
    if not hwnd or iconic(hwnd) or not pid_for(hwnd, ctypes.byref(pid)):
        raise OSError('Keep the practice game visible')
    # Limited process query only, exactly as overlay.metrics.GameWindow does.
    process = open_process(0x1000, False, pid.value)
    if not process:
        raise OSError('The practice window is unavailable')
    try:
        name, size = ctypes.create_unicode_buffer(32768), w.DWORD(32768)
        if (not image_name(process, 0, name, ctypes.byref(size))
                or PureWindowsPath(name.value).name.casefold() != 'cs2.exe'):
            raise OSError('Keep the practice game visible')
    finally:
        close(process)
    rect = w.RECT()
    if not rect_for(hwnd, ctypes.byref(rect)):
        raise OSError('The picture size is unavailable')
    width, height = rect.right - rect.left, rect.bottom - rect.top
    if not 1 <= width <= 4096 or not 1 <= height <= 4096:
        raise OSError('The picture size is unavailable')
    source = target = bitmap = old = None
    try:
        source = get_dc(hwnd)
        target = compatible_dc(source) if source else None
        bitmap = bitmap_for(source, width, height) if target else None
        if not bitmap:
            raise OSError('The game picture is unavailable')
        old = select(target, bitmap)
        if not old or old == ctypes.c_void_p(-1).value:
            old = None
            raise OSError('The game picture is unavailable')
        if not blit(target, 0, 0, width, height, source, 0, 0, 0x00CC0020):
            raise OSError('The game picture is unavailable')
        select(target, old)
        old = None
        # BITMAPINFOHEADER, top-down 32-bit uncompressed BGRA.
        import struct
        info = ctypes.create_string_buffer(struct.pack('<IiiHHIIiiII',
            40, width, -height, 1, 32, 0, width*height*4, 0, 0, 0, 0) + bytes(4))
        pixels = ctypes.create_string_buffer(width*height*4)
        if bits(target, bitmap, 0, height, pixels, info, 0) != height:
            raise OSError('The game picture is unavailable')
        current_pid = w.DWORD()
        current_rect = w.RECT()
        if (foreground() != hwnd or iconic(hwnd)
                or not pid_for(hwnd, ctypes.byref(current_pid)) or current_pid.value != pid.value
                or not rect_for(hwnd, ctypes.byref(current_rect))
                or tuple(getattr(current_rect, k) for k in ('left','top','right','bottom'))
                != tuple(getattr(rect, k) for k in ('left','top','right','bottom'))):
            raise OSError('The practice window changed; no picture was saved')
        return rgba_frame(width, height, pixels.raw)
    finally:
        if old and target:
            select(target, old)
        if bitmap:
            delete_object(bitmap)
        if target:
            delete_dc(target)
        if source:
            release(hwnd, source)


def process_started(hwnd):
    """Read process creation time through limited query access; no memory read."""
    if not hwnd:
        return None
    try:
        user, kernel = ctypes.WinDLL('user32'), ctypes.WinDLL('kernel32')
        user.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
        kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        kernel.OpenProcess.restype = w.HANDLE
        kernel.GetProcessTimes.argtypes = [w.HANDLE] + [ctypes.POINTER(w.FILETIME)]*4
        kernel.CloseHandle.argtypes = [w.HANDLE]
        pid = w.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return None
        try:
            times = [w.FILETIME() for _ in range(4)]
            if kernel.GetProcessTimes(handle, *[ctypes.byref(t) for t in times]):
                return ((times[0].dwHighDateTime << 32) + times[0].dwLowDateTime)/10000000 - 11644473600
        finally:
            kernel.CloseHandle(handle)
    except (OSError, AttributeError):
        pass
    return None
