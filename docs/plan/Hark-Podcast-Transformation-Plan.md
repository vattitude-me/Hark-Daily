# Hark Daily — Transformation Plan: From News Reader to Two-Host Podcast

**Repository:** https://github.com/vattitude-me/Hark-Daily  
**Current app:** https://hark.vattitude.ca/  
**Primary script-generation provider:** Groq API  
**Local speech generation:** Chatterbox Turbo on an Apple M3 Pro Mac server  
**Feeds / editions:** Canada (CA), United States (US), India (IN)

## 1. Mission

Transform Hark Daily from a sequential RSS news reader with short host interludes into a genuinely conversational, polished two-host news podcast. The hosts must discuss each story, explain context and implications, ask natural questions, respond meaningfully to one another, and use pauses and emotion appropriate to the subject. The output should sound like an edited radio/podcast conversation, not two voices taking turns reading summaries.

Keep the existing RSS sources, Groq as the primary script-generation provider, Chatterbox Turbo on the local Mac for speech, and existing web/PWA, Android, and Supabase integrations wherever practical.

## 2. Current Symptoms and Likely Causes

The known symptoms are:

- The first 30 seconds contain only a couple of lines of generic host banter.
- The two hosts do not meaningfully discuss the article; most of the news is still read as a conventional narration.
- Dialogue can be incoherent, repetitive, or disconnected from the article.
- Speech lacks natural conversational timing, reactions, emotional variation, and intentional silence.
- Podcast clips may be assembled by concatenating separately encoded MP3 byte streams rather than decoding, joining, and re-encoding valid audio.
- A leading pause directive may be discarded by the voice service's text parsing. Do not depend on a pause token at the beginning of a separate TTS request to create silence between clips.
- The existing code path may attempt Gemini before Groq. The new dialogue path must use Groq first, as explicitly required.

Treat these as implementation hypotheses to verify against the current checked-out code before changing it. Do not assume line numbers or repository state remain unchanged.

## 3. Product Requirements

### 3.1 Editorial conversation

Each selected story must become a short conversation, not a headline read followed by generic reactions. As a starting point:

- Lead stories: approximately 60–90 seconds of discussion.
- Regular stories: approximately 30–50 seconds of discussion.
- Most stories: 4–6 substantive speaker turns, adjusted to story complexity and importance.
- Every turn must do at least one useful thing: introduce a verified fact, clarify context, ask a genuine follow-up, explain an implication, distinguish what is known from what is uncertain, or summarize what happens next.
- Both hosts should contribute substance. Avoid a fixed formula where one host always reads facts and the other merely says “That’s interesting.”
- The opening should begin with a compelling, verified news development and why it matters. Keep greetings brief; do not spend the first 30 seconds on empty banter.
- Connect stories and sections with concise transitions. Do not force a transition when it sounds unnatural.
- Retain Canada, US, and India editions and the existing article/source attribution.

### 3.2 Stable host identities

Use the existing configured host names and voice identities (currently understood to be Matthew and Kelly; verify actual configuration). Establish complementary, flexible editorial roles:

- **Lead host:** sets up the story, asks the obvious listener question, maintains momentum, and summarizes the point.
- **Analysis host:** contributes context, explains implications and trade-offs, and respectfully challenges assumptions when the source material supports it.

Allow roles to switch naturally. Do not make either host a caricature. Do not fabricate personal experience or claim either host witnessed events.

### 3.3 Factual grounding and safety

- Every factual claim must be supported by the provided article text or other explicitly supplied source material.
- Preserve attribution for disputed claims and statistics.
- Distinguish confirmed facts, reported claims, analysis, and uncertainty.
- Do not invent quotes, data, motives, predictions, or outcomes.
- Do not imply that the system independently verified facts it did not verify.
- Do not make jokes or use playful reactions for tragedies, disasters, violence, or other sensitive stories.
- Use reactions such as laughter, gasps, or sighs sparingly and only when appropriate.
- Avoid copying long passages from source articles verbatim. Summarize and discuss them.

### 3.4 Natural voice performance

