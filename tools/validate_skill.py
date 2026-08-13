from __future__ import annotations

import argparse
import re
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the public Skill's required metadata.")
    parser.add_argument("skill_directory")
    args = parser.parse_args()
    skill = Path(args.skill_directory).resolve()
    manifest = skill / "SKILL.md"
    if not manifest.is_file():
        raise SystemExit("SKILL.md is missing.")
    text = manifest.read_text(encoding="utf-8")
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not match:
        raise SystemExit("SKILL.md must start with YAML frontmatter.")
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            raise SystemExit(f"Invalid frontmatter line: {line}")
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip().strip('"\'')
    if set(fields) != {"name", "description"}:
        raise SystemExit("Frontmatter must contain only name and description.")
    if not re.fullmatch(r"[a-z0-9-]{1,63}", fields["name"]):
        raise SystemExit("Skill name must use lowercase letters, digits, and hyphens.")
    if fields["name"] != skill.name:
        raise SystemExit("Skill name must match its directory name.")
    if len(fields["description"]) < 40:
        raise SystemExit("Skill description is too short to be a useful trigger.")
    if not (skill / "agents" / "openai.yaml").is_file():
        raise SystemExit("agents/openai.yaml is missing.")
    print("Skill structure validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
