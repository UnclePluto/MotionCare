import shutil
import subprocess
import sys

import pytest

from pp_mcare.media import SkeletonVideoEncoder, probe_source_video
from pp_mcare.worker import _workspace_tool_paths
from pp_mcare.workspace import TaskWorkspace


@pytest.mark.skipif(sys.platform != "linux", reason="Production uses Linux procfs")
def test_worker_workspace_paths_support_real_media_subprocesses(tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("Real FFmpeg tools required")
    import numpy as np

    with TaskWorkspace.create(tmp_path, 42) as workspace:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
             "color=c=black:s=64x64:r=25", "-t", "1", "-c:v", "libx264",
             str(workspace.input_path)],
            check=True,
        )
        input_path, output_path = _workspace_tool_paths(workspace)
        assert probe_source_video(input_path).frame_count == 25
        encoder = SkeletonVideoEncoder(output_path, width=64, height=64, fps=25)
        try:
            for _ in range(25):
                encoder.write(np.zeros((64, 64, 3), dtype=np.uint8))
            assert encoder.finish().frame_count == 25
            encoder.commit()
            assert workspace.output_path.is_file()
        finally:
            encoder.abort()
    assert list(tmp_path.iterdir()) == []
