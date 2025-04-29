# Verification

Local checks ran on 27 September 2026 with Python 3.12, Chromium 153 and FFmpeg. Browser responses are synthetic test inputs, not research findings.

## Results

**27 automated tests passed**, including the optional OpenCV, VADER and scikit-learn integration checks.

| Area | Verified behavior |
|---|---|
| Survey | Consent required, random assignment, saved zero rating, duplicate-safe retries, immutable study settings |
| Paired study | Own rating saved before interview; both measures retained; dashboard and CLI exports keep them separate |
| Interviews | Answer saved before provider call; failed follow-up and final inference retry; null scores; concurrent independent sessions |
| Researcher access | Protected results, transcript/frame inspection and exports; invalid condition/measure rejected; no scores in participant payload |
| Media | Byte-range playback, OpenCV sampling, codec validation, rejection of incomplete MP4, explicit valid-subset import |
| Analysis | Structured response validation, refusal handling, resume behavior, evidence hashes, separate model conditions, conservative legacy parsing |
| Comparison | Missing scores stay missing; repeated runs are not participants; paired inference comparison matches session AND video |

Four browser scenarios passed:

1. **Direct rating:** consent, MP4 playback, reload, all three videos, score zero, dashboard points, CSV and a 390px mobile survey.
2. **Interview:** saved conversation recovery, early finish, automatic finish, inferred-score label and conversation export.
3. **Paired:** draft score/text recovery, an intentionally lost network response after a successful save, no duplicate answer, measure switching, protected frame rendering, search, comparison CSV, mobile dashboard and blocked submissions for broken media in both stages.
4. **Supplied video:** the portrait clip plays, a synthetic response saves, the real transcript and six frames load in the researcher view, and no model score is invented when none exists.

The LaTeX/TikZ diagram compiles and has been visually checked. Dashboard and survey screenshots are from the running app.

## Supplied media

| Clip | Actual result |
|---|---|
| `part_46.mp4` | Valid H.264/AAC, 720 × 1600, 50.9 seconds. Played in Chromium. Local Whisper `tiny` produced 22 transcript segments and detected Finnish (`fi`); OpenCV sampled six frames. |
| `part_1 (2).mp4` | Incomplete MP4: `ffprobe` reported `moov atom not found`. Rejected before survey registration. Supply the complete original file to test it. |

Transcription execution succeeded; accuracy has not been manually validated. The native test environment used Whisper 20250625, CPU Torch 2.6.0 and Numba 0.61.2. An incomplete installed LLVM shared library initially caused a crash; restoring the full wheel library resolved it. This was an installation issue, not an inferred trust result.

Raw supplied videos, transcript text and sampled research frames are excluded from the public source package.

## Repeat the checks

```bash
python -m unittest discover -s tests -v
```

Optional processing checks skip when their dependencies are absent:

```bash
python -m pip install -e '.[enrichment]' opencv-python-headless
python -m unittest discover -s tests -v
```

Install FFmpeg for media registration. Browser tests need Playwright and OpenCV for the paired evidence check:

```bash
npm install --no-save playwright
npx playwright install chromium
PYTHONPATH=. python tests/run_browser.py
```

PowerShell: set `$env:PYTHONPATH='.'` before running the Python command. Optional variables: `CHROMIUM_EXECUTABLE`, `PLAYWRIGHT_MODULE`, and `SCREENSHOT_DIR`. The application itself has no Node dependency.

To test your own clip and its prepared evidence:

```bash
python -m videotrust register --input /path/to/video.mp4 --workspace data/media-test
python -m videotrust prepare --workspace data/media-test --whisper-model tiny --frames 6
PYTHONPATH=. python tests/run_real_video.py --video /path/to/video.mp4 \
  --prepared-workspace data/media-test
```

The real-video browser test uses a temporary study and discards its synthetic response.

## Still unverified

| Component | Limit |
|---|---|
| Live OpenAI interview, video assessment and embeddings | No API key available. Request contracts, validation and failure recovery use controlled provider responses. |
| YouTube / yt-dlp | Collection logic tested; no fresh external collection run. |
| Public hosting, Docker and recruitment load | Not deployed or load tested. |
| Other browsers / operating systems | Local browser checks used Linux Chromium only. |
| Scientific validity | Software tests do not validate transcript quality, the survey instrument or model trust judgments. |

GitHub Actions are configured but have not run remotely. The prepared repository is checked for secrets, unexpected data, clean final state, commit timestamps and a restorable Git bundle.
