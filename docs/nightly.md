# Daily run on macOS

Each morning a Mac builds the day's pack with `python -m app pack`. It reads the feeds for all 8 sections, writes the scripts and the two-host dialogue, voices everything, and uploads the audio and data to Supabase. The app only shows a day once the whole pack is published.

All voice work runs on the Mac's GPU (Apple Silicon, MPS). There is no cloud GPU.

## Schedule

| Time | What happens |
| :--- | :--- |
| 04:58 | `pmset` wakes the Mac, even with the lid closed, if it is on power |
| 05:00 | launchd starts `scripts/morning_pack_mac.sh` |
| about 05:20 | Pack is published and the Mac can sleep again |

The morning run is the only one active. The evening script, `scripts/evening_pack_mac.sh`, still works if you run it by hand.

## What the run script does

1. Re-runs itself under `caffeinate -i -s -m` so the Mac stays awake.
2. Loads `.env` and sets the voice and podcast settings.
3. Starts the voice service on port 8090 and waits for `/health`.
4. Runs the pack for all three editions.
5. Sets the next wake with `scripts/schedule_wake.sh`.
6. Stops the voice service.

## Setup

1. Install the LaunchAgent at `~/Library/LaunchAgents/me.vattitude.harkdaily.morning.plist`. It runs the script at 05:00 and logs to `logs/`.
2. Add a daily hardware wake:

   ```bash
   sudo pmset repeat wakeorpoweron MTWRFSU 04:58:00
   ```

3. Optional. To let `schedule_wake.sh` set one-off wakes without a password, add a sudoers rule for `/usr/bin/pmset` in `/etc/sudoers.d/`.

## Missed runs

launchd runs a missed job when the Mac wakes from sleep. It does not run it after the Mac was shut down or the battery ran out. In that case, run the script by hand.

## Commands

```bash
./scripts/morning_pack_mac.sh                      # full run now
./scripts/podcast_pack_mac.sh --force              # redo today's dialogue only
python scripts/regen_story.py --date 2026-11-10 --section markets --rank 1
python -m app pack --check                         # what today's pack has
./scripts/schedule_wake.sh status                  # upcoming wakes
tail -f logs/morning_pack.log                      # follow a run
```

## Retention

Successful runs delete older days from Supabase storage and tables with `prune_older()`. The fixed voice notes in `notes/static/` are never deleted. `KEEP_DAYS` sets how many days to keep.