- Keep the existing Chatterbox Turbo local synthesis path and voice conditioning unless testing shows a concrete blocker.
- Use natural punctuation and varied sentence lengths in the script.
- Use supported paralinguistic tags only when appropriate and verify actual model support. Do not assume unsupported generation parameters change performance.
- Add silence in the audio assembly layer, not solely with text markers at the start of a new synthesis request.
- The final episode must have consistent sample rate, channel layout, loudness and no audible clipping, broken MP3 boundaries, or cut-off words.

### 3.5 Preserve existing product capabilities

Retain RSS ingestion for CA/US/IN, source URLs, article metadata, scheduling/current generation triggers, Supabase storage, user topic selections, existing PWA/mobile playback controls, background playback/offline behavior where supported, and Full Brief mode during migration. Do not silently publish old single-host narration as a podcast when conversation generation fails.

## 4. Target Architecture

1. **Ingest:** pull articles from existing RSS feeds.
2. **Clean and deduplicate:** normalize article text and identify duplicate/related coverage across sources.
3. **Build story facts:** produce a concise story brief with source, title, article text, key facts, entities, numbers/dates, attribution, uncertainty, context, impact, and “what happens next” when supported.
4. **Create an editorial rundown:** rank stories and group them by CA/US/IN or existing edition/section rules. Avoid repeating the same event from multiple RSS sources unless the additional coverage is useful.
5. **Generate dialogue with Groq first:** return structured turns for each story plus a cold open, concise episode introduction, section transitions as needed, and sign-off.
6. **Validate:** parse schema, check speaker names, minimum useful turns, length targets, repetition, continuity, unsupported claims, and source references. Repair only the invalid story where possible.
7. **Fallback:** if Groq fails, use a configured local instruct model where available with the same output schema. If the fallback cannot pass validation, mark the segment failed or use an explicitly labelled, safe fallback—not silent legacy narration.
8. **Synthesize:** generate each speaker turn with Chatterbox Turbo on the M3 Pro. Cache successful audio per turn/segment and invalidate cache when script or voice/model configuration changes.
9. **Assemble audio:** decode segments, normalize sample rate and channel layout, insert actual silence, apply consistent loudness processing, concatenate waveforms, then encode the final output once. Prefer FFmpeg or the project's existing robust audio tooling.
10. **Publish:** save audio and structured transcript/metadata to Supabase and expose a sequence of discussion segments to the clients.
11. **Play:** the PWA and Android apps play the conversational segments in editorial order and show story context, source links, transcript, and the current speaker/turn where supported.

## 5. Dialogue Contract

Use a strict structured output format rather than free-form dialogue that downstream code must guess how to split. The precise schema should fit project conventions, but it should contain fields equivalent to:

```json
{
  "story_id": "stable-story-id",
  "tone": "curious and analytical",
  "turns": [
    {
      "speaker": "matthew",
      "purpose": "lead",
      "text": "A verified, substantive opening to the story.",
      "fact_refs": ["F1"]
    },
    {
      "speaker": "kelly",
      "purpose": "context",
      "text": "Useful context grounded in the supplied reporting.",
      "fact_refs": ["F2"]
    },
    {
      "speaker": "matthew",
      "purpose": "question",
      "text": "A natural question that follows from the facts.",
      "fact_refs": []
    },
    {
      "speaker": "kelly",
      "purpose": "implication",
      "text": "An explanation of what it could mean and what remains unknown.",
      "fact_refs": ["F3"]
    }
  ]
}
```

This is an example contract, not final user-facing news content. Do not include fake facts to fill fields. Model outputs must be schema-validated and escaped safely before storage or synthesis.

### Dialogue-generation rules

The prompt should instruct the model to:

- Write speech that sounds natural when read aloud, not written journalism.
- Lead with the news and its significance, not greetings or vague reactions.
- Move through a coherent narrative: what happened → context → why it matters → what is known/unknown or what happens next.
- Make each host's next line responsive to the previous line.
- Avoid repetition, filler, artificial agreement, excessive rhetorical questions, and “as you mentioned” loops.
- Avoid long uninterrupted monologues. Split turns at natural speaker changes, not every sentence.
- Vary conversational patterns across stories while preserving clarity and reliable pacing.
- Include concise source attribution in speech when useful, and retain full source links in the UI/transcript metadata.
- Target durations using an estimated spoken-word rate; validate with actual synthesized durations and adjust empirically.

