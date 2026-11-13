"""Cifratura dei segreti legata all'utente Windows (DPAPI)."""
from __future__ import annotations

import base64
import ctypes
import sys
from ctypes import wintypes


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.c_void_p)]


def _call(func_name: str, data: bytes) -> bytes:
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = _Blob(len(data), ctypes.cast(buf, ctypes.c_void_p))
    blob_out = _Blob()
    func = getattr(crypt32, func_name)
    ok = func(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out))
    if not ok:
        raise OSError("Operazione DPAPI fallita")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        kernel32.LocalFree(blob_out.pbData)


def protect(text: str) -> str:
    if not text:
        return ""
    raw = text.encode("utf-8")
    if sys.platform != "win32":
        return "b64:" + base64.b64encode(raw).decode()
    return "dpapi:" + base64.b64encode(_call("CryptProtectData", raw)).decode()


def unprotect(token: str) -> str:
    if not token:
        return ""
    scheme, _, payload = token.partition(":")
    raw = base64.b64decode(payload)
    if scheme == "dpapi" and sys.platform == "win32":
        raw = _call("CryptUnprotectData", raw)
    elif scheme != "b64":
        raise ValueError("Formato segreto non riconosciuto")
    return raw.decode("utf-8")
