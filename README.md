# Trust-LLMHuman-VideoComparison

**What makes a video feel trustworthy?** 

**Do people and language models rely on the same cues?**

Here is a project I worked on during the Human Computer Interaction Course by Giulio Jacucci in Winter 2024 at the University of Helsinki. 

This is a complete frontend-backend survey software which lets people watch a video, give a trust rating, and explain their judgment in a short interview hosted by a chatbot. Separately, a language model assesses a transcript and sampled video frames. A researcher dashboard brings the scores, explanations and evidence together to understand the differences in trust and, if **people and language models rely on the same cues which accessing trust!**

The aim was to investigate **how trust is formed**: the role of a familiar publisher, a verification badge, a formal setting, the substance of a claim, or information missing from the model's input etc. 

I would be happy to allow other researchers to adapt it to their own studies; however, if this project is useful for your research, please get in touch. I would be interested in discussing the research question, a possible collaboration, or customization. At present, I do not have funding or time to develop features on request; help with adaptation depends on availability and interest! 

The software is released under the **[MIT license](LICENSE)**. Please also credit the project when you use or adapt it in research; Forking and reuse are permitted under the license. Contact and collaboration is encouraged. 

[Quick Test](#quick-try-with-everything-preloaded) · [Run a live pilot](#run-a-live-pilot) · [Design a study](#design-a-study) 

## An example

This examples uses only **`part_46`**, a 50.9-second Finnish news/debate clip.

| Assessment | Score | What shaped the judgment |
| --- | ---: | --- |
| Participant's own rating | **9 / 10** | Recognition of Iltalehti and the account's visible verification badge, formal presentation and a moderated discussion. |
| Independent video assessment | **4 / 10** | The model described a fragmented transcript, missing context and insufficient supporting evidence. |
| Difference | **+5 points** | Check what caused this difference |

This suggests that maybe **recognizing the source can change how people and models interpret the same content?**

The example does not fully understand the cause of the difference. Source branding is visible in some sampled frames, we cannot conclude that the model never saw it. It may have missed or given less weight to those cues. 

## Here is the participant's answers (+ Surevy and dashboard UI)

![Participant rating and explanation](assets/participant-rating.png)

![Participant interview and reasons for trusting the source](assets/participant-explanation.png)

![Recorded model assessment and its limitations](assets/model-explanation.png)

![Automatic transcript and six sampled frames](assets/transcript-and-frames.png)

This is only a fictional example! 

## Quick Try with Everything Preloaded

**Start here.** You need Python 3.11 or newer. It includes the video, a prepared transcript, six frames and the recorded model example.

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

Keep the terminal open. It prints the survey address, researcher address and a **researcher token**. The application runs on your own computer.

### 3. Try the participant side

Open **[http://127.0.0.1:8000](http://127.0.0.1:8000)** and try/test. 

The offline interview uses fixed questions and makes no model calls. It saves your answers but leaves the inferred interview score empty.

![Interview after a participant has explained their initial impression](assets/interview-followup.png)

### 4. Try the researcher side

Open **[http://127.0.0.1:8000/researcher](http://127.0.0.1:8000/researcher)** in another tab. Paste the researcher token from the terminal.

- Select `part_46` and use **Responses**, **Model runs** and **Evidence** to read both explanations and inspect the transcript and frames.
- Use **Export responses**, **Export comparison** or **Export interviews** to save CSV or JSON files.

Responses stay in `data/demo-part46-paired/` by default. A new researcher token is printed each time the server starts.

## Run a live pilot

This creates a **separate workspace** and generates new model assessments. It does not copy the recorded score or demo responses.

### 1. Install the analysis tools

From the project folder, with the same Python environment:

```bash
python -m pip install ".[analysis]"
```

Install **[FFmpeg](https://ffmpeg.org/download.html)**, including `ffprobe`

Whisper runs locally. The first transcription downloads its model; this can take time and disk space.

### 2. Set your API key

Obtain a key from your own [OpenAI API account](https://platform.openai.com/api-keys). Live video assessments and interviews use that account's API billing. The key is read by the Python server and is never sent to the participant browser.

macOS/Linux:

```bash
export OPENAI_API_KEY="your-api-key"
```

### 3. Prepare the example

```bash
trust-video example
trust-video prepare --whisper-model base --language fi --frames 6
```
This registers the bundled clip in `data/study/` and sets up a paired pilot.

### 4. Assess the video, then open the study

```bash
trust-video analyze --model gpt-4o-mini --evidence-mode video_only
trust-video serve
```

Open the printed survey and researcher addresses just as in the offline demo. This time, interview follow-ups and interview interpretation call the live model. The independent video assessment never receives participant responses. Its score is not shown to participants.

## Design a study

The three measures answer different questions:

| Measure | Input | Meaning |
| --- | --- | --- |
| Direct participant rating | A person's own 0–10 selection | How much that person reports trusting the video. |
| Interview inference | That person's written answers | An LLM's interpretation of expressed trust; inconclusive answers can remain unscored. |
| Independent video assessment | Title, transcript, sampled frames and the chosen context | The model's judgment from the supplied evidence. |


![Black-and-white study workflow](assets/workflow.png)

### How to use your own videos

```bash
trust-video register --input "path/to/your/videos" --workspace data/my-study --response-mode paired
```

Use H.264 MP4 with AAC/MP3 audio, or VP8/VP9 WebM with Opus/Vorbis audio. Registration checks metadata and decodes the first frame; pilot full playback before recruitment. A single video path also works. Invalid files are reported; `--skip-invalid` explicitly allows a valid subset.

Before the first `serve`, edit `data/my-study/study.json`: study title, contact, consent wording/version, retention and withdrawal information, number of videos per session, response mode and interview length. Then use `prepare`, `analyze` and `serve` with `--workspace data/my-study` on each command.