## 6. Provider Strategy

1. **Primary:** Groq API using `GROQ_API_KEY` and the repository's configured Groq model selection. Do not hard-code secret values or model IDs without checking existing configuration.
2. **Retry and repair:** bounded retries for transient failures, malformed JSON, or validation failures. Repair the affected story only rather than regenerating the entire episode.
3. **Local fallback:** use a quantized local instruct model available on the M3 Pro through the project's selected runtime. Benchmark quality, memory use and generation time before choosing a model size.
4. **Optional secondary provider:** Gemini may remain configurable as an explicit additional fallback if desired, but it must not be tried before Groq in the new primary path.
5. **Failure behavior:** set clear generation statuses and logs. A failed or low-quality story must not silently be published in the old narration format as if it were a podcast.

Keep API keys and tokens server-side. Never put the Groq key in client-side JavaScript, Android resources, logs, or generated transcripts.

## 7. Audio Production Requirements

### 7.1 Pauses and timing

Use actual audio silence inserted between decoded clips. Initial values to A/B test:

- Ordinary host turn boundary: 250–450 ms.
- Significant reveal or topic change: 500–900 ms.
- Boundary between stories: 600–1,000 ms.

These are initial tuning ranges, not hard-coded universal rules. Allow different values for rapid exchanges, serious reporting, and section breaks. Do not add a pause after every sentence automatically.

### 7.2 Audio stitching

- Do not concatenate independently encoded MP3 byte strings with `b"".join(...)` and assume the result is a valid seamless file.
- Decode all clip outputs to PCM or another robust intermediate representation.
- Standardize sample rate, channel count, sample format and timing.
- Insert silence at the waveform level.
- Apply consistent gain/loudness processing with peak protection; avoid aggressive processing that damages natural voice dynamics.
- Re-encode the finished segment/episode once.
- Validate final duration, codec, sample rate, channel count, peak level, and non-zero audio.
- Detect missing or empty TTS responses and prevent them from corrupting the assembled episode.

### 7.3 Synthesis and caching

- Keep synthesis local to the M3 Pro server.
- Reuse existing voice references/conditioning where possible.
- Cache per turn or per story discussion using a key derived from the script hash, voice identity/configuration, synthesis model/version and audio settings.
- Store render status and errors so one failed turn can be retried without rebuilding the entire episode.
- Verify which Chatterbox Turbo tags and parameters are actually supported in the installed implementation. Do not rely on settings that are ignored by the engine.
- Confirm that concurrent TTS jobs remain within memory and latency limits on the M3 Pro; use bounded concurrency and backpressure.

## 8. Data Model and Playback

Inspect the existing schema before migration. Either extend the existing podcast-clips structure or add a dedicated `podcast_segments` table. Avoid duplicate models if the existing structure can represent this cleanly.

The published segment should support fields equivalent to:

- episode date / edition / section / sort rank
- stable story ID and source article URL
- structured dialogue turns (JSON)
- complete readable transcript
- audio path and measured duration
- writer provider/model and prompt/schema version
- script hash and synthesis configuration hash
- generation/render/publish status and error metadata
- created/updated timestamps

The player order should be:

**Cold open → short episode intro → story discussion → story discussion → section transition (when needed) → remaining discussions → sign-off.**

Do not use normal `story_audio` narration as the podcast segment in the new mode. Preserve regular narration for Full Brief or other existing modes as appropriate.

PWA and Android should provide equivalent behavior: correct sequence, play/pause, seeking, resume/background playback as currently supported, article/source links, transcript/captions, active story indication and speaker labels. Do not over-engineer word-level timing in the initial milestone; segment- or turn-level synchronization is sufficient if accurate word timestamps are unavailable.

## 9. Likely Code Areas to Inspect

