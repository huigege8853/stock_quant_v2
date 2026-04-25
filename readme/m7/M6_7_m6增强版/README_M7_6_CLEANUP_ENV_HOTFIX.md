# M7.6 Cleanup Env Hotfix

Replace `tools/cleanup_m7_6_rerun_artifacts.py` with the included file.

It now loads `.env` / `.env.local`, accepts multiple DB URL env names, and reads `M7_DAILY_PLANS_FILE` with `utf-8-sig`.

Run:

```powershell
python tools/cleanup_m7_6_rerun_artifacts.py
```

Then rerun M7.6 with `M7_REPLACE_EXISTING=false`.
