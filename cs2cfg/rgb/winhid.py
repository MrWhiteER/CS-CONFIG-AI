"""Just enough of Windows' HID API to send feature reports, through ctypes.

Used to set lighting straight on a USB device, with no vendor software
running. A device is opened with no read or write access: Windows keeps
keyboards and mice to itself for input, but still lets anyone send and read
*feature* reports on a handle opened that way, so no administrator is needed
and typing is never touched.

Import-safe everywhere; on anything but Windows ``devices()`` returns [].
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import POINTER, byref, c_void_p, sizeof
from dataclasses import dataclass
from typing import List, Optional

IS_WINDOWS = sys.platform == "win32"


@dataclass
class HidInfo:
    path: str
    vendor_id: int
    product_id: int
    usage_page: int
    usage: int
    feature_len: int


if IS_WINDOWS:
    from ctypes import wintypes

    _hid = ctypes.WinDLL("hid", use_last_error=True)
    _setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class _GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    class _SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("InterfaceClassGuid", _GUID),
                    ("Flags", wintypes.DWORD), ("Reserved", ctypes.c_size_t)]

    class _HIDD_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Size", wintypes.ULONG), ("VendorID", wintypes.USHORT),
                    ("ProductID", wintypes.USHORT), ("VersionNumber", wintypes.USHORT)]

    class _HIDP_CAPS(ctypes.Structure):
        _fields_ = [("Usage", wintypes.USHORT), ("UsagePage", wintypes.USHORT),
                    ("InputReportByteLength", wintypes.USHORT),
                    ("OutputReportByteLength", wintypes.USHORT),
                    ("FeatureReportByteLength", wintypes.USHORT),
                    ("Reserved", wintypes.USHORT * 17),
                    ("NumberLinkCollectionNodes", wintypes.USHORT),
                    ("NumberInputButtonCaps", wintypes.USHORT),
                    ("NumberInputValueCaps", wintypes.USHORT),
                    ("NumberInputDataIndices", wintypes.USHORT),
                    ("NumberOutputButtonCaps", wintypes.USHORT),
                    ("NumberOutputValueCaps", wintypes.USHORT),
                    ("NumberOutputDataIndices", wintypes.USHORT),
                    ("NumberFeatureButtonCaps", wintypes.USHORT),
                    ("NumberFeatureValueCaps", wintypes.USHORT),
                    ("NumberFeatureDataIndices", wintypes.USHORT)]

    _setupapi.SetupDiGetClassDevsW.restype = c_void_p
    _setupapi.SetupDiGetClassDevsW.argtypes = [POINTER(_GUID), wintypes.LPCWSTR,
                                               wintypes.HWND, wintypes.DWORD]
    _setupapi.SetupDiEnumDeviceInterfaces.argtypes = [
        c_void_p, c_void_p, POINTER(_GUID), wintypes.DWORD,
        POINTER(_SP_DEVICE_INTERFACE_DATA)]
    _setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [
        c_void_p, POINTER(_SP_DEVICE_INTERFACE_DATA), c_void_p, wintypes.DWORD,
        POINTER(wintypes.DWORD), c_void_p]
    _setupapi.SetupDiDestroyDeviceInfoList.argtypes = [c_void_p]
    _kernel32.CreateFileW.restype = c_void_p
    _kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      c_void_p, wintypes.DWORD, wintypes.DWORD, c_void_p]
    _kernel32.CloseHandle.argtypes = [c_void_p]
    _hid.HidD_GetHidGuid.argtypes = [POINTER(_GUID)]
    _hid.HidD_GetAttributes.argtypes = [c_void_p, POINTER(_HIDD_ATTRIBUTES)]
    _hid.HidD_GetPreparsedData.argtypes = [c_void_p, POINTER(c_void_p)]
    _hid.HidD_FreePreparsedData.argtypes = [c_void_p]
    _hid.HidP_GetCaps.argtypes = [c_void_p, POINTER(_HIDP_CAPS)]
    _hid.HidD_SetFeature.argtypes = [c_void_p, c_void_p, wintypes.ULONG]
    _hid.HidD_GetFeature.argtypes = [c_void_p, c_void_p, wintypes.ULONG]

    _INVALID = c_void_p(-1).value
    _DIGCF_PRESENT, _DIGCF_DEVICEINTERFACE = 0x02, 0x10
    _SHARE_RW, _OPEN_EXISTING = 0x01 | 0x02, 3


def _open(path: str) -> Optional[int]:
    # Access 0: feature reports only. Never asks Windows for the input stream.
    h = _kernel32.CreateFileW(path, 0, _SHARE_RW, None, _OPEN_EXISTING, 0, None)
    return None if h in (None, _INVALID) else h


def devices(vendor_id: Optional[int] = None) -> List[HidInfo]:
    """Every present HID collection (optionally of one vendor). Reads only."""
    if not IS_WINDOWS:
        return []
    guid = _GUID()
    _hid.HidD_GetHidGuid(byref(guid))
    info = _setupapi.SetupDiGetClassDevsW(byref(guid), None, None,
                                         _DIGCF_PRESENT | _DIGCF_DEVICEINTERFACE)
    if info in (None, _INVALID):
        return []
    out: List[HidInfo] = []
    try:
        index = 0
        while True:
            iface = _SP_DEVICE_INTERFACE_DATA()
            iface.cbSize = sizeof(_SP_DEVICE_INTERFACE_DATA)
            if not _setupapi.SetupDiEnumDeviceInterfaces(info, None, byref(guid), index,
                                                         byref(iface)):
                break
            index += 1
            needed = wintypes.DWORD()
            _setupapi.SetupDiGetDeviceInterfaceDetailW(info, byref(iface), None, 0,
                                                      byref(needed), None)
            buf = ctypes.create_string_buffer(needed.value)
            # cbSize of SP_DEVICE_INTERFACE_DETAIL_DATA_W: 8 on 64-bit, 6 on 32-bit.
            ctypes.c_uint32.from_buffer(buf).value = 8 if sizeof(c_void_p) == 8 else 6
            if not _setupapi.SetupDiGetDeviceInterfaceDetailW(
                    info, byref(iface), buf, needed, None, None):
                continue
            path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
            found = _describe(path)
            if found and (vendor_id is None or found.vendor_id == vendor_id):
                out.append(found)
    finally:
        _setupapi.SetupDiDestroyDeviceInfoList(info)
    return out


def _describe(path: str) -> Optional[HidInfo]:
    h = _open(path)
    if h is None:
        return None
    try:
        attrs = _HIDD_ATTRIBUTES()
        attrs.Size = sizeof(_HIDD_ATTRIBUTES)
        if not _hid.HidD_GetAttributes(h, byref(attrs)):
            return None
        pre = c_void_p()
        caps = _HIDP_CAPS()
        if _hid.HidD_GetPreparsedData(h, byref(pre)):
            try:
                _hid.HidP_GetCaps(pre, byref(caps))
            finally:
                _hid.HidD_FreePreparsedData(pre)
        return HidInfo(path, attrs.VendorID, attrs.ProductID, caps.UsagePage,
                       caps.Usage, caps.FeatureReportByteLength)
    finally:
        _kernel32.CloseHandle(h)


class Handle:
    """An open device, for feature reports only."""

    def __init__(self, path: str) -> None:
        if not IS_WINDOWS:
            raise OSError("HID is only available on Windows")
        self.h = _open(path)
        if self.h is None:
            raise OSError(f"could not open {path} (error {ctypes.get_last_error()})")

    def set_feature(self, data: bytes) -> None:
        buf = ctypes.create_string_buffer(bytes(data), len(data))
        if not _hid.HidD_SetFeature(self.h, buf, len(data)):
            raise OSError(f"HidD_SetFeature failed (error {ctypes.get_last_error()})")

    def get_feature(self, length: int, report_id: int = 0) -> bytes:
        buf = ctypes.create_string_buffer(bytes([report_id]) + b"\0" * (length - 1), length)
        if not _hid.HidD_GetFeature(self.h, buf, length):
            raise OSError(f"HidD_GetFeature failed (error {ctypes.get_last_error()})")
        return buf.raw

    def close(self) -> None:
        if self.h is not None:
            _kernel32.CloseHandle(self.h)
            self.h = None
