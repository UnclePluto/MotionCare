import os
import signal
import stat
import subprocess
import time
from pathlib import Path


WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "deploy-production.yml"
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DOCKERFILE = REPOSITORY_ROOT / "backend" / "Dockerfile"
PRODUCTION_COMPOSE = REPOSITORY_ROOT / "deploy" / "docker-compose.prod.yml"
PP_MCARE_CONTROL_PLANE_ENV_SCRIPT = (
    REPOSITORY_ROOT / "deploy" / "configure-pp-mcare-control-plane.sh"
)
PP_MCARE_PYPROJECT = REPOSITORY_ROOT / "services" / "pp_mcare" / "pyproject.toml"


def _build_push_action_inputs() -> list[dict[str, str]]:
    lines = WORKFLOW_PATH.read_text(encoding="utf-8").splitlines()
    action_inputs: list[dict[str, str]] = []
    for index, line in enumerate(lines):
        if line.strip() != "uses: docker/build-push-action@v6":
            continue

        inputs: dict[str, str] = {}
        for candidate in lines[index + 1 :]:
            stripped = candidate.strip()
            if candidate.startswith("      - "):
                break
            if not candidate.startswith("          ") or ":" not in stripped:
                continue
            key, value = stripped.split(":", 1)
            inputs[key] = value.strip()
        action_inputs.append(inputs)
    return action_inputs


def test_acr_application_image_builds_disable_unsupported_provenance_attestations():
    action_inputs = _build_push_action_inputs()

    assert len(action_inputs) == 3
    assert [inputs.get("provenance") for inputs in action_inputs] == [
        "false",
        "false",
        "false",
    ]


def test_verify_job_gates_contract_worker_backend_frontend_and_miniapp_without_models():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    worker_pyproject = PP_MCARE_PYPROJECT.read_text(encoding="utf-8")

    ffmpeg_install = workflow.index("sudo apt-get install -y ffmpeg")
    worker_dev_install = workflow.index("pip install -e './services/pp_mcare[dev]'")
    worker_test = workflow.index(
        "pytest -q packages/motion_analysis_contract/tests services/pp_mcare/tests"
    )
    assert ffmpeg_install < worker_dev_install < worker_test
    assert "packages/motion_analysis_contract" in workflow
    assert "services/pp_mcare" in workflow
    assert "packages/motion_analysis_contract/tests" in workflow
    assert "services/pp_mcare/tests" in workflow
    assert "python manage.py makemigrations --check" in workflow
    assert "npm run test" in workflow
    assert "npm run lint" in workflow
    assert "npm run build:weapp" in workflow
    assert "npm run build:h5" in workflow
    assert "PADDLE_PDX_CACHE_HOME" not in workflow
    assert "pp_mcare[inference]" not in workflow
    assert '"opencv-python-headless==4.10.0.84"' in worker_pyproject
    dev_dependencies = worker_pyproject.split("dev = [", 1)[1]
    assert '"paddlex[cv]' not in dev_dependencies
    assert '"paddlepaddle' not in dev_dependencies


def test_production_workflow_keeps_last_wx_image_when_public_asset_domain_is_missing():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    verify_job, publish_job = workflow.split("  publish:\n", 1)

    assert (
        "TARO_APP_ASSET_BASE_URL: "
        "${{ vars.TARO_APP_ASSET_BASE_URL || "
        "'https://assets.example.invalid/motioncare/static-assets' }}"
    ) in verify_job
    assert "if: ${{ vars.TARO_APP_ASSET_BASE_URL != '' }}" in publish_job
    assert "if: ${{ vars.TARO_APP_ASSET_BASE_URL == '' }}" in publish_job
    assert "WX_FALLBACK_VERSION: ${{ vars.WX_FALLBACK_VERSION }}" in publish_job
    assert '[[ "$WX_FALLBACK_VERSION" =~ ^[0-9a-f]{40}$ ]]' in publish_job
    assert "grep -Eq '^[0-9a-f]{40}$'" not in publish_job
    assert 'docker pull --platform linux/amd64 "${ACR_IMAGE}:wx-${WX_FALLBACK_VERSION}"' in publish_job
    assert 'docker tag "${ACR_IMAGE}:wx-${WX_FALLBACK_VERSION}"' in publish_job
    assert '"${ACR_IMAGE}:wx-${{ github.sha }}"' in publish_job


