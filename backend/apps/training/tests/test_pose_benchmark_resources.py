from apps.training.pose_benchmark_resources import (
    ResourceSampler,
    ResourceSnapshot,
    read_linux_resource_snapshot,
)


def test_reads_linux_process_memory_and_swap(tmp_path):
    meminfo = tmp_path / "meminfo"
    statm = tmp_path / "statm"
    meminfo.write_text(
        "MemTotal:       2048000 kB\n"
        "MemAvailable:    512000 kB\n"
        "SwapTotal:      4194304 kB\n"
        "SwapFree:       3145728 kB\n",
        encoding="utf-8",
    )
    statm.write_text("1000 250 0 0 0 0 0\n", encoding="utf-8")

    snapshot = read_linux_resource_snapshot(
        meminfo_path=meminfo,
        statm_path=statm,
        page_size=4096,
    )

    assert snapshot.process_rss_bytes == 250 * 4096
    assert snapshot.system_memory_used_bytes == (2048000 - 512000) * 1024
    assert snapshot.memory_available_bytes == 512000 * 1024
    assert snapshot.swap_used_bytes == (4194304 - 3145728) * 1024
    assert snapshot.swap_free_bytes == 3145728 * 1024


def test_sampler_keeps_peaks_and_lowest_available_values():
    snapshots = iter(
        [
            ResourceSnapshot(100, 500, 900, 10, 990),
            ResourceSnapshot(300, 700, 600, 40, 960),
            ResourceSnapshot(200, 650, 750, 20, 980),
        ]
    )
    sampler = ResourceSampler(reader=lambda: next(snapshots), interval_seconds=60)

    sampler.sample_once()
    sampler.sample_once()
    sampler.sample_once()

    assert sampler.peak == ResourceSnapshot(300, 700, 600, 40, 960)
