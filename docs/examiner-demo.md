# Examiner demonstration (under ten minutes)

Start with `py -3.13 start.py --mode examiner` (or use the existing environment:
`venv\Scripts\python.exe start.py --mode examiner --use-current-python`). Open
http://127.0.0.1:5173. Both services run locally; no radio transmission exists.
Use **Open presentation controls**, then **Start 9-minute presentation** when ready to present.
The eight-minute script below leaves one minute for questions before the nine-minute
hard stop, and a further minute below the ten-minute examiner limit. Start after
models finish warming. Rehearse microphone permission and speaker volume beforehand.

The timer uses wall time, not accelerated aircraft time. At nine minutes the server
freezes scenario progression and automatic movement. It does not close the page or
erase records. Reset starts a separate rehearsal/session; it is not a way to extend
the same presentation. The examiner's conversation and speaking pace remain human
activities; follow the running order and stop the presentation when the timer ends.

| Wall time | Show and say | Actions |
| --- | --- | --- |
| 0:00–0:30 | Synthetic traffic, real software/model pipeline; controller retains authority. | Start timed demo. Point out SYNTHETIC label, UTC and model readiness. |
| 0:30–1:15 | A flight strip follows Clearance → Ground → Tower; surface movement is generated because real ground data is unavailable. | Select IGO101. In Clearance assume strip, enter runway 27 / illustrative taxi route; offer to Ground, switch position, acknowledge; repeat to Tower. Advance 60s once to show taxi. |
| 1:15–2:15 | Speech becomes transcript and a matched callsign. Pilot requests cannot issue clearances. | Expand Speech, choose Pilot, record “Indigo one zero one, request departure”, stop. Show text/match. If room audio fails, use Transcribe pilot sample (fresh inference). |
| 2:15–3:00 | Takeoff requires approval; approved command has playable/downloadable WAV. Motion and altitude then change. | Next chapter → approve takeoff. Expand Approved command audio; play a few seconds and download. Collapse it; Advance 60s three times to see 5,000 ft. |
| 3:00–3:45 | Controller altitude intent and pilot readback checks. | In Speech choose ATCO and record “Indigo one zero one, climb to five thousand feet”. Then Pilot: “Indigo one zero one, climbing to five thousand feet”. If correction is needed, use labelled reviewed text. An optional four-thousand-foot readback shows mismatch. |
| 3:45–4:30 | Runway occupied; go-around; strip manager defers arrival readiness and recalculates. | Next chapter: AIC202 final and DEMO01 on runway. Approve go-around; open Sequence. IGO303 now precedes AIC202; explain educational 120-second gap. Advance 60s shows climb-away to 2,700 ft (next 30s reaches 3,000). |
| 4:30–6:00 | Real conflict detection, explanation and ranked resolution, with approval before command audio. | Next chapter; Step +10s twice. Open ML, inspect IGO401/AIC402 alert/explanation/options. Pause if playing; approve chosen model option in demo controls. Download/play its WAV in Approved command audio. |
| 6:00–7:00 | Simulated crew compliance, followed by fresh model reassessment. Approval alone does not clear the alarm. | Advance 60s three times. Inspect altitude/heading change and ML alert state. The existing manoeuvre simulator includes response delay and rate limits. |
| 7:00–8:00 | Recovered arrival lands/vacates; close movement and show audit history. | Next chapter; Advance 60s twice (capped at 100s). AIC202 is stationary on ground. Sequence → Close out AIC202 → Record close-out. Open closed history, then logs and JSON export. |
| 8:00–9:00 | Buffer / brief questions. | Stop or use remaining time to show sequence edit/undo, pinning, typed communication, takeover or emergency priority. Return planner to normal before scenario approval. |

Traffic now starts moving automatically, with reports every ten seconds throughout all
chapters. There are 16 aircraft initially (10 airborne, six on ground), 11 mixed
arrival/departure movements, and 18 aircraft during the main conflict chapter.
Arrival holding patterns and overflights keep moving; ground aircraft may correctly
remain at a stand or holding point. Chapters no longer freeze the traffic clock.

Use **Pause** before reviewing/approving a command or changing chapter. Use
**Step +10s** or **Advance 60s** for fast paused inspection, then **Play** to resume
continuous movement. The nine-minute wall-time cap still stops the presentation.
Normal route/aircraft names are shown without repeated synthetic/demo labels.

