# Source recovery

Updated 25 September 2026 using the complete supplied archive. The two files named `OneDrive_4_25-09-2026.zip` and `OneDrive_4_25-09-2026(1).zip` have identical SHA-256 hashes. `docs/source-inventory.csv` records all 58 entries from the complete archive. Earlier archives and checksums remain documented in `archive-checksums.json`.

## What survived

| Material | Count / interpretation |
|---|---|
| English records with classification and topics | 183 |
| Saved video summary records | 394 unique filenames |
| English visual summaries | 182 usable |
| English metadata / comments | 115 / 105 records |
| English trust evaluations | 3,294 blocks in 18 logs |
| Temperatures 0, 0.5, 1 | Five runs each, 183 blocks per run |
| Temperature 2 | Three runs, 183 blocks per run |
| Structurally accepted / flagged | 2,730 / 564 |
| Historical interviews | Seven conversation sections; no reliable video linkage |
| Original source | 17 Python files including an empty `video_description.py`, plus one notebook |
| Original video media | Not supplied |
| Original application | Backend archive empty; main frontend source missing |

## Original work and current implementation

| Original source | Current responsibility |
|---|---|
| `full_automation.py` | `collect.py`: API collection, retained-video accounting, metadata, comments, downloads |
| `whisper_dir.py`, Hindi transcription test | `media.py`: language-selectable Whisper, timestamps and hashes |
| `language_filtering.py`, identical `full_python.py` | Preserved references; preparation records detected language; no automatic language exclusion |
| `combining_jsons.py`, `hindi_jsoncombine.py` | `legacy.py`: English corpus import with exact filename identity |
| `topic_modelling.py` | `enrich.py`: normalized embeddings and seeded K-means |
| `topology_videos.py` | `enrich.py`: format classification from sampled frames |
| `main_trust_detection.py` | `llm.py`: three explicit evidence conditions and validated JSON |
| `python_chatgpt_integrate.py` | `interview.py`: linked, resumable browser interviews and separate trust inference |
| `streamlit_test.py`, surviving frontend HTML | New `web/`, `server.py`, `storage.py` interface and collector |
| `video_description.py` | Empty original; new summary stage implemented in `enrich.py` |
| Image, clothing, random-number experiments and emotion notebook | Preserved reference material; not part of the trust pipeline |

The old `image_to_text_openai.py` describes superhero images. It is **not** the missing video-summary generator. The old `topology_videos.py` samples about every three seconds for format classification; the rebuild deliberately uses a bounded number of evenly spaced frames. These are documented implementation choices, not exact reproductions of missing historical components.

Original script text is preserved as `.txt` reference files so unsafe hardcoded paths and outdated APIs do not run accidentally. Ten embedded credential occurrences were redacted from the complete archive's source files. `credentials.txt` is excluded altogether. The earlier surviving frontend reference remains available.

## Historical results

The parser accepts field structure, not semantic correctness. Every temperature-2 result is flagged; other malformed or incomplete fields are also flagged. Raw output is retained in the private recovery workspace for review. Historical analyses are not automatically pooled with prospective runs: exact prompts and model snapshots were not logged per run.

The supplied conversations concern participant impressions, and the original LLM inferred a trust score. They are not direct numeric participant ratings. The new interview records persist session ID, video ID, request ID, turn, model metadata and assessment provenance. Historical conversations stay unlinked rather than guessing which video they refer to.

For an already-normalized private workspace, keep `catalog.json`, `legacy_analyses.jsonl`, `legacy_ratings.csv`, `recovery_statistics.json`, and `unlinked_interviews.txt` together. Restore your original video files before serving it. Recovery refuses a nonempty destination to protect existing responses.
