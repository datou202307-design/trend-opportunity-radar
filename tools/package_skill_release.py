from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Iterable


VERSION_PATTERN = re.compile(r"^v\d+\.\d+\.\d+(?:-[a-z0-9][a-z0-9.-]*)?$")
ALLOWED_ROOTS = {"SKILL.md", "agents", "assets", "references", "scripts"}
ARCHIVE_TIME = (1980, 1, 1, 0, 0, 0)


class PackageError(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def release_files(skill_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in skill_root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(skill_root)
        if relative.parts[0] not in ALLOWED_ROOTS:
            continue
        if "__pycache__" in relative.parts or path.suffix.lower() in {".pyc", ".pyo"}:
            continue
        if path.is_symlink():
            raise PackageError(f"Symlinks are not allowed in the release package: {relative.as_posix()}")
        files.append(path)
    required = {"SKILL.md", "agents/openai.yaml"}
    present = {path.relative_to(skill_root).as_posix() for path in files}
    missing = sorted(required - present)
    if missing:
        raise PackageError(f"Required Skill files are missing: {', '.join(missing)}")
    return sorted(files, key=lambda path: path.relative_to(skill_root).as_posix())


def install_text(version: str) -> bytes:
    return (
        "Trend Opportunity Radar " + version + "\n\n"
        "1. Extract this archive.\n"
        "2. Copy the trend-opportunity-radar folder into your Agent Skill directory.\n"
        "3. Reload the Agent session.\n"
        "4. Optional first run: python scripts/trend_radar.py demo --output-dir ./trend-radar-demo\n\n"
        "The Skill does not contain cookies, browser sessions, credentials, or live platform data.\n"
    ).encode("utf-8")


def zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, ARCHIVE_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    return info


def write_zip(path: Path, entries: Iterable[tuple[str, bytes]]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in entries:
            archive.writestr(zip_info(name), payload)


def package_release(repo_root: Path, output_dir: Path, version: str) -> dict:
    if not VERSION_PATTERN.fullmatch(version):
        raise PackageError("Version must look like v1.2.3 or v1.2.3-candidate.")
    skill_root = repo_root / "skills" / "trend-opportunity-radar"
    license_path = repo_root / "LICENSE"
    if not skill_root.is_dir() or not license_path.is_file():
        raise PackageError("Expected the public Skill directory and repository LICENSE.")

    entries: list[tuple[str, bytes]] = []
    file_manifest: list[dict[str, object]] = []
    prefix = "trend-opportunity-radar"
    for source in release_files(skill_root):
        relative = source.relative_to(skill_root).as_posix()
        payload = source.read_bytes()
        archive_path = f"{prefix}/{relative}"
        entries.append((archive_path, payload))
        file_manifest.append({"path": archive_path, "size": len(payload), "sha256": sha256_bytes(payload)})
    for relative, payload in (
        ("LICENSE", license_path.read_bytes()),
        ("INSTALL.txt", install_text(version)),
    ):
        archive_path = f"{prefix}/{relative}"
        entries.append((archive_path, payload))
        file_manifest.append({"path": archive_path, "size": len(payload), "sha256": sha256_bytes(payload)})

    output_dir.mkdir(parents=True, exist_ok=True)
    archive_name = f"trend-opportunity-radar-{version}.zip"
    archive_path = output_dir / archive_name
    if archive_path.exists():
        raise PackageError(f"Refusing to overwrite an existing release archive: {archive_path}")
    write_zip(archive_path, sorted(entries, key=lambda item: item[0]))
    archive_payload = archive_path.read_bytes()
    archive_sha = sha256_bytes(archive_payload)
    manifest = {
        "schema_version": "trend-radar-release-package-v0.1",
        "version": version,
        "archive": archive_name,
        "archive_size": len(archive_payload),
        "archive_sha256": archive_sha,
        "root_directory": prefix,
        "file_count": len(file_manifest),
        "files": sorted(file_manifest, key=lambda item: str(item["path"])),
        "exclusions": ["tests", "__pycache__", "local outputs", "credentials", "browser sessions", "live platform data"],
    }
    manifest_path = output_dir / f"trend-opportunity-radar-{version}.manifest.json"
    checksum_path = output_dir / f"trend-opportunity-radar-{version}.sha256"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    checksum_path.write_text(f"{archive_sha}  {archive_name}\n", encoding="utf-8")
    return {**manifest, "output_dir": str(output_dir.resolve())}


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a deterministic, auditable Skill release ZIP.")
    parser.add_argument("--version", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        result = package_release(args.root.resolve(), args.output_dir.resolve(), args.version)
    except PackageError as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

