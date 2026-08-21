from pathlib import Path


WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2]
    / ".github"
    / "workflows"
    / "deploy-production.yml"
)


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