Verify names and ownership in the current checkout before editing. Based on the existing project structure, likely areas include:

- `app/podcast.py` — podcast script generation, clips and assembly.
- `app/writer.py` — article summary/card writing; keep separate from dialogue writing.
- `app/storypack.py` — daily story pack generation, publish path, cache and orchestration.
- `voice_service/turbo_voice/text.py` — pause directives and text/tag parsing.
- `voice_service/turbo_voice/engine.py` — Chatterbox Turbo synthesis and supported controls.
- `voice_service/README.md` — documented local generation behavior and setup.
- `supabase/` — schema, migrations, storage and segment metadata.
- `web/js/storypack.js`, `web/js/player.js` and related player files — PWA episode data and playback.
- Android `StoryPack.kt` and related playback classes — equivalent mobile data/playlist path.
- `tests/` — provider selection, dialogue schema, audio assembly and playback-related tests.

Search the current source for the provider call order, clip types, legacy narration fallback, `[[pause:...]]` parsing, MP3 byte concatenation, cache keys, database schema and player playlist construction before deciding exact patches.

## 10. Delivery Phases

### Phase 0 — Repository audit and baseline

- Check the actual branch, working tree, configuration and current tests.
- Trace the whole existing pipeline from RSS ingestion through generated text, TTS, storage and playback.
- Confirm current provider precedence, fallback logic, clip/segment models, pause parser, audio assembly, and M3 Pro deployment constraints.
- Record the current mode's behavior and retain a small set of representative input articles from CA, US and IN for regression tests.
- Produce a concise audit note with verified findings before making large architectural changes.

**Exit criteria:** identified execution path, configuration keys, data model, relevant tests, and a clear migration approach.

### Phase 1 — Single-story vertical slice

- Implement the structured story brief and Groq-first dialogue generator.
- Add JSON/schema validation, bounded retry and local fallback handling.
- Generate a dialogue with meaningful contributions from both hosts.
- Synthesize the turns with Chatterbox Turbo on the M3 Pro.
- Implement PCM-based stitching and deliberate inter-turn silence.
- Save one complete segment with transcript and story metadata.
- Add automated tests and listen to the actual generated audio.

**Exit criteria:** one article can reliably become a coherent, well-paced, publishable two-host discussion end to end.

### Phase 2 — Episode orchestration

- Add story prioritization/deduplication and country/section grouping while preserving current feed semantics.
- Generate the cold open, concise intro, story discussions, necessary transitions and sign-off.
- Cache segments and retry only failures.
- Publish a complete episode without inserting legacy single-host narration into podcast mode.

**Exit criteria:** a full CA, US or IN edition (and any existing combined edition) can be generated in the intended order and has valid audio/transcripts.

### Phase 3 — Web and Android integration

- Adapt the backend response/schema and Supabase migrations as required.
- Make the PWA use the new conversational segments for the new podcast mode.
- Update Android to use the same ordering and segment metadata.
- Preserve existing modes and controls during transition.
- Add a feature flag/edition-level switch so rollback is easy.

**Exit criteria:** web and Android play the same segment sequence and show consistent story and transcript details.

### Phase 4 — Quality tuning and rollout

- Run listening tests across Canada, US and India articles and different story types.
- Improve dialogue prompts based on observed failures, not just prompt length.
- Tune turn length, pause values, loudness and generation concurrency.
- Monitor failed scripts, malformed dialogue, TTS failures and episode build times.
- Enable the new format by default only after the acceptance criteria below are met.
- Retire legacy narration generation from the podcast-only path once the new path is stable; retain it where Full Brief still needs it.

**Exit criteria:** quality, reliability, and runtime behavior are demonstrated on representative real articles and on both clients.

## 11. Test Plan

### Script tests

- Groq is selected first when configured.
- Groq timeout, rate limit, API error and malformed output each follow the defined fallback policy.
- Output parses against the schema and uses only configured speaker IDs.
- Story turns are coherent, non-repetitive and tied to provided source facts.
- Empty, duplicate, truncated, unusually short, and excessively long articles are handled gracefully.
- Sensitive stories do not get inappropriate humour/reaction tags.
- CA, US and IN metadata, source URLs and country/section grouping are preserved.

