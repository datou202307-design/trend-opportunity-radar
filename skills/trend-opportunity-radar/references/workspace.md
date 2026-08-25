# Local research workspace

Use the workspace only when the user wants to revisit, organize, continue, or monitor multiple existing research runs. It indexes local artifacts; it does not collect platform data, upload reports, or create scheduled tasks.

```bash
python scripts/trend_radar.py workspace \
  --root PATH/TO/RESEARCH-ROOT \
  --output-dir PATH/TO/RESEARCH-ROOT/workspace \
  --language en
```

Use `--language zh-CN` for Chinese. The output directory must stay inside the indexed root so report links remain usable over loopback HTTP.

The command reads `run-manifest.json` and `monitor.json` as the sources of truth, then generates:

- `workspace.json`: a machine-readable index without absolute paths or raw platform content;
- `index.html`: a local dashboard of unfinished runs, due monitoring recommendations, completed reports, and the exact prompt needed to continue;
- `summary-cards/*.html`: optional local decision summaries for completed reports.

A due monitor means only that `next_run_after` has passed. Display “scheduled” only when `external_schedule_created` is true because a real scheduling tool succeeded. A completed report without a monitor may be shown as a decision to consider, never as an already-created monitoring cycle.

Repeated builds with unchanged inputs are byte-stable. The output directory is bound to its first indexed root and must refuse another root. Serve the research root over loopback HTTP and inspect the real workspace on desktop and mobile before delivery. Summary cards may contain the subject and decision answer; remind the user to review them before sharing.
