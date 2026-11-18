# Demo assets and attribution

These assets are for an academic decision-support prototype, not operational ATC.
Training is unnecessary to run them. The original corpora and private credentials
are not included. The source code's availability does not relicense third-party data.

## Aircraft replay and context

Contains information from **adsb.lol and its contributors**, made available under the
[Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
The derived replay/context database in `demo/replay` and `demo/context` is provided
under ODbL 1.0 as well. Preserve the attribution and share-alike terms when sharing it.
Source: [adsb.lol daily archive](https://github.com/adsblol/globe_history_2026),
[provider licence](https://www.adsb.lol/docs/privacy-license).
`provenance.json` records the interval, transformations and original trace hashes.
Measured aircraft positions are bucketed at ten seconds and units converted; no flight
paths are invented. This limited sample does not reproduce the previous OpenSky demo
exactly and has no newly claimed accuracy score.

**No OpenSky raw recording is distributed here.** Its access and sharing restrictions
are at https://opensky-network.org/about/terms-of-use. Optional live mode uses the
user's own credentials and is subject to the provider's terms and availability.

## Reference data

- Airport/runway CSV: **OurAirports contributors**, public domain,
  https://ourairports.com/data/.
- Route lookup facts: **adsbdb**, https://www.adsbdb.com/; cached origin/destination
  lookups, not verified flight plans. Missing entries remain unknown.
- Airport weather archive: **Iowa Environmental Mesonet**,
  https://mesonet.agron.iastate.edu/request/download.phtml.
- Airline radio names: **FAA JO 7340.2**,
  https://www.faa.gov/air_traffic/publications/atpubs/cnt_html/chap3_section_3.html,
  and **OpenFlights**, https://openflights.org/data.html (Open Database License).
  The OpenFlights cache retains its provider's database terms.

## Speech model and practice recordings

The included speech runtime is Flight Right's validation-selected `uniform_soup3`,
based on **OpenAI Whisper-small** (MIT,
https://github.com/openai/whisper/blob/main/LICENSE), adapted using ATCOSIM and
UWB-ATCC plus the documented generated-voice continuation. Exact lineage, hashes,
experiments and limitations: `docs/evaluations/asr_small_atc_p1.md`.
**Non-commercial research/education only for this trained bundle.** UWB-ATCC is
Attribution-NonCommercial-ShareAlike 4.0; preserve that restriction and attribution
for UWB-derived material. Source authors: Lubos Smidl, Jan Svec, Daniel Tihelka,
Jindrich Matousek, Jindrich Romportl and Pavel Ircing, *Air traffic control
communication speech corpora and their use for ASR and TTS development* (2019).
Dataset: https://lindat.mff.cuni.cz/repository/handle/11858/00-097C-0000-0001-CCA1-0;
licence: https://creativecommons.org/licenses/by-nc-sa/4.0/.
ATCOSIM: https://www.spsc.tugraz.at/databases-and-tools/atcosim-air-traffic-control-simulation-speech-corpus.html.

The three included WAVs are **synthetic practice audio**, generated with
**AI4Bharat Indic Parler-TTS** (Apache 2.0,
https://huggingface.co/ai4bharat/indic-parler-tts), with the project's simulated
radio channel using UWB noise. Treat these UWB-derived clips as CC BY-NC-SA 4.0.
They are labelled synthetic in the UI. No ATCO2 test recordings, real pilot voices,
private radio captures, training-audio cache or cached recognition scores are shipped.

The trajectory/classifier model files are the existing served project artifacts,
not newly trained replacements. Their provenance and limitations remain in the
model ledgers under `docs/evaluations/`. They do not constitute a redistributable
copy of the original training datasets.
