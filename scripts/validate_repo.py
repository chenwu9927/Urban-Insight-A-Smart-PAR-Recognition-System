from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WEB_CONSOLE_DIR = ROOT / "apps" / "web-console"
CONTRACTS_DIR = ROOT / "contracts" / "http"

REQUIRED_DIRS = (
    ROOT / "apps" / "web-console",
    ROOT / "services",
    ROOT / "agents",
    ROOT / "contracts" / "http",
    ROOT / "contracts" / "events",
    ROOT / "deploy" / "compose",
    ROOT / "deploy" / "docker",
    ROOT / "deploy" / "nginx",
)

FORBIDDEN_PATHS = (
    ROOT / "frontend",
    ROOT / "deployment",
    ROOT / "microservices",
)

EXPECTED_CONTRACTS = {
    "auth-service.openapi.json": "auth-service",
    "media-service.openapi.json": "media-service",
    "analysis-service.openapi.json": "analysis-service",
    "search-service.openapi.json": "search-service",
    "insight-service.openapi.json": "insight-service",
    "agent-service.openapi.json": "agent-service",
}


def run(command: list[str], *, cwd: Path | None = None) -> None:
    location = cwd or ROOT
    print(f"[run] {' '.join(command)}")
    subprocess.run(command, cwd=location, check=True)


def capture(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    location = cwd or ROOT
    print(f"[run] {' '.join(command)}")
    return subprocess.run(
        command,
        cwd=location,
        check=False,
        capture_output=True,
        text=True,
    )


def check_required_paths() -> None:
    missing = [path for path in REQUIRED_DIRS if not path.exists()]
    if missing:
        formatted = ", ".join(str(path.relative_to(ROOT)) for path in missing)
        raise RuntimeError(f"Missing required project paths: {formatted}")


def check_forbidden_paths() -> None:
    existing = [path for path in FORBIDDEN_PATHS if path.exists()]
    if existing:
        formatted = ", ".join(str(path.relative_to(ROOT)) for path in existing)
        raise RuntimeError(f"Legacy paths still present: {formatted}")


def export_and_validate_contracts() -> None:
    run([sys.executable, "scripts/export_openapi_contracts.py"])

    present_files = {path.name for path in CONTRACTS_DIR.glob("*.openapi.json")}
    if present_files != set(EXPECTED_CONTRACTS):
        raise RuntimeError(
            "Unexpected OpenAPI contract set. "
            f"expected={sorted(EXPECTED_CONTRACTS)} present={sorted(present_files)}"
        )

    for filename, service_name in EXPECTED_CONTRACTS.items():
        path = CONTRACTS_DIR / filename
        payload = json.loads(path.read_text(encoding="utf-8"))
        info = payload.get("info") or {}
        if info.get("x-service-name") != service_name:
            raise RuntimeError(f"{filename} is missing x-service-name={service_name}")
        if "paths" not in payload:
            raise RuntimeError(f"{filename} does not contain OpenAPI paths")


def validate_python_sources() -> None:
    for base_name in ("services", "agents", "backend", "agent", "scripts"):
        base_dir = ROOT / base_name
        for path in sorted(base_dir.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            compile(source, str(path), "exec")


def validate_first_party_text() -> None:
    suspicious_patterns = ("闀挎", "璁颁綇", "浠ュ悗", "榛樿", "锛歖")
    search_roots = (
        ROOT / "agent",
        ROOT / "agents",
        ROOT / "backend",
        ROOT / "services",
        ROOT / "docs",
        ROOT / "apps" / "web-console" / "src",
    )
    allowed_suffixes = {".py", ".jsx", ".js", ".md", ".css"}
    hits: list[str] = []

    for root in search_roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix.lower() not in allowed_suffixes or not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if any(pattern in line for pattern in suspicious_patterns):
                    hits.append(f"{path.relative_to(ROOT)}:{lineno}")
                    if len(hits) >= 20:
                        break
            if len(hits) >= 20:
                break
        if len(hits) >= 20:
            break

    if hits:
        formatted = ", ".join(hits)
        raise RuntimeError(f"Suspicious mojibake-like text found in first-party sources: {formatted}")


def validate_agent_autonomy() -> None:
    run([sys.executable, "scripts/validate_agent_autonomy.py"])


def validate_frontend(*, install_deps: bool) -> None:
    npm = shutil.which("npm")
    if not npm:
        raise RuntimeError("npm is not available in PATH")

    if install_deps:
        run([npm, "ci"], cwd=WEB_CONSOLE_DIR)
    run([npm, "run", "build"], cwd=WEB_CONSOLE_DIR)
    validate_frontend_audit(npm)


def validate_frontend_audit(npm: str) -> None:
    result = capture([npm, "audit", "--json"], cwd=WEB_CONSOLE_DIR)
    if not result.stdout.strip():
        raise RuntimeError("npm audit did not return JSON output")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Failed to parse npm audit output: {exc}") from exc

    metadata = payload.get("metadata") or {}
    vulnerabilities = (metadata.get("vulnerabilities") or {}).get("total", 0)
    if vulnerabilities:
        raise RuntimeError(f"npm audit reported {vulnerabilities} vulnerabilities")


def validate_compose() -> None:
    docker = shutil.which("docker")
    if not docker:
        raise RuntimeError("docker is not available in PATH")

    run([docker, "compose", "config"])
    run([docker, "compose", "-f", "deploy/compose/docker-compose.yml", "config"])
    run(
        [
            docker,
            "compose",
            "--env-file",
            ".env.example",
            "-f",
            "deploy/compose/docker-compose.yml",
            "-f",
            "deploy/compose/docker-compose.prod.yml",
            "config",
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate repository structure and deployment guardrails.")
    parser.add_argument(
        "--skip-frontend",
        action="store_true",
        help="Skip the web console build validation.",
    )
    parser.add_argument(
        "--install-frontend-deps",
        action="store_true",
        help="Run npm ci before building the web console.",
    )
    parser.add_argument(
        "--skip-docker",
        action="store_true",
        help="Skip docker compose validation.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    check_required_paths()
    check_forbidden_paths()
    export_and_validate_contracts()
    validate_python_sources()
    validate_first_party_text()
    validate_agent_autonomy()

    if not args.skip_frontend:
        validate_frontend(install_deps=args.install_frontend_deps)

    if not args.skip_docker:
        validate_compose()

    print("[ok] repository validation passed")


if __name__ == "__main__":
    main()
