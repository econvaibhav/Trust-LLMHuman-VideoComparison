# Trust-LLMHuman-VideoComparison

**What makes a video feel trustworthy—and do people and language models rely on the same cues?**

This research toolkit lets people watch a video, give a trust rating, and explain their judgment in a short interview. Separately, a language model assesses a transcript and sampled video frames. A researcher dashboard brings the scores, explanations and evidence together.

The aim is to investigate **how trust is formed**: the role of a familiar publisher, a verification badge, a formal setting, the substance of a claim, or information missing from the model's input. A disagreement is a starting point for investigation, not a verdict about who is right.

Originally developed for a Human–Computer Interaction course at the **University of Helsinki**, the project has since been extended by **Vaibhav Agarwal** so that other researchers can adapt it to their own studies.

[Try it locally](#try-it-locally) · [Run a live pilot](#run-a-live-pilot) · [Design a study](#design-a-study) · [Technical details](#technical-details) · [Contact and credit](#contact-and-credit)

![Researcher dashboard from the part_46 pilot: participant 9, model 4, gap 5](assets/study-results.png)

## A real example: one video, two judgments

The examples use just **`part_46`**, a 50.9-second Finnish news/debate clip. In the author's exploratory pilot:

| Assessment | Score | What shaped the judgment |
| --- | ---: | --- |
| Participant's own rating | **9 / 10** | Recognition of Iltalehti, the account's visible verification badge, formal presentation and a moderated discussion. |
| Independent video assessment | **4 / 10** | The model described a fragmented transcript, missing context and insufficient supporting evidence. |
| Difference | **+5 points** | Participant rating minus model rating. |

This suggests a useful question: **does recognizing the source change how people and models interpret the same content?**

The example does not establish the cause of the difference. Source branding is visible in some sampled frames, so we cannot conclude that the model never saw it. It may have missed or given less weight to those cues. The automatic Finnish transcript also contains errors, which offer another plausible explanation. One participant and one model run cannot establish a general pattern.

<details>
<summary>See the participant's explanation, model reasoning and evidence</summary>

![Participant rating and explanation](assets/participant-rating.png)

![Participant interview and reasons for trusting the source](assets/participant-explanation.png)

![Recorded model assessment and its limitations](assets/model-explanation.png)

![Automatic transcript and six sampled frames](assets/transcript-and-frames.png)

These are screenshots of the author's actual pilot. The offline demo contains the model score and wording transcribed from the screenshot, labelled **recorded example**. The original API response and complete run metadata were not supplied, so that excerpt is not a full replication record. The bundled transcript and frames were prepared locally from the same clip. They are not presented as a recovered API request.

The demo starts with no participant responses. Your own rating is collected afresh; the earlier rating of 9 is not inserted into your data. A fresh model run may produce a different score.

</details>

## Try it locally

**Start here.** You need Python 3.11 or newer; Python 3.12 is a straightforward choice. The demo needs no API key, FFmpeg, GPU, Node.js or paid service. It includes the video, a prepared transcript, six frames and the recorded model example.

### 1. Download and open the project

On this repository's GitHub page, choose **Code → Download ZIP**, then extract it. Open a terminal in the extracted folder—the one containing `README.md` and `pyproject.toml`.

### 2. Install and start

**macOS or Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
trust-video demo --paired
```

**Windows — PowerShell**

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\trust-video.exe demo --paired
```

On Windows, use `.\.venv\Scripts\trust-video.exe` wherever later instructions say `trust-video`, and `.\.venv\Scripts\python.exe` wherever they say `python`. This avoids changing PowerShell's execution policy.

Keep the terminal open. It prints the survey address, researcher address and a **researcher token**. The application runs on your own computer.

### 3. Try the participant side

Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)**.

1. Read the study information and agree to participate.
2. Watch `part_46`, choose a score from 0 to 10, and optionally explain why.
3. Save the rating, then answer the interview questions. You can finish after your first answer.
4. Look for the confirmation that your responses have been saved.

The offline interview uses fixed questions and makes no model calls. It saves your answers but leaves the inferred interview score empty.

![Interview after a participant has explained their initial impression](assets/interview-followup.png)

### 4. Try the researcher side

