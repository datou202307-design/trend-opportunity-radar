"""Adapter-neutral entry point for controlled trend collection.

The implementation remains import-compatible with the original DokoBot module so
existing runs and state files continue to work.
"""

from orchestrate_dokobot_collection import main


if __name__ == "__main__":
    main()
