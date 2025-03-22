# Study method

The unit of comparison is the same **video**, identified by stable ID and media hash. A workspace freezes the stimulus catalog, consent version, session length and participant mode. Participants receive a random sample/order without seeing model judgments.

## Participant measures

- **Direct rating:** participant-selected integer 0–10; optional confidence and rationale. Client playback time is a convenience measure, not proof of attention.
- **Interview inference:** an LLM estimates a 0–10 score from a conversation. It does not view the video or independent model scores. Inconclusive evidence produces null, which does not enter score means. The conversation and inference provenance are retained. Demo interview scores are fixed synthetic fixtures.

A workspace uses `direct`, `interview`, or `paired` mode. Paired mode records the direct score before the interview, and keeps the two measures separate. The interview model never receives the direct score. Report which measure was used. LLM interpretation of participant answers is not an independent human numeric rating. Model assumptions can affect both interview interpretation and video assessment. The interviewer can also influence how a participant articulates an impression.

## Video assessments

`video_only` uses title, transcript and sampled images. `metadata_comments` adds metadata and comments. `legacy_enriched` uses textual representations including a generated visual summary, presentation format, arbitrary topic-cluster label, and comment sentiment. It does not receive raw frames at the final trust stage. The conditions are kept separate, as are requested model, resolved model, temperature, prompt hash/version and corpus evidence fingerprint. Re-preparing evidence creates a separate comparison condition.

Whisper transcripts may be wrong; sparse frames miss events; neither is equivalent to a person's complete audiovisual exposure. VADER's English lexicon does not establish commenter intent or validate a claim. Likes and comments are reception signals, not evidence of truth. K-means labels are arbitrary and should not be interpreted as ordered topics. There is no independent fact-checking stage.

## Comparisons

For each condition and video, show the participant score mean, sample size and sample SD alongside the model mean, repeat count and sample SD. The signed gap is participant mean minus model mean. Mean absolute gap averages absolute video-level gaps. Pearson correlation is reported only for at least three matched videos with nonzero variance on both axes. Agreement is not accuracy, and correlation is not agreement.

Repeated model runs are not additional human participants. Sessions are not verified unique people, and the interface does not prevent one person creating multiple sessions. Analyses are descriptive, without causal claims or automatic significance tests. Report missingness, recruitment, assignment, exposure differences and historical review exclusions.

The paired agreement panel matches by **session and video**. Its signed gap is inferred score minus direct rating; its absolute gap uses the same matched pairs. Missing inferred scores are excluded and reported as missing. Rating first may anchor the interview, so this panel checks agreement under that ordering, not an independent validation of the instrument.

## Reproducibility

Live model records include requested/resolved models, prompt and evidence hashes, temperature, repeat index, usage, response ID and raw validated output. Enrichment records visual model provenance and the corpus-level clustering signature. Interview turns and assessments are linked to the frozen study. A repeated completed request is not counted twice. Temperature zero does not guarantee deterministic model responses.

Historical records lack some of these identifiers; do not silently pool them with new runs. The editable workflow diagram shows the implemented paths for linked responses.

## What the pilot can establish

The local pilot checks stimulus playback, response persistence, measure separation and a traceable evidence pipeline. A successful Whisper run establishes execution, not transcript accuracy. Inspect a sample against the audio, especially for Finnish and other languages in the corpus. A tiny model is useful for a smoke test; choose and evaluate the transcription model before collecting research results.

Before interpreting trust differences, review neutral interview wording, use enough videos and respondents, and manually compare inferred scores with paired direct ratings. Keep the same evidence condition and model snapshot within a comparison. Human viewers hear prosody and see continuous video; sampled frames plus text provide a different exposure. Run a real-provider pilot before recruitment, and report that difference when interpreting gaps.