Open **[http://127.0.0.1:8000/researcher](http://127.0.0.1:8000/researcher)** in another tab. Paste the researcher token from the terminal.

- Leave **Participant measure** on **Direct participant rating** to compare your score with the recorded model score of 4.
- Select `part_46` and use **Responses**, **Model runs** and **Evidence** to read both explanations and inspect the transcript and frames.
- Use **Export responses**, **Export comparison** or **Export interviews** to save CSV or JSON files.

If you enter 9, the displayed difference should be **+5**. If you choose another score, the difference should change accordingly. Selecting interview inference in an offline demo shows an unscored response; it does not create a numeric judgment.

### 5. Stop, resume or start fresh

Press **Ctrl+C** in the terminal to stop. Run the same command to resume the saved workspace. Reloading the participant tab preserves its session and draft answers. Open a private browser window to try another participant session.

For a fresh demo, use a new folder:

```bash
trust-video demo --paired --workspace data/another-demo
```

Responses stay in `data/demo-part46-paired/` by default. A new researcher token is printed each time the server starts. Add `--port 8001` if port 8000 is already in use.

<details>
<summary>Other demo modes and Docker</summary>

```bash
trust-video demo              # Direct rating only
trust-video demo --interview  # Interview only
```

Each mode has its own default workspace. The existing `videotrust` command and `python -m videotrust` also work.

If you already use Docker:

```bash
docker build -t trust-video .
docker run --rm -p 127.0.0.1:8000:8000 -v trust-video-data:/data trust-video
```

The container starts the paired offline demo. The named volume keeps responses across restarts. Docker is optional; the Python installation is the primary tested route.

</details>

## Run a live pilot

This creates a **separate workspace** and generates new model assessments. It does not copy the recorded score or demo responses.

### 1. Install the analysis tools

From the project folder, with the same Python environment:

```bash
python -m pip install ".[analysis]"
```

Install **[FFmpeg](https://ffmpeg.org/download.html)**, including `ffprobe`, and check that both commands work:

```bash
ffmpeg -version
ffprobe -version
```

For example, Ubuntu/Debian users can run `sudo apt install ffmpeg`; macOS users with Homebrew can run `brew install ffmpeg`. Windows builds are linked from FFmpeg's download page. Restart your terminal after adding FFmpeg to PATH.

Whisper runs locally. The first transcription downloads its model; this can take time and disk space. A CPU is sufficient for a short pilot.

### 2. Set your API key

Obtain a key from your own [OpenAI API account](https://platform.openai.com/api-keys). Live video assessments and interviews use that account's API billing. The key is read by the Python server and is never sent to the participant browser.

macOS/Linux:

```bash
export OPENAI_API_KEY="your-api-key"
```

Windows PowerShell:

```powershell
$env:OPENAI_API_KEY = "your-api-key"
```

The `.env.example` file lists supported settings; `.env` files are not loaded automatically.

### 3. Prepare the example

```bash
trust-video example
trust-video prepare --whisper-model base --language fi --frames 6
```

This registers the bundled clip in `data/study/` and sets up a paired pilot. Before analysis, review the transcript in `data/study/evidence/` against the audio. Successful transcription does not mean accurate transcription. If the transcript needs improvement, try `--whisper-model small --force`, or use a separately documented human-corrected transcript in a new study workspace.

### 4. Assess the video, then open the study

```bash
trust-video analyze --model gpt-4o-mini --evidence-mode video_only
trust-video serve
```

Open the printed survey and researcher addresses just as in the offline demo. This time, interview follow-ups and interview interpretation call the live model. The independent video assessment never receives participant responses. Its score is not shown to participants.

A useful pilot check is: video plays; rating survives reload; interview answers are saved; the dashboard displays a fresh model run; both export files and explanations match what you entered. A score different from 4 is a possible new result, not an installation failure.

For another pilot, add the **same new `--workspace data/pilot2`** to every command above. Existing response data is never overwritten.

## Contact and credit

**Vaibhav Agarwal · [vaibhav.agarwal@tum.de](mailto:vaibhav.agarwal@tum.de)**

If this project is useful for your research, please get in touch. I would be interested in discussing the research question, a possible collaboration, or customization. I do not have dedicated funding or time to develop features on request; help with adaptation depends on availability.

The software is released under the **[MIT license](LICENSE)**. Copies and substantial portions must retain the copyright and license text. Please also credit the project when you use or adapt it in research; [CITATION.cff](CITATION.cff) provides citation metadata. Forking and reuse are permitted under the license. Contact and collaboration are encouraged, not additional license conditions.

The bundled news clip and third-party footage, logos and platform elements visible in screenshots are outside the software license. The clip visibly carries Iltalehti branding; inclusion does not transfer rights to the underlying content or imply endorsement. Check the permissions needed for your own reuse or study distribution.
