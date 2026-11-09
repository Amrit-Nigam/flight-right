# Passive live radio integration

The dashboard's **Live radio monitor** and `/radio` workspace listen to an existing radio
channel. The application does not originate or synthesize ATCO messages.

## Using it

1. Connect a receiver, line-in or virtual audio cable as an audio input; alternatively,
   play the radio in a browser tab and choose shared tab audio. Select **Share audio**
   in the browser's source picker. A default audio input may be the computer microphone.
2. Choose **Mixed pilot + ATCO radio** for a normal shared radio channel. Only choose a
   labelled channel if its upstream source actually separates ATCO and pilot audio.
3. Start listening. The level meter should respond to the radio. Adjust the transmission
   threshold if quiet speech is missed or static repeatedly opens the gate.
4. Completed transmissions appear automatically, with the transcript, aircraft match,
   extracted actions, role hint, confidence and decision. No per-transmission recording
   button is required. Stop listening releases the audio source and clears queued audio.
5. Review ambiguous or low-confidence captured information before using it. The latest
   20 live audio segments remain available in browser memory for playback after listening
   is stopped. Review links the correction to the original transcription; it does not
   send a message to an aircraft. Reviews older than two minutes cannot apply intent.

Live radio requires live aircraft surveillance to change trajectory intent. With replay
traffic, radio is still transcribed and extracted, but cannot change recorded aircraft.
The source indicator explains this. Use the explicitly labelled sample recordings for
offline experiments with replay. The configured radio channel must cover the airspace
being monitored; matching callsigns alone does not establish geographic relevance.

## Data path and implemented effects

AudioWorklet captures mono PCM without playing the feed back into the input. An energy
gate groups candidate transmissions with 250 ms of pre-roll, 800 ms of trailing silence
and a 25 second cap. Original-rate WAV is sent to the backend, which resamples to 16 kHz
with a filtered polyphase resampler. Silero VAD, bundled with faster-whisper, checks live
segments for speech before the configured fine-tuned Whisper recognizer is called.
Whisper's saved evaluation decoding settings and weights are unchanged.

The client submits one segment at a time, queues at most six and reports dropped, failed
or stale segments. Audio older than 45 seconds is skipped before submission; the server
rejects supplied timestamps older than 60 seconds. These are local engineering limits,
not aviation standards or measured guarantees. Forced splits and their continuations
remain incomplete until a pause; their content cannot automatically become an instruction.
Stopping can cancel a client request but cannot undo processing already begun on the server.

Extraction handles multiple instructions in one transmission. Callsigns are matched to
currently visible aircraft; closely tied matches, implausible values, low confidence,
negation, conditional instructions and conflicting instructions for the same axis do not
silently become trajectory constraints. Invalid headings are rejected rather than wrapped
into valid ones. Pilot requests and readbacks never issue a new clearance.

Accepted altitude instructions cap candidate altitudes; heading instructions filter the
candidate fan, preserving the existing fallback if every candidate contradicts the heading.
Those candidates feed multi-path conflict assessment and resolution checks on subsequent
surveillance updates. The UI displays the actual model's clearance-effect report. Radio
does not replace measured surveillance positions or reinterpret a pilot's current-altitude
report as a target altitude. The existing deterministic conflict path remains in place.

## Research decisions and unresolved issues

| Issue | Evidence and decision |
|---|---|
| Shared-channel pilot/ATCO identification | [ATC speaker-role research](https://sesar.eu/sites/default/files/documents/sid/2022/paper_68.pdf) reports approximately 83% average accuracy for grammar-based identification and describes difficulties with noisy mixed VHF audio. The local role rules are unvalidated hints, not measured role probabilities. Mixed-channel ATCO hints require review; only correctly labelled upstream ATCO channels or reviewed captured instructions may apply intent. A trained and locally evaluated role/diarization solution remains unresolved. |
| Silence and radio noise producing text | Whisper can hallucinate text; [non-speech hallucination research](https://arxiv.org/abs/2501.11378) studies this failure. Live capture uses energy gating and the [documented Silero VAD integration](https://github.com/SYSTRAN/faster-whisper#vad-filter). VAD reduces non-speech inputs; it does not establish transcription correctness or solve overlapping speakers. |
| Audio capture timing and browser support | [AudioWorklet](https://developer.mozilla.org/en-US/docs/Web/API/AudioWorklet) processes audio separately from the main UI thread. Capture timestamps come from the audio clock. Browser [shared-audio support varies](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getDisplayMedia); missing audio or suspended/disconnected capture is reported instead of pretending to listen. |
| Overlap, very short inter-speaker pauses and receiver squelch | An energy/pause boundary is not a guaranteed speaker or push-to-talk boundary. No overlap separation or PTT integration is claimed. The installed model and heuristics need evaluation on the actual receiver/channel. |
| Speed and direct-to instructions | Extracted and recorded, but the existing trajectory code lacks wind/airspeed handling and a validated navigation-fix database. These actions do not adjust paths. No guessed dynamics or fix coordinates were added. |
| Pilot unable or mismatched readback | Reported in the transcript and clearance status. It does not replace an ATCO clearance or automatically choose a new flight path. How to model noncompliance uncertainty needs a validated policy; it remains unresolved. |
| Live surveillance missing or replaced by replay | Live audio cannot change replay predictions. This prevents today's radio from being attached to historical traffic. |

The model's confidence scores are ranking signals, not calibrated probabilities of a
correct instruction. The existing 0.85 clearance floor is retained. It is not lowered to
make a demonstration appear successful. A model or role hint that looks plausible is not
sufficient evidence to change this floor.

Transcriptions, clearances and radio decisions use the existing append-only database/audit
records. The current conversation view, readback status and active clearances are session
state; they are not restored as active intent after restart. Raw live audio is kept only
in bounded browser memory, not saved permanently. No receiver hardware or connected browser
was available to verify physical capture end to end during this implementation.

## Verification

```powershell
venv\Scripts\python.exe -m unittest ml_pipeline.tests.test_speech_workflow ml_pipeline.tests.test_radio_api -v
cd client
node --test src/lib/radioSegmenter.test.js
npm.cmd run build
```

The Python checks cover real extraction and clearance/path rules, mixed-channel uncertainty,
requests/readbacks, confidence rejection, review linkage/age, live/replay isolation, audio
validation/resampling and live silence rejection. API model/database calls are mocked where
needed; those tests are not an ASR accuracy benchmark. JavaScript checks cover segmentation,
pre-roll, bounded silence memory, squelch clicks and incomplete/continued transmissions.

On 2 November 2026, the 20 new Python checks, 24 existing unit checks and seven JavaScript
audio checks passed, and the production frontend build passed. The repository's ESLint
configuration could not load because `eslint-plugin-react` is missing from the existing
installation; no lint pass is claimed.

An installed synthetic radio clip also passed through the running live endpoint using
the actual fine-tuned model on CUDA, producing a transcript and extracted descent level.
Its uncertain role and replay surveillance prevented application, as intended. This is a
plumbing check using synthetic audio, not an accuracy result on live radio.

The full saved-model replay check produced
[archived `chain_check_20261102_100239.json` evidence](evaluations/clearance_extractor.md#source-register).
Its explicitly labelled oracle ATCO text reached clearance processing, the five-candidate
trajectory reports, conflict escalation and resolution checks. Candidate probabilities
remained normalized. In this particular replay the oracle 37,000 ft cap changed zero paths,
and the pair's conflict results stayed the same; this does not demonstrate an improvement
in conflict detection. The unit test separately exercises a cap that changes candidate
altitudes. No learned weights or operating thresholds were changed.
