from __future__ import annotations

import argparse
import json
from pathlib import Path

from platform_adapter_contract import REGISTRY_PATH, load_registry


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the platform adapter registry contract.")
    parser.add_argument("--registry", default=str(REGISTRY_PATH))
    args = parser.parse_args()
    registry = load_registry(Path(args.registry))
    print(json.dumps({
        "valid": True,
        "schema_version": registry["schema_version"],
        "contract_version": registry["contract_version"],
        "platforms": sorted(registry["platforms"]),
        "adapters": sorted(registry["adapters"]),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
