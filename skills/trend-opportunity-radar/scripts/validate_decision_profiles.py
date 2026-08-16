from __future__ import annotations

import json

from decision_profiles import load_registry


if __name__ == "__main__":
    registry = load_registry()
    print(json.dumps({"valid": True, "schema_version": registry["schema_version"], "profiles": sorted(registry["profiles"])}, ensure_ascii=False, indent=2))
