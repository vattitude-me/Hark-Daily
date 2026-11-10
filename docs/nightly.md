# The Automated Daily Pack Run (macOS Apple Silicon MPS)

`python -m app pack` fetches the day's stories across 7 sections, generates extractive broadcast scripts, voices them with neural voices, generates dynamic two-host podcast banter, and publishes all audio and metadata to Supabase. Clients refuse a day until its narrators and podcast markers are published, ensuring listeners always receive a complete edition.

---

## Architecture

The entire synthesis pipeline runs locally on an **Apple Silicon Mac (M3 Pro)** using **Metal Performance Shaders (MPS)** hardware acceleration. There are zero cloud GPU dependencies, zero cloud VM rental costs, and zero external infrastructure requirements.

```
[macOS Hardware RTC Alarm (pmset)]
        │ 05:58 AM (Morning) / 17:58 PM (Evening)
        ▼
[DarkWake Mode (Lid Closed on AC Power)]
        │ Screen stays off, CPU/GPU & Network active
        ▼
[macOS launchd Daemon]
        │ 06:00 AM: me.vattitude.harkdaily.morning
        │ 18:00 PM: me.vattitude.harkdaily.evening
        ▼
[Runner Script: caffeinate -i -s -m]
        │ Holds system sleep assertion during generation
        ├──► Starts local Chatterbox-Turbo (:8090, PyTorch MPS)
        ├──► Fetches news (CBC, TechCrunch, ScienceDaily, BetaKit)
        ├──► Generates stories & podcast dialogue (Gemini / Groq LLM chain)
        ├──► Voices stories (C-3PO, Matthew, Kelly) & podcast banter pieces
        ├──► Uploads MP3s to Supabase Storage (briefings/)
        ├──► Inserts metadata into Supabase DB (story_audio, podcast_clips)
        ├──► Dispatches Web Push Notifications (VAPID)
        ├──► Queues next edition's hardware wake via scripts/schedule_wake.sh
        └──► Shuts down local voice service & releases caffeinate assertion
        │
        ▼
[Mac returns to low-power sleep (~3-5W)]
```

---

## Scheduled Editions

### 1. Morning Edition (05:00 / 06:00 AM) — Active
* **Runner**: [`scripts/morning_pack_mac.sh`](file:///Users/vattitude/Coding/Morning_Brief/scripts/morning_pack_mac.sh)
* **LaunchAgent**: `~/Library/LaunchAgents/me.vattitude.harkdaily.morning.plist`
* **Schedule**: Daily at 05:00 / 06:00 AM local time (`America/Toronto`).
* **Content**: Curated stories across 8 sections (Top, Markets, AI, Tech, Politics, Entertainment, Science, Sports), voiced by C-3PO, Matthew, and Kelly, plus dynamic opening, teaser, bridge, and sign-off banter for the two-host Podcast edition.
* **Wake Relay**: On completion, automatically schedules tomorrow's 04:58 (4:58 AM) wake timer via [`scripts/schedule_wake.sh`](file:///Users/vattitude/Coding/Morning_Brief/scripts/schedule_wake.sh) `morning`.

### 2. Evening Edition (18:00 / 6:00 PM) — Paused
* **Status**: Paused / Disabled per configuration.
* **LaunchAgent**: Archived in `~/Library/LaunchAgents/disabled/me.vattitude.harkdaily.evening.plist` (unloaded from launchctl).
* **Runner**: [`scripts/evening_pack_mac.sh`](file:///Users/vattitude/Coding/Morning_Brief/scripts/evening_pack_mac.sh) (retained for on-demand execution).

---

## Power Management & Lid-Closed Execution

Apple Silicon MacBooks enter sleep when the lid is closed unless connected to an external display. To run autonomously while connected to AC power with the lid closed:

1. **Repeating Hardware Wake**:
   `pmset repeat wakeorpoweron MTWRFSU 05:58:00` acts as a permanent hardware anchor, waking the machine into DarkWake mode 2 minutes before the morning launchd trigger.
2. **Dynamic Relay Wake**:
   [`scripts/schedule_wake.sh`](file:///Users/vattitude/Coding/Morning_Brief/scripts/schedule_wake.sh) uses `sudo pmset schedule wake "MM/dd/yy HH:mm:ss"` (enabled without password via `/etc/sudoers.d/hark_pmset`) to schedule the evening wake timer.
3. **Execution Assertion**:
   Both runners execute under `caffeinate -i -s -m "$0" "$@"`, ensuring the Mac does not sleep while the local PyTorch model synthesizes audio.

---

## Manual & On-Demand Commands

```bash
# Run morning briefing pack immediately (stories + podcast banter)
./scripts/morning_pack_mac.sh

# Run evening briefing pack immediately
./scripts/evening_pack_mac.sh

# Re-voice only today's podcast banter
./scripts/podcast_pack_mac.sh --force

# Surgically re-voice a single story or section
python scripts/regen_story.py --date 2026-11-10 --section markets --rank 1

# Inspect current hardware wake schedule
./scripts/schedule_wake.sh status
```

---

## Data Retention & Cleanup

Audio and database records are kept for the current active editions: successful runs prune older days from Supabase Storage and database tables (`prune_older`), keeping storage well within free-tier quotas.
