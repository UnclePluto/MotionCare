#!/usr/bin/env python3
"""Pure release gate: installed lock, immutable assets, source geometry and contract."""

from __future__ import annotations

import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from apps.crf.registry_loader import check_crf_assets  # noqa: E402
from crf_registry.schema import validate_registry_contract  # noqa: E402
from crf_registry.source_slots import build_source_slots  # noqa: E402

REGISTRY = Path("specs/patient-rehab-system/crf/registry.v1.json")
TEMPLATE = Path("docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx")


def _installed_lock(path: Path) -> dict:
    locked = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)", line)
        if match is None:
            raise ValueError(f"依赖必须精确锁定：{line}")
        name, version = match.groups()
        name = re.sub(r"[-_.]+", "-", name).lower()
        if name in locked:
            raise ValueError(f"重复依赖：{name}")
        actual = metadata.version(name)
        if actual != version:
            raise ValueError(f"依赖锁未生效：{name} 需要 {version}，实际 {actual}")
        locked[name] = version
    if not locked:
        raise ValueError("运行依赖锁为空")
    # Check every installed runtime distribution's declared dependencies, including
    # extras (notably psycopg-binary) locked explicitly in the deployment snapshot.
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name

    pending = [
        (name, frozenset()) for name in [*locked, "motioncare-backend", "motion-analysis-contract"]
    ]
    checked = set()
    while pending:
        name, extras = pending.pop()
        if (name, extras) in checked:
            continue
        checked.add((name, extras))
        for raw in metadata.requires(name) or []:
            dependency = Requirement(raw)
            if dependency.marker and not any(
                dependency.marker.evaluate({"extra": extra}) for extra in (extras or {""})
            ):
                continue
            key = canonicalize_name(dependency.name)
            if key not in locked and key not in {"motioncare-backend", "motion-analysis-contract"}:
                raise ValueError(f"依赖闭包未锁定：{name} -> {key}")
            if metadata.version(key) not in dependency.specifier:
                raise ValueError(f"依赖版本不兼容：{name} -> {dependency}")
            pending.append((key, frozenset(dependency.extras)))
    return locked


def verify_crf_release(*, repo_root: Path, registry_path: Path, template_path: Path) -> dict:
    if sys.version_info[:2] != (3, 12):
        raise ValueError("发布校验必须使用 Python 3.12")
    locked = _installed_lock(repo_root / "backend/requirements.lock.txt")
    assets = check_crf_assets(registry_path=registry_path, template_path=template_path)
    copy_path = repo_root / "frontend/src/crf/registry.v1.json"
    if registry_path.read_bytes() != copy_path.read_bytes():
        raise ValueError("前后端 registry 副本不同")
    registry = json.loads(registry_path.read_text())
    if registry.get("schema_revision") != 3:
        raise ValueError("schema_revision 必须为 3")
    manifest = build_source_slots(template_path)
    if manifest != json.loads(registry_path.with_name("source_slots.v1.json").read_text()):
        raise ValueError("独立源位置清单与原表不一致")
    coverage = dict(
        tables=manifest["table_count"], rows=manifest["row_count"], slots=len(manifest["slots"])
    )
    if coverage != dict(tables=31, rows=265, slots=561):
        raise ValueError(f"原位置覆盖异常：{coverage}")
    errors = validate_registry_contract(registry, manifest)
    if errors:
        raise ValueError("来源绑定合约不一致：" + "; ".join(errors))
    return {
        **assets,
        "schema_revision": registry["schema_revision"],
        "source_coverage": coverage,
        "contract_errors": errors,
        "python": sys.version.split()[0],
        "runtime_packages": locked,
        "lock_sha256": hashlib.sha256(
            (repo_root / "backend/requirements.lock.txt").read_bytes()
        ).hexdigest(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--registry-path", type=Path)
    parser.add_argument("--template-path", type=Path)
    args = parser.parse_args()
    try:
        result = verify_crf_release(
            repo_root=args.repo_root,
            registry_path=args.registry_path or args.repo_root / REGISTRY,
            template_path=args.template_path or args.repo_root / TEMPLATE,
        )
    except (OSError, ValueError, RuntimeError, metadata.PackageNotFoundError) as exc:
        print(f"CRF 发布校验失败：{exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
