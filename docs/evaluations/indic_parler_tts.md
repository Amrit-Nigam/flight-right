# ai4bharat/indic-parler-tts: evaluation and testing

Synthetic voice generation for training/demo; no objective TTS quality benchmark found. Script extraction recovery is not TTS accuracy.

[Latest comparison](../evaluation.md) · [Every original source and cleanup status](source_inventory.json)

This is the single maintained history for this model/component. Records preserve the original bytes, including every numeric field, trial, seed, protocol, selection and caveat. Shared reports are included in each relevant ledger. No fresh inference is implied by consolidation.


## Source register

| Original path | SHA-256 | Bytes |
| --- | --- | --- |
| ml_pipeline/reports/mumbai_scripts_20260925_175929.json | 540022bee402a1bae26f9db880c8844e0386d0be637699b2fa4769c6bdf0a829 | 3322 |

## Lossless evidence

Machine-readable JSON envelope. `content` is exact UTF-8 text or base64 bytes; numeric payloads remain unchanged, including historical JSON NaN. Use the maintenance script to verify or restore a source.

<!-- evaluation-evidence-v1 -->
```json
{
  "model": "indic_parler_tts",
  "records": [
    {
      "path": "ml_pipeline/reports/mumbai_scripts_20260925_175929.json",
      "sha256": "540022bee402a1bae26f9db880c8844e0386d0be637699b2fa4769c6bdf0a829",
      "bytes": 3322,
      "encoding": "utf-8",
      "content": "{\r\n  \"measured_at_utc\": \"2026-09-25T12:29:29.283626+00:00\",\r\n  \"transmissions\": 3757,\r\n  \"extractor_recovers_script_pct\": 98.99,\r\n  \"aircraft\": 856,\r\n  \"callsign_prefixes\": {\r\n    \"IGO\": 1516,\r\n    \"AIC\": 761,\r\n    \"AKJ\": 265,\r\n    \"AXB\": 231,\r\n    \"UAE\": 111,\r\n    \"ETH\": 58,\r\n    \"QTR\": 48,\r\n    \"ETD\": 44,\r\n    \"ABY\": 42,\r\n    \"SDG\": 42,\r\n    \"BAW\": 41,\r\n    \"BDA\": 33,\r\n    \"GFA\": 30,\r\n    \"LLR\": 29,\r\n    \"SVA\": 25\r\n  },\r\n  \"by_action\": {\r\n    \"TURN\": 1300,\r\n    \"SPEED\": 1034,\r\n    \"none\": 758,\r\n    \"DESCEND\": 507,\r\n    \"CLIMB\": 158\r\n  },\r\n  \"by_value_source\": {\r\n    \"observed settled track\": 1300,\r\n    \"standard phraseology value\": 1034,\r\n    \"no clearance (distractor)\": 758,\r\n    \"observed held level\": 665\r\n  },\r\n  \"by_role\": {\r\n    \"ATCO\": 3121,\r\n    \"PILOT\": 636\r\n  },\r\n  \"by_split\": {\r\n    \"train\": 3341,\r\n    \"val\": 416\r\n  },\r\n  \"examples\": [\r\n    {\r\n      \"callsign\": \"IGO607K\",\r\n      \"action\": \"SPEED\",\r\n      \"value\": 160.0,\r\n      \"value_source\": \"standard phraseology value\",\r\n      \"text\": \"ifly six zero seven kilo mumbai approach maintain one six zero knots\",\r\n      \"tts_text\": \"eye fly six zero seven kilo mumbai approach maintain one six zero knots\"\r\n    },\r\n    {\r\n      \"callsign\": \"AIC8DT\",\r\n      \"action\": \"SPEED\",\r\n      \"value\": 190.0,\r\n      \"value_source\": \"standard phraseology value\",\r\n      \"text\": \"air india eight delta tango mumbai approach speed one nine zero knots\",\r\n      \"tts_text\": \"air india eight delta tango mumbai approach speed one nine zero knots\"\r\n    },\r\n    {\r\n      \"callsign\": \"IGO2100\",\r\n      \"action\": \"CLIMB\",\r\n      \"value\": 30000.0,\r\n      \"value_source\": \"observed held level\",\r\n      \"text\": \"climbing flight level three zero zero ifly two one zero zero\",\r\n      \"tts_text\": \"climbing flight level three zero zero eye fly two one zero zero\"\r\n    },\r\n    {\r\n      \"callsign\": \"AIC1AF\",\r\n      \"action\": NaN,\r\n      \"value\": NaN,\r\n      \"value_source\": \"no clearance (distractor)\",\r\n      \"text\": \"air india one alfa foxtrot qnh one zero zero two\",\r\n      \"tts_text\": \"air india one alfa foxtrot qnh one zero zero two\"\r\n    },\r\n    {\r\n      \"callsign\": \"IGO1402\",\r\n      \"action\": \"DESCEND\",\r\n      \"value\": 29000.0,\r\n      \"value_source\": \"observed held level\",\r\n      \"text\": \"ifly one four zero two descend to flight level two nine zero\",\r\n      \"tts_text\": \"eye fly one four zero two descend to flight level two nine zero\"\r\n    },\r\n    {\r\n      \"callsign\": \"IGO355\",\r\n      \"action\": NaN,\r\n      \"value\": NaN,\r\n      \"value_source\": \"no clearance (distractor)\",\r\n      \"text\": \"ifly three five five squawk five three two three\",\r\n      \"tts_text\": \"eye fly three five five squawk five three two three\"\r\n    },\r\n    {\r\n      \"callsign\": \"IGO676V\",\r\n      \"action\": \"TURN\",\r\n      \"value\": 240.0,\r\n      \"value_source\": \"observed settled track\",\r\n      \"text\": \"right heading two four zero ifly six seven six victor\",\r\n      \"tts_text\": \"right heading two four zero eye fly six seven six victor\"\r\n    },\r\n    {\r\n      \"callsign\": \"CAL5686\",\r\n      \"action\": NaN,\r\n      \"value\": NaN,\r\n      \"value_source\": \"no clearance (distractor)\",\r\n      \"text\": \"dynasty five six eight six contact mumbai tower one one eight decimal one goodbye\",\r\n      \"tts_text\": \"dynasty five six eight six contact mumbai tower one one eight decimal one goodbye\"\r\n    }\r\n  ]\r\n}"
    }
  ]
}
```
