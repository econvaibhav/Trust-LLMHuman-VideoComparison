"use strict";
const $ = (id) => document.getElementById(id);
let token = sessionStorage.getItem("vt-session") || "",
  mode = "direct",
  current = null,
  busy = false,
  mediaReady = false,
  watchSeconds = 0,
  lastTick = null,
  pending = null;
const uid = () =>
  crypto.randomUUID
    ? crypto.randomUUID()
    : Array.from(crypto.getRandomValues(new Uint8Array(16)), (n) =>
        n.toString(16).padStart(2, "0"),
      ).join("");
const draftKey = () =>
  current && !current.done
    ? `vt-draft:${token}:${current.video.video_id}`
    : null;
function draft() {
  try {
    return JSON.parse(sessionStorage.getItem(draftKey()) || "{}");
  } catch (_) {
    return {};
  }
}
function saveDraft() {
  const key = draftKey();
  if (!key) return;
  const radio = document.querySelector("input[name=trust]:checked");
  sessionStorage.setItem(
    key,
    JSON.stringify({
      score: radio ? Number(radio.value) : null,
      rationale: $("reason").value,
      confidence: $("confidence").value,
      answer: $("interview-answer").value,
      watchSeconds,
      pending,
    }),
  );
}
async function api(path, body) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  const r = await fetch(path, {
    method: body ? "POST" : "GET",
    headers,
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const d = await r.json();
  if (!r.ok) {
    const e = new Error(d.error || "Please try again.");
    e.status = r.status;
    throw e;
  }
  return d;
}
function error(e) {
  $("status").textContent = e.message;
  $("status").classList.add("error");
}
function clearError() {
  $("status").textContent = "";
  $("status").classList.remove("error");
}
function screen(name) {
  for (const s of ["welcome", "task", "done"]) $(s).hidden = s !== name;
}
function controls() {
  const hasScore = !!document.querySelector("input[name=trust]:checked");
  $("submit").disabled = busy || !mediaReady || !hasScore;
  $("submit").textContent = busy
    ? "Saving…"
    : pending
      ? "Retry save"
      : "Save & continue";
  for (const el of $("rating-form").querySelectorAll("input,textarea,select"))
    el.disabled = busy || !!pending;
  const state = current?.interview;
  const canAnswer = state && !state.ready_to_finish && !state.pending_question;
  $("send-answer").disabled = busy || !mediaReady || !canAnswer;
  $("interview-answer").disabled = busy || !mediaReady || !canAnswer;
  $("finish-interview").disabled = busy || !mediaReady || !state?.answered;
  $("retry-question").disabled = busy || !mediaReady;
}
function updateWatch() {
  const now = performance.now();
  if (lastTick !== null && !$("video").paused && !document.hidden)
    watchSeconds += Math.min((now - lastTick) / 1000, 2);
  lastTick = now;
  saveDraft();
}
$("video").addEventListener("timeupdate", updateWatch);
$("video").addEventListener("playing", () => {
  lastTick = performance.now();
});
$("video").addEventListener("pause", () => {
  lastTick = null;
  saveDraft();
});
$("video").addEventListener("canplay", () => {
  mediaReady = true;
  $("media-error").hidden = true;
  controls();
});
$("video").addEventListener("error", () => {
  mediaReady = false;
  $("media-error").hidden = false;
  controls();
});
document.addEventListener("visibilitychange", () => {
  lastTick = null;
  saveDraft();
});
window.addEventListener("pagehide", saveDraft);
function renderInterview(data, restoreAnswer = "") {
  const state = data.interview;
  $("conversation").replaceChildren();
  for (const m of state.messages) {
    const p = document.createElement("p"),
      label = document.createElement("strong");
    p.className =
      m.role === "user" ? "participant-message" : "interviewer-message";
    label.textContent = m.role === "user" ? "You: " : "Interviewer: ";
    p.append(label, document.createTextNode(m.content));
    $("conversation").append(p);
  }
  $("interview-answer").value = restoreAnswer;
  $("retry-question").hidden = !state.pending_question;
  $("interview-note").textContent = state.pending_question
    ? "Your answer is saved. Retry the next question, or finish now."
    : state.ready_to_finish
      ? "Your answers are saved. Finish the interview to continue."
      : `${state.answered} of ${state.max_turns} answers saved`;
}
function render(data) {
  const old = current,
    sameVideo =
      old &&
      !old.done &&
      !data.done &&
      old.video.video_id === data.video.video_id;
  current = data;
  clearError();
  if (data.done) {
    $("video").pause();
    screen("done");
    $("session-reference").textContent = data.session_id;
    return;
  }
  screen("task");
  const saved = draft();
  pending = saved.pending || null;
  $("step-label").textContent = `Video ${data.completed + 1} of ${data.total}`;
  $("progress").max = data.total;
  $("progress").value = data.completed;
  $("video-number").textContent = String(data.completed + 1).padStart(2, "0");
  $("video-title").textContent = data.video.title;
  if (!sameVideo) {
    mediaReady = false;
    watchSeconds = saved.watchSeconds || 0;
    lastTick = null;
    $("video").src = data.video.media_url;
    $("media-error").hidden = true;
  }
  const stage = data.stage || (mode === "interview" ? "interview" : "rating");
  $("rating-form").hidden = stage !== "rating";
  $("interview-form").hidden = stage !== "interview";
  $("stage-label").textContent =
    mode === "paired"
      ? stage === "rating"
        ? "STEP 1 · YOUR OWN RATING"
        : "STEP 2 · YOUR EXPLANATION"
      : "YOUR RESPONSE";
  $("save-note").textContent =
    mode === "paired"
      ? "Your rating is saved before the interview starts."
      : "Your response is saved before the next video appears.";
  if (stage === "interview") renderInterview(data, saved.answer || "");
  else {
    $("rating-form").reset();
    $("scores").replaceChildren();
    for (let n = 0; n <= 10; n++) {
      const label = document.createElement("label"),
        radio = document.createElement("input"),
        span = document.createElement("span");
      radio.type = "radio";
      radio.name = "trust";
      radio.value = n;
      radio.required = true;
      radio.checked = saved.score === n;
      radio.setAttribute(
        "aria-label",
        `${n}${n === 0 ? " completely distrust" : n === 10 ? " completely trust" : ""}`,
      );
      span.textContent = n;
      label.append(radio, span);
      $("scores").append(label);
      radio.addEventListener("change", () => {
        $("selected-score").textContent = `Your trust score: ${n} / 10`;
        saveDraft();
        controls();
      });
    }
    $("reason").value = saved.rationale || "";
    $("confidence").value = saved.confidence ?? "";
    $("selected-score").textContent =
      saved.score === null || saved.score === undefined
        ? "Choose a score to continue"
        : `Your trust score: ${saved.score} / 10`;
  }
  controls();
  if (!sameVideo) window.scrollTo({ top: 0, behavior: "auto" });
}
for (const id of ["reason", "confidence", "interview-answer"])
  $(id).addEventListener("input", saveDraft);
$("consent").addEventListener("change", () => {
  $("start").disabled = !$("consent").checked;
});
$("start").addEventListener("click", async () => {
  if (busy) return;
  busy = true;
  $("start").disabled = true;
  clearError();
  try {
    const d = await api("/api/sessions", { consent: $("consent").checked });
    token = d.token;
    sessionStorage.setItem("vt-session", token);
    render(d);
  } catch (e) {
    error(e);
  } finally {
    busy = false;
    controls();
    $("start").disabled = !$("consent").checked;
  }
});
$("rating-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (busy || !current || current.done || !mediaReady) return;
  const radio = document.querySelector("input[name=trust]:checked");
  if (!radio) return;
  const key = draftKey();
  pending = pending || {
    video_id: current.video.video_id,
    trust_score: Number(radio.value),
    confidence:
      $("confidence").value === "" ? null : Number($("confidence").value),
    rationale: $("reason").value,
    watch_seconds: Math.round(watchSeconds * 1000) / 1000,
  };
  saveDraft();
  busy = true;
  controls();
  clearError();
  try {
    const d = await api("/api/ratings", pending);
    sessionStorage.removeItem(key);
    pending = null;
    render(d);
  } catch (e) {
    error(e);
    if (e.status && e.status < 500) {
      pending = null;
      saveDraft();
    }
  } finally {
    busy = false;
    controls();
  }
});
async function sendInterview(finish = false, retry = false) {
  if (busy || !current || current.done || !mediaReady) return;
  const state = current.interview;
  if (!finish && !retry && !$("interview-answer").value.trim()) return;
  const key = draftKey(),
    answer = $("interview-answer").value;
  const payload = retry
    ? state.retry_payload
    : {
        video_id: current.video.video_id,
        request_id: uid(),
        expected_turn: state.answered,
        answer: finish ? "" : answer,
      };
  if (!payload) return;
  busy = true;
  controls();
  clearError();
  try {
    const d = await api(
      finish ? "/api/interview/finish" : "/api/interview/answer",
      payload,
    );
    sessionStorage.removeItem(key);
    pending = null;
    render(d);
  } catch (e) {
    try {
      const d = await api("/api/session");
      const changed =
        d.done ||
        d.video.video_id !== current.video.video_id ||
        d.interview?.answered !== state.answered;
      if (changed) sessionStorage.removeItem(key);
      render(d);
    } catch (_) {}
    error(e);
  } finally {
    busy = false;
    controls();
  }
}
$("interview-form").addEventListener("submit", (e) => {
  e.preventDefault();
  sendInterview();
});
$("finish-interview").addEventListener("click", () => sendInterview(true));
$("retry-question").addEventListener("click", () => sendInterview(false, true));
(async () => {
  try {
    const study = await api("/api/study");
    mode = study.response_mode || "direct";
    $("consent-text").textContent = study.consent_text;
    $("contact").textContent = study.is_demo
      ? "Local demonstration · No API requests"
      : study.contact || "";
    $("mode").textContent = study.is_demo ? "Demo study" : "Research study";
    $("instructions").textContent =
      mode === "paired"
        ? "Watch a short video, choose your own trust score, then explain your impression in a brief interview."
        : mode === "interview"
          ? "Watch a short video and share your impressions in a brief interview."
          : "Watch a short video and tell us how much you trust it.";
    $("consent").disabled = false;
    if (token) {
      try {
        render(await api("/api/session"));
      } catch (e) {
        if (e.status === 401) {
          sessionStorage.removeItem("vt-session");
          token = "";
        } else throw e;
      }
    }
  } catch (e) {
    error(e);
  }
})();
