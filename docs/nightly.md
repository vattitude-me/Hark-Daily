# Daily run

Each morning a scheduled job builds the day's pack with `python -m app pack`. It reads the feeds for all 8 sections, writes the scripts and the two-host dialogue, voices everything, and uploads the audio and data to the backend. The app only shows a day once the whole pack is published.

Voice work runs on the build machine's own GPU. There is no cloud GPU.

## Schedule

| Time | What happens |
| :--- | :--- |
| 04:58 | The machine wakes if it was asleep |
| 05:00 | The scheduler starts the morning run script |
| about 05:20 | The pack is published and the machine can sleep again |

Only the morning run is scheduled. The evening script still works if you run it by hand.

## What the run script does

1. Keeps the machine awake for the length of the run.
2. Loads `.env` and sets the voice and podcast settings.
3. Starts the voice service and waits for its health check.
4. Runs the pack for all three editions.
5. Sets the next wake time.
6. Stops the voice service.

## Setup

1. Register the run script with your scheduler (for example launchd or cron) to start at 05:00 and log to `logs/`.
2. Schedule a daily wake a couple of minutes earlier, using your platform's wake or power-on timer.
3. Optional. Allow the wake-scheduling script to run without a password prompt.

## Missed runs

Most schedulers run a missed job when the machine wakes from sleep. They do not run it after a shutdown or a flat battery. In that case, run the script by hand.

## Commands

```bash
./scripts/morning_pack_mac.sh                      # full run now
./scripts/podcast_pack_mac.sh --force              # redo today's dialogue only
python -m app pack --check                         # what today's pack has
tail -f logs/morning_pack.log                      # follow a run
```

## Retention

Successful runs delete older days from storage and tables with `prune_older()`. The fixed voice notes are never deleted. `KEEP_DAYS` sets how many days to keep.