def test_backend_image_installs_contract_before_backend_without_inference_dependencies():
    dockerfile = BACKEND_DOCKERFILE.read_text(encoding="utf-8")

    contract_copy = dockerfile.index("COPY packages/motion_analysis_contract")
    contract_install = dockerfile.index("pip install", contract_copy)
    backend_copy = dockerfile.index("COPY backend")
    backend_install = dockerfile.index("/app/backend", backend_copy)

    assert contract_copy < contract_install < backend_copy < backend_install
    assert "services/pp_mcare" not in dockerfile
    assert "paddlepaddle" not in dockerfile.lower()
    assert "paddlex" not in dockerfile.lower()
    assert "opencv" not in dockerfile.lower()


def test_production_control_plane_defaults_auto_enqueue_off_and_requires_token_digest():
    compose = PRODUCTION_COMPOSE.read_text(encoding="utf-8")

    assert "PP_MCARE_AUTO_ENQUEUE_ENABLED: ${PP_MCARE_AUTO_ENQUEUE_ENABLED:-false}" in compose
    assert (
        "PP_MCARE_SERVICE_TOKEN_SHA256: "
        "${PP_MCARE_SERVICE_TOKEN_SHA256:?PP_MCARE_SERVICE_TOKEN_SHA256 is required}"
    ) in compose


def test_production_compose_passes_static_asset_settings_and_keeps_video_settings():
    compose = PRODUCTION_COMPOSE.read_text(encoding="utf-8")

    assert (
        "MINIAPP_STATIC_ASSET_BASE_URL: "
        "${MINIAPP_STATIC_ASSET_BASE_URL:-https://cdn.whestsun.com/motioncare/static-assets}"
    ) in compose
    assert (
        "MINIAPP_STATIC_ASSET_URL_TTL_SECONDS: "
        "${MINIAPP_STATIC_ASSET_URL_TTL_SECONDS:-600}"
    ) in compose
    assert "MINIAPP_STATIC_ASSET_RATE_LIMIT_REDIS_URL: *backend-redis-url" in compose
    assert (
        "MINIAPP_STATIC_ASSET_RATE_LIMIT_REQUESTS: "
        "${MINIAPP_STATIC_ASSET_RATE_LIMIT_REQUESTS:-60}"
    ) in compose
    assert (
        "MINIAPP_STATIC_ASSET_RATE_LIMIT_WINDOW_SECONDS: "
        "${MINIAPP_STATIC_ASSET_RATE_LIMIT_WINDOW_SECONDS:-60}"
    ) in compose
    assert "QINIU_DOWNLOAD_DOMAIN: ${QINIU_DOWNLOAD_DOMAIN:-}" in compose
    assert "MOTION_ACTION_VIDEO_DOWNLOAD_DOMAIN:" in compose


def test_control_plane_env_script_atomically_sets_digest_and_keeps_auto_disabled(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_VERSION=old\n"
        "PP_MCARE_SERVICE_TOKEN_SHA256=stale\n"
        "PP_MCARE_AUTO_ENQUEUE_ENABLED=true\n"
        "POSTGRES_DB=motioncare\n",
        encoding="utf-8",
    )
    env_file.chmod(0o600)

    completed = subprocess.run(
        [str(PP_MCARE_CONTROL_PLANE_ENV_SCRIPT)],
        cwd=tmp_path,
        input=f"{'a' * 64}\nfalse\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert env_file.read_text(encoding="utf-8").splitlines() == [
        "APP_VERSION=old",
        "POSTGRES_DB=motioncare",
        f"PP_MCARE_SERVICE_TOKEN_SHA256={'a' * 64}",
        "PP_MCARE_AUTO_ENQUEUE_ENABLED=false",
    ]
    assert stat.S_IMODE(env_file.stat().st_mode) == 0o600


