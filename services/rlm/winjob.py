"""Windows Job Object process confinement for Prime Agent.

Ensures that child processes, REPL runtimes, and inference servers are
terminated when the job handle closes or the parent process exits.
"""

from __future__ import annotations
import sys
import ctypes
from ctypes import wintypes
from typing import Optional

# Win32 Constants
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JobObjectExtendedLimitInformation = 9


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
        ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryLimit", ctypes.c_size_t),
        ("PeakJobMemoryLimit", ctypes.c_size_t),
    ]


class WindowsJobGroup:
    """Manages a Windows Job Object to guarantee child process cleanup."""

    def __init__(self, name: Optional[str] = None):
        self.handle = None
        if sys.platform != "win32":
            return

        kernel32 = ctypes.windll.kernel32
        self.handle = kernel32.CreateJobObjectW(None, name)
        if not self.handle:
            return

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        res = kernel32.SetInformationJobObject(
            self.handle,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info)
        )
        if not res:
            kernel32.CloseHandle(self.handle)
            self.handle = None

    def assign_process(self, pid: int) -> bool:
        """Assigns an OS process by PID to this Job Object."""
        if sys.platform != "win32" or not self.handle:
            return False

        kernel32 = ctypes.windll.kernel32
        PROCESS_SET_QUOTA = 0x0100
        PROCESS_TERMINATE = 0x0001
        h_process = kernel32.OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, False, pid)
        if not h_process:
            return False

        try:
            return bool(kernel32.AssignProcessToJobObject(self.handle, h_process))
        finally:
            kernel32.CloseHandle(h_process)

    def close(self):
        if self.handle:
            ctypes.windll.kernel32.CloseHandle(self.handle)
            self.handle = None
