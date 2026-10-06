@AGENTS.md

<!-- Claude Code specifics only; at most 20 lines. -->
Run `python scripts/replay_audit.py --all` before every commit that touches the detector, the statistics, the baselines or the emailer; a BLOCK means the change is wrong on data that really occurred.