### Audio tests

- A pause at a clip boundary creates measurable silence in the assembled PCM signal.
- Independent audio clips can be decoded and assembled into a playable output.
- All clips are standardized before concatenation.
- Empty/corrupt TTS output fails safely and is logged.
- Final audio duration is plausible relative to the synthesized turns.
- No broken clip transitions, clipping, missing first/last words or abrupt level changes in listening tests.

### Integration tests

- Successful segments and transcripts are stored with correct source metadata.
- Script or synthesis configuration changes invalidate the relevant cache.
- A failed story can be retried without rebuilding successful segments.
- Podcast mode never silently substitutes the legacy single-host narration path.
- PWA and Android use correct editorial ordering and article/story association.
- Full Brief and other existing behavior remain intact during rollout.

## 12. Acceptance Criteria

The new mode is ready to ship when all of the following are true:

1. The opening contains a meaningful news hook in the first 15–25 seconds, rather than prolonged greetings.
2. Every successfully published story has a real two-host discussion; most ordinary stories have at least four meaningful turns, adjusted for story complexity.
3. Each speaker's turn is responsive to the previous turn and adds context, evidence, explanation, a useful question or a clear takeaway.
4. The script is factually grounded in the supplied sources and distinguishes uncertainty from fact.
5. Repetition, generic filler and disconnected reactions are uncommon in a manually reviewed sample.
6. Inter-speaker and inter-story silences are intentional and audible, but not excessive.
7. The assembled files are valid playable audio with consistent technical properties and no broken MP3 concatenation artifacts.
8. Groq is the primary dialogue provider and the local fallback follows the documented policy.
9. CA, US and IN editions continue to work with source links and existing edition/topic semantics.
10. Web/PWA and Android play the same conversational edition and retain essential existing controls.
11. Automated tests cover provider ordering, schema validation, failure handling, pause insertion, audio assembly and segment ordering.
12. A feature flag or comparable rollback mechanism remains available during rollout.

## 13. Non-Goals for the First Release

Do not block the first release on:

- Replacing the RSS ingestion system.
- Training a custom voice model.
- Replacing Chatterbox Turbo before measured evidence requires it.
- Perfect word-level audio/transcript alignment.
- Adding background music, sound effects or elaborate radio stingers.
- Building a complex multi-agent editorial system.
- Removing Full Brief or other existing modes.

Prioritize coherent dialogue, grounding, audio integrity, performance and reliable playback before production embellishments.

## 14. Agent Execution Instructions

Work directly in the existing repository. Do not only produce a high-level design or rewrite the application wholesale.

1. Inspect repository state and trace current code paths before editing. Confirm every diagnosis against the actual code.
2. Present a brief implementation checklist and identify any database/API changes before making them.
3. Implement the smallest complete end-to-end vertical slice first, then expand it to full episodes and clients.
4. Preserve existing configuration conventions and secrets. Never print keys/tokens in logs or commits.
5. Use the existing test/build/lint commands; add tests for each changed contract. If a service such as Groq or the local voice server is unavailable, mock it in automated tests and state what was not verified live.
6. Avoid unrelated refactoring. Keep changes incremental and easy to review.
7. Add migrations rather than destructively changing persisted data. Keep a rollback path.
8. Do not claim that audio quality is verified from text-only tests. Generate and listen to a representative sample when the local Mac voice service is available.
9. At completion, report: files changed, architectural decisions, migrations/configuration required, tests executed and their results, a generated sample's location if produced, known limitations, and exact steps to enable/disable the new feature.
10. Do not stop after generating a prompt template. The target deliverable is a working end-to-end story-discussion pipeline integrated with the existing product.

## 15. Final Recommendation

Build one excellent end-to-end story discussion first. The biggest improvement will come from having Groq write the actual dialogue of the article—not just an intro and brief teaser—then validating it and rendering the resulting speaker turns into correctly stitched audio. Once that works on the M3 Pro, scale the exact same contract to the daily edition and the web/Android players.
