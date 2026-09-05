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