The background IGO918/AIC119 encounter runs through the actual model chain from the
start. Open ML to inspect forecasts, watch/alert state and explanations. After a
confirmed offer, Pause and open **Traffic conflict resolutions** in presentation
controls. **Approve traffic resolution** generates the command/audio and applies the
manoeuvre to those aircraft without changing the main chapter. This optional branch
can replace the later main conflict explanation to keep the spoken demo under nine
minutes. The 11-flight queue can be recalculated with **Sequence ? Recalculate
sequence**. After the go-around, **Runway recovery changes** shows before/after order;
the Airport timeline also shows planned arrival/departure slots.

The start/reset action creates a fresh traffic/session scope with its own strips,
plan and approvals. Previous audit and planning records are retained. Examiner mode
has a separate SQLite store under `demo/.runtime/examiner/`, disables route/intent
network feeds in the launcher, and cannot switch into live traffic through the mode
API. The ordinary live/replay startup remains available separately.

To switch back to live, stop the demo's backend/frontend (Ctrl+C in its launcher),
then run `py -3.13 start.py --mode live`. The existing local OpenSky credentials
are read as before. `--mode auto` retains live-with-replay-fallback behavior and
`--mode replay` retains recorded traffic. Examiner runtime flags exist only in its
child process; they are not written to `.env` and do not carry into the next launch.
The default invocation remains replay, as before this change.

**Review resolution** shows the pilot command for the selected option. Click
**Listen to command** to play it locally, or **Download preview WAV** after the audio
loads. Selecting another option changes the command. Approve the command separately
in the presentation controls when you are ready to demonstrate the manoeuvre.

## What the demonstration establishes

Ground, departure, missed approach and recovery positions are explicitly synthetic.
They are illustrative trajectories, not surveyed taxi paths, actual Mumbai procedures
or validated terminal/surface conflict detection. DEMO01 is a scripted runway hazard;
the en-route model is never described as detecting it. Runway planning uses the
existing educational 120-second resource constraint and earliest-ready heuristic,
not an operational optimum. The go-around updates the missed arrival's earliest
ready time, preserves its history, and recalculates the existing queue.

The conflict chapter uses two generated, ten-report-warmed aircraft at FL300 through
the actual served trajectory/multipath/classifier, alert gate and resolution engine.
No scripted alert or synthetic confidence is substituted. If no option is offered,
the UI reports that and blocks resolution approval. Chosen commands are rebuilt
server-side from current model options; session/revision/content checks reject stale
or duplicate approval. Approved resolution intent is recorded and only the synthetic
aircraft obeys it. An urgent alert clears only through subsequent assessment.

Microphone, uploaded WAV and generated sample all run actual ASR. Review is labelled
as corrected text and never presented as successful recognition. Pilot/unknown roles
retain existing acceptance/readback gates. Command WAVs use the offline Windows
System.Speech voice and are available only after approval. Audio is local playback /
download; no pilot/radio connection or transmission is implemented. Other operating
systems return an explicit unsupported-generation error. Windows speech voices must
be installed; no cloud account or API key is needed.

The UI also retains typed instructions, transcript-to-plan updates, strip annotations
and handoffs, sequence drag/arrows/undo/pins, emergency/takeover, forecast and model
readiness, alert explanation, audit search/export, responsive views and themes. These
optional branches do not all fit into eight minutes; the running order covers the
major end-to-end workflows. Login, operational surface routing, stop bars, wake
separation, actual radio delivery and certified autonomous control are not implemented.

## Verification

`scripts/check_examiner_demo.py` runs actual models, synthetic movement and fresh ASR
in isolated stores, retaining raw attempts under `checkpoints/examiner_20261118/`.
`python -m unittest ml_pipeline.tests.test_examiner_demo` covers mode isolation,
stale/duplicate approvals, readiness recovery, time caps and the presentation budget.
Chromium frontend evidence and the recorded running-time result are in the same
checkpoint directory; durable summary/hash references are registered in the existing
model ledgers. These are integration checks, not new accuracy or inference-latency
benchmarks. Model weights, deployed selections and published accuracy remain unchanged.
