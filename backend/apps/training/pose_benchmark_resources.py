import os
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResourceSnapshot:
    process_rss_bytes: int
    system_memory_used_bytes: int
    memory_available_bytes: int
    swap_used_bytes: int
    swap_free_bytes: int


def _read_meminfo(path):
    values = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        key, raw_value = line.split(":", 1)
        values[key] = int(raw_value.strip().split()[0]) * 1024
    required = ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree")
    if any(key not in values for key in required):
        raise RuntimeError("/proc/meminfo 缺少必要字段")
    return values


def read_linux_resource_snapshot(
    *,
    meminfo_path=Path("/proc/meminfo"),
    statm_path=Path("/proc/self/statm"),
    page_size=None,
):
    memory = _read_meminfo(meminfo_path)
    fields = Path(statm_path).read_text(encoding="utf-8").split()
    if len(fields) < 2:
        raise RuntimeError("/proc/self/statm 格式无效")
    resident_pages = int(fields[1])
    resolved_page_size = page_size or os.sysconf("SC_PAGE_SIZE")
    return ResourceSnapshot(
        process_rss_bytes=resident_pages * resolved_page_size,
        system_memory_used_bytes=memory["MemTotal"] - memory["MemAvailable"],
        memory_available_bytes=memory["MemAvailable"],
        swap_used_bytes=memory["SwapTotal"] - memory["SwapFree"],
        swap_free_bytes=memory["SwapFree"],
    )


class ResourceSampler:
    def __init__(self, *, reader=read_linux_resource_snapshot, interval_seconds=0.5):
        self._reader = reader
        self._interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread = None
        self.peak = None

    def sample_once(self):
        current = self._reader()
        if self.peak is None:
            self.peak = current
        else:
            self.peak = ResourceSnapshot(
                process_rss_bytes=max(self.peak.process_rss_bytes, current.process_rss_bytes),
                system_memory_used_bytes=max(
                    self.peak.system_memory_used_bytes,
                    current.system_memory_used_bytes,
                ),
                memory_available_bytes=min(
                    self.peak.memory_available_bytes,
                    current.memory_available_bytes,
                ),
                swap_used_bytes=max(self.peak.swap_used_bytes, current.swap_used_bytes),
                swap_free_bytes=min(self.peak.swap_free_bytes, current.swap_free_bytes),
            )
        return current

    def _run(self):
        while not self._stop.wait(self._interval_seconds):
            self.sample_once()

    def __enter__(self):
        self.sample_once()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self._interval_seconds * 2))
        self.sample_once()