def test_control_plane_env_script_rejects_bad_digest_without_changing_env(tmp_path):
    env_file = tmp_path / ".env"
    original = b"APP_VERSION=old\nPOSTGRES_DB=motioncare\n"
    env_file.write_bytes(original)
    env_file.chmod(0o600)

    completed = subprocess.run(
        [str(PP_MCARE_CONTROL_PLANE_ENV_SCRIPT)],
        cwd=tmp_path,
        input="not-a-sha256\nfalse\n",
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert env_file.read_bytes() == original


def test_control_plane_env_script_rejects_unterminated_extra_input(tmp_path):
    env_file = tmp_path / ".env"
    original = b"APP_VERSION=old\nPOSTGRES_DB=motioncare\n"
    env_file.write_bytes(original)
    env_file.chmod(0o600)

    completed = subprocess.run(
        [str(PP_MCARE_CONTROL_PLANE_ENV_SCRIPT)],
        cwd=tmp_path,
        input=f"{'a' * 64}\nfalse\nunexpected-without-newline",
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert env_file.read_bytes() == original


def test_control_plane_env_script_does_not_replace_env_after_sigterm(tmp_path):
    env_file = tmp_path / ".env"
    original = b"APP_VERSION=old\nPOSTGRES_DB=motioncare\n"
    env_file.write_bytes(original)
    env_file.chmod(0o600)

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    marker = tmp_path / "awk-started"
    fake_awk = fake_bin / "awk"
    fake_awk.write_text(
        "#!/bin/sh\n"
        ': > "$PP_MCARE_TEST_MARKER"\n'
        "sleep 1\n"
        'exec /usr/bin/awk "$@"\n',
        encoding="utf-8",
    )
    fake_awk.chmod(0o755)

    process = subprocess.Popen(
        [str(PP_MCARE_CONTROL_PLANE_ENV_SCRIPT)],
        cwd=tmp_path,
        env={
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "PP_MCARE_TEST_MARKER": str(marker),
        },
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdin is not None
    process.stdin.write(f"{'a' * 64}\nfalse\n")
    process.stdin.close()

    deadline = time.monotonic() + 2
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert marker.exists()

    process.send_signal(signal.SIGTERM)
    returncode = process.wait(timeout=3)

    assert returncode != 0
    assert env_file.read_bytes() == original
    assert list(tmp_path.glob(".env.pp-mcare.*")) == []


def test_control_plane_env_script_rejects_malicious_auto_value_as_data(tmp_path):
    env_file = tmp_path / ".env"
    original = b"APP_VERSION=old\nPOSTGRES_DB=motioncare\n"
    env_file.write_bytes(original)
    env_file.chmod(0o600)
    injected_marker = tmp_path / "must-not-exist"

    completed = subprocess.run(
        [str(PP_MCARE_CONTROL_PLANE_ENV_SCRIPT)],
        cwd=tmp_path,
        input=(
            f"{'a' * 64}\n"
            f'false"; touch {injected_marker}; #\n'
        ),
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert env_file.read_bytes() == original
    assert not injected_marker.exists()


def test_production_workflow_supplies_token_digest_before_deploying():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    deploy_step = workflow[workflow.index("      - name: 部署指定版本") :]
    configure_position = deploy_step.index("./configure-pp-mcare-control-plane.sh")
    deploy_position = deploy_step.index("./deploy.sh")
    assert configure_position < deploy_position
    assert "secrets.PP_MCARE_SERVICE_TOKEN_SHA256" in deploy_step
    assert (
        'printf \'%s\\n%s\\n\' "$PP_MCARE_SERVICE_TOKEN_SHA256" '
        '"$PP_MCARE_AUTO_ENQUEUE_ENABLED"'
    ) in deploy_step


def test_production_workflow_reads_auto_enqueue_flag_with_safe_false_default():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    deploy_step = workflow[workflow.index("      - name: 部署指定版本") :]

    assert (
        "PP_MCARE_AUTO_ENQUEUE_ENABLED: "
        "${{ vars.PP_MCARE_AUTO_ENQUEUE_ENABLED || 'false' }}"
    ) in deploy_step
    remote_command = deploy_step[deploy_step.index('"cd /opt/motioncare-prod') :]
    assert "./configure-pp-mcare-control-plane.sh &&" in remote_command
    assert "$PP_MCARE_AUTO_ENQUEUE_ENABLED" not in remote_command
    assert "$PP_MCARE_SERVICE_TOKEN_SHA256" not in remote_command
