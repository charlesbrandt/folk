# Deploying the session-promotion job

Reference only -- not installed by this repo. These files describe the intended shape for running `folk promote` on a schedule, on whichever machine hosts your source adapter's sessions (e.g. an always-on server).

Since a real deployment's config necessarily carries real hostnames, IPs, and paths, run `python3 scripts/check_release_hygiene.py` before committing anything under `deploy/` (or anywhere else) -- it scans tracked files for exactly that class of fingerprint, plus real person names. Wire it up as a local pre-commit hook if you want it automatic: `ln -s ../../scripts/check_release_hygiene.py .git/hooks/pre-commit`.

1. `folk` installed on that machine (same package as here), with Ollama already serving your chosen model.
2. Copy `promotion.json.example` to `~/.config/folk/promotion.json` on that machine and fill in the real `sessions_dir` per source profile, plus the profile -> collection routing (`session-promotion-job.md`'s "Routing" section -- one line per profile, never inferred from content).
3. `folk promote` runs one invocation: discovers quiescent (mtime idle > `quiet_seconds`), unprocessed sessions, caps the batch (`cap_per_run`), and for each one extracts, promotes, lints, and appends-or-quarantines into `~/.folk-staging/<collection>/YYYY-MM.<writer>.ndjson`. Idempotency state lives in `~/.folk/promotion-state.json`; a per-session log line lands in `~/.folk/promotion.log`.
4. Install `folk-promote.service` + `folk-promote.timer` under `/etc/systemd/system/` (adjust `ExecStart` to the actual `folk` binary path/user), then `systemctl enable --now folk-promote.timer`.
5. Transport: sync `~/.folk-staging/<collection>/*.ndjson` to that collection's registered journal root (e.g. wherever your `personal` collection lives) as plain files -- rsync or existing sync tooling, an ops detail per the spec. Per-writer naming means concurrent promotion hosts never collide on the same file. Run this sync, then `folk index --rebuild`, before reviewing (`folk review`) or reading (`folk show`).
