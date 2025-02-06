"use strict";
const $ = (id) => document.getElementById(id);
const fmt = (v, d = 1) =>
  v === null || v === undefined ? "—" : Number(v).toFixed(d);
const measureNames = {
  direct_rating: "Direct participant rating",
  interview_inferred: "Trust inferred from interview",
};
let access = "",
  selected = "",
  measure = "",
  data = null,
  selectedVideo = "",
  loadId = 0,
  detailId = 0,
  urls = [];
function el(tag, text, cls) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;
  if (cls) n.className = cls;
  return n;
}
async function request(path) {
  const r = await fetch(path, {
    headers: { Authorization: `Bearer ${access}` },
  });
  if (!r.ok) {
    let d = await r.json();
    throw new Error(d.error || "Request failed");
  }
  return r;
}
function query() {
  const q = new URLSearchParams();
  if (selected) q.set("group", selected);
  if (measure) q.set("measure", measure);
  return "?" + q;
}
function svgNode(tag, attrs = {}, text) {
  const n = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (text !== undefined) n.textContent = text;
  return n;
}
function chart(rows) {
  const svg = svgNode("svg", {
    viewBox: "0 0 520 340",
    role: "img",
    "aria-label":
      "Video-level comparison: model score on the horizontal axis, selected participant measure on the vertical axis",
  });
  for (let i = 0; i <= 10; i += 2) {
    const x = 57 + i * 39,
      y = 276 - i * 22;
    svg.append(
      svgNode("line", { x1: x, y1: 56, x2: x, y2: 276, stroke: "#e7e7e7" }),
      svgNode("line", { x1: 57, y1: y, x2: 447, y2: y, stroke: "#e7e7e7" }),
      svgNode("text", { x, y: 298, "text-anchor": "middle", class: "axis" }, i),
      svgNode(
        "text",
        { x: 43, y: y + 4, "text-anchor": "end", class: "axis" },
        i,
      ),
    );
  }
  svg.append(
    svgNode("line", {
      x1: 57,
      y1: 276,
      x2: 447,
      y2: 56,
      stroke: "#777",
      "stroke-dasharray": "4 5",
    }),
    svgNode(
      "text",
      { x: 252, y: 329, "text-anchor": "middle", class: "axis-title" },
      "Independent model score",
    ),
    svgNode(
      "text",
      { x: 57, y: 27, class: "axis-title" },
      measure === "interview_inferred"
        ? "Interview-inferred trust"
        : "Direct participant rating",
    ),
  );
  const pairs = rows.filter((r) => r.gap !== null);
  for (const r of pairs) {
    const c = svgNode("circle", {
      cx: 57 + r.model_mean * 39,
      cy: 276 - r.human_mean * 22,
      r: 7,
      fill: "#111",
      stroke: "#fff",
      "stroke-width": 2,
      tabindex: 0,
      role: "button",
      "aria-label": `Open ${r.title}: participant ${fmt(r.human_mean)}, model ${fmt(r.model_mean)}`,
    });
    c.append(
      svgNode(
        "title",
        {},
        `${r.title} · participant ${fmt(r.human_mean)} · model ${fmt(r.model_mean)}`,
      ),
    );
    c.addEventListener("click", () => inspect(r.video_id));
    c.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        inspect(r.video_id);
      }
    });
    svg.append(c);
  }
  if (!pairs.length) {
    svg.append(
      svgNode("rect", { x: 65, y: 134, width: 374, height: 61, fill: "#fff" }),
      svgNode(
        "text",
        { x: 252, y: 157, "text-anchor": "middle", class: "axis-title" },
        "No matched scores yet",
      ),
      svgNode(
        "text",
        { x: 252, y: 180, "text-anchor": "middle", class: "axis" },
        "Collect responses and complete a video assessment.",
      ),
    );
  }
  $("chart").replaceChildren(svg);
}
function coverage(label, value, total) {
  const wrap = el("div");
  wrap.append(el("dt", label), el("dd", `${value} / ${total}`));
  return wrap;
}
function renderRows() {
  if (!data) return;
  let rows = data.rows.filter((r) =>
    r.title.toLowerCase().includes($("search").value.trim().toLowerCase()),
  );
  if ($("sort").value === "title")
    rows.sort((a, b) => a.title.localeCompare(b.title));
  if ($("sort").value === "missing")
    rows.sort((a, b) => Number(b.gap === null) - Number(a.gap === null));
  $("rows").replaceChildren();
  $("visible-count").textContent = `${rows.length} videos`;
  $("list-empty").hidden = !!rows.length;
  for (const r of rows) {
    const tr = el("tr");
    tr.classList.toggle("selected", r.video_id === selectedVideo);
    tr.dataset.videoId = r.video_id;
    const td = el("td"),
      b = el("button", r.title, "video-title-button");
    b.type = "button";
    b.setAttribute("aria-pressed", String(r.video_id === selectedVideo));
    b.addEventListener("click", () => inspect(r.video_id));
    td.append(
      b,
      el(
        "small",
        r.gap !== null
          ? "Both scores available"
          : r.human_n
            ? "Waiting for model"
            : r.model_n
              ? "Waiting for participants"
              : "No scores yet",
        "row-status",
      ),
    );
    tr.append(td);
    for (const prefix of ["human", "model"]) {
      const cell = el("td");
      cell.append(
        el("strong", fmt(r[prefix + "_mean"])),
        el("small", `n = ${r[prefix + "_n"]}`),
      );
      tr.append(cell);
    }
    tr.append(
      el("td", r.gap === null ? "—" : `${r.gap > 0 ? "+" : ""}${fmt(r.gap)}`),
    );
    $("rows").append(tr);
  }
}
function option(select, value, text) {
  const o = el("option", text);
  o.value = value;
  select.append(o);
}
async function load() {
  const seq = ++loadId;
  $("status").classList.remove("error");
  $("status").textContent = "Loading results…";
  $("refresh").disabled = true;
  try {
    const next = await (
      await request("/api/admin/comparison" + query())
    ).json();
    if (seq !== loadId) return;
    data = next;
    selected = data.selected_group || "";
    measure = data.participant_measure;
    $("results").hidden = false;
    $("login").hidden = true;
    $("demo-note").hidden = !data.is_demo;
    $("study-mode").textContent = data.is_demo
      ? "Demo study"
      : data.study.response_mode === "paired"
        ? "Paired study"
        : "Research study";
    $("measure").replaceChildren();
    for (const m of data.available_measures)
      option($("measure"), m, measureNames[m]);
    $("measure").value = measure;
    $("group").replaceChildren();
    for (const g of data.groups)
      option(
        $("group"),
        g.id,
        `${g.model} · T=${g.temperature} · ${g.evidence_mode}${g.evidence_set_hash ? " · " + g.evidence_set_hash.slice(0, 6) : ""}`,
      );
    if (!data.groups.length) option($("group"), "", "No completed assessments");
    $("group").value = selected;
    $("measure-note").textContent =
      measure === "interview_inferred"
        ? "This score is inferred by an LLM from the conversation. It is not the participant’s own numeric rating."
        : "This score was selected by the participant before any interview. The video model never receives it.";
    $("participant-column").textContent =
      measure === "interview_inferred" ? "Inferred" : "Participant";
    const s = data.summary;
    $("responses").textContent = s.responses;
    $("sessions").textContent = s.completed_sessions;
    $("session-context").textContent =
      `${s.sessions} started · ${s.active_sessions} in progress`;
    $("paired").textContent = s.paired_videos;
    $("pair-context").textContent = `Of ${s.videos} videos`;
    $("gap").textContent = fmt(s.mean_absolute_gap);
    $("correlation").textContent = fmt(s.pearson_r, 2);
    $("response-context").textContent = s.unscored_responses
      ? `${s.unscored_responses} without an inferred score`
      : "Selected participant measure";
    $("correlation-note").textContent =
      s.pearson_r === null
        ? "Correlation needs at least three matched videos with variation in both scores."
        : `Video-level Pearson r = ${fmt(s.pearson_r, 2)}. Correlation is not agreement.`;
    $("coverage").replaceChildren(
      coverage("Participant scores", s.participant_videos, s.videos),
      coverage("Transcripts & frames", s.prepared_videos, s.videos),
      coverage("Model assessments", s.model_videos, s.videos),
    );
    const agreement = data.interview_agreement;
    $("agreement-panel").hidden = !agreement;
    if (agreement)
      $("agreement-value").textContent = agreement.pairs
        ? `${agreement.pairs} paired responses · mean absolute gap ${fmt(agreement.mean_absolute_gap)} · mean signed gap ${fmt(agreement.mean_signed_gap)} points`
        : "Complete both steps for a video to compare the two participant measures.";
    $("coverage-note").textContent = s.paired_videos
      ? `${s.paired_videos} video${s.paired_videos === 1 ? "" : "s"} can be compared for this condition.`
      : "Responses and model assessments must refer to the same video before a gap is calculated.";
    $("export-interviews").hidden = data.study.response_mode === "direct";
    chart(data.rows);
    renderRows();
    $("status").textContent = "";
    const vid =
      data.rows.find((r) => r.video_id === selectedVideo)?.video_id ||
      data.rows[0]?.video_id;
    if (vid) await inspect(vid);
  } catch (e) {
    if (seq === loadId) {
      $("status").textContent = e.message;
      $("status").classList.add("error");
      if (data) {
        measure = data.participant_measure;
        selected = data.selected_group || "";
        $("measure").value = measure;
        $("group").value = selected;
      }
    }
  } finally {
    if (seq === loadId) $("refresh").disabled = false;
  }
}
function appendEmpty(target, text) {
  target.append(el("p", text, "empty-state"));
}
function renderResponses(detail) {
  const target = $("panel-responses");
  target.replaceChildren();
  const responses = detail.participant_responses.filter(
    (r) => r.measure === measure,
  );
  if (!responses.length) {
    appendEmpty(target, "No saved responses for this measure yet.");
    return;
  }
  for (const r of responses) {
    const box = el("article", undefined, "response-item"),
      top = el("div", undefined, "response-heading");
    top.append(
      el("strong", `Session ${r.session_id.slice(0, 8)}`),
      el("span", `${fmt(r.trust_score)} / 10`),
    );
    box.append(top, el("p", r.rationale || "No written explanation."));
    if (r.participant_summary)
      box.append(el("p", r.participant_summary, "muted"));
    if (r.measure === "direct_rating")
      box.append(
        el(
          "p",
          `Confidence: ${r.confidence === null ? "not given" : r.confidence + " / 10"} · Playback logged: ${fmt(r.watch_seconds)} s`,
          "small muted",
        ),
      );
    const turns = detail.interview_turns
      .filter((t) => t.session_id === r.session_id)
      .sort((a, b) => a.turn - b.turn);
    if (turns.length) {
      const d = el("details"),
        summary = el("summary", "Read interview");
      d.append(summary);
      let question =
        "What stood out to you in the video, and what impression did it leave?";
      for (const t of turns) {
        d.append(el("p", question, "interview-question"), el("p", t.answer));
        question = t.next_question || "";
      }
      box.append(d);
    }
    target.append(box);
  }
}
function renderModels(row) {
  const target = $("panel-model");
  target.replaceChildren();
  if (!row.model_runs.length) {
    appendEmpty(target, "No completed model assessment for this condition.");
    return;
  }
  for (const run of row.model_runs) {
    const box = el("article", undefined, "response-item");
    box.append(
      el("strong", `Run ${run.repeat} · ${fmt(run.trust_score)} / 10`),
      el("p", run.rationale || "No explanation recorded."),
    );
    if (run.full_summary) box.append(el("p", run.full_summary, "muted"));
    if (run.factors)
      box.append(el("p", "Factors: " + run.factors.join("; "), "small"));
    if (run.limitations)
      box.append(
        el("p", "Limitations: " + run.limitations.join("; "), "small muted"),
      );
    const d = el("details");
    d.append(
      el("summary", "Assessment details"),
      el(
        "p",
        `${run.resolved_model || run.model} · ${run.evidence_mode} · temperature ${run.temperature}`,
        "small",
      ),
    );
    box.append(d);
    target.append(box);
  }
}
async function renderEvidence(detail, seq) {
  const target = $("panel-evidence");
  target.replaceChildren();
  const ev = detail.evidence;
  if (!ev) {
    appendEmpty(
      target,
      "No transcript or sampled frames have been prepared for this video yet.",
    );
    return;
  }
  target.append(
    el("h3", "Transcript"),
    el(
      "p",
      `${ev.language || "Language not detected"} · ${ev.transcription_status === "no_audio" ? "No audio stream" : ev.transcription_status}`,
      "small muted",
    ),
    el("p", ev.transcript || "No speech transcript.", "transcript"),
  );
  if (detail.context) {
    target.append(
      el("h3", "Visual summary"),
      el("p", detail.context.visual_summary),
      el(
        "p",
        `${detail.context.classification} · ${detail.context.topic || "No topic cluster"}`,
        "small muted",
      ),
    );
  }
  if (ev.frames?.length) {
    target.append(el("h3", "Sampled frames"));
    const frames = el("div", undefined, "frame-grid");
    target.append(frames);
    for (const frame of ev.frames) {
      try {
        const blob = await (await request(frame.url)).blob();
        if (seq !== detailId) return;
        const u = URL.createObjectURL(blob);
        urls.push(u);
        const figure = el("figure"),
          img = el("img");
        img.src = u;
        img.alt = `Video frame at ${frame.timestamp_seconds} seconds`;
        figure.append(
          img,
          el("figcaption", `${fmt(frame.timestamp_seconds)} s`),
        );
        frames.append(figure);
      } catch (_) {
        frames.append(el("p", "Frame unavailable", "small"));
      }
    }
  }
}
async function inspect(vid) {
  if (!data) return;
  const seq = ++detailId;
  selectedVideo = vid;
  renderRows();
  const row = data.rows.find((r) => r.video_id === vid);
  if (!row) return;
  for (const name of ["responses", "model", "evidence"])
    $("panel-" + name).replaceChildren();
  $("detail-title").textContent = row.title;
  $("detail-status").textContent = "Loading video details…";
  $("detail-video").pause();
  $("detail-video").hidden = true;
  for (const u of urls) URL.revokeObjectURL(u);
  urls = [];
  $("detail-scores").replaceChildren();
  for (const [p, label] of [
    [
      "human",
      measure === "interview_inferred"
        ? "Interview inference"
        : "Participant rating",
    ],
    ["model", "Video model"],
  ]) {
    const box = el("div");
    box.append(
      el("span", label),
      el("strong", fmt(row[p + "_mean"])),
      el("small", `n = ${row[p + "_n"]} · SD ${fmt(row[p + "_sd"])}`),
    );
    $("detail-scores").append(box);
  }
  try {
    const detail = await (
      await request("/api/admin/video?id=" + encodeURIComponent(vid))
    ).json();
    if (seq !== detailId) return;
    $("detail-video").src = detail.media_url;
    $("detail-video").hidden = false;
    $("detail-meta").textContent = detail.media_info
      ? `${fmt(detail.media_info.duration_seconds)} seconds · ${detail.media_info.width} × ${detail.media_info.height}${detail.media_info.has_audio ? " · audio" : ""}`
      : "";
    renderResponses(detail);
    renderModels(row);
    $("detail-status").textContent = "";
    await renderEvidence(detail, seq);
  } catch (e) {
    if (seq === detailId) $("detail-status").textContent = e.message;
  }
}
async function download(path, name) {
  try {
    const blob = await (await request(path)).blob(),
      u = URL.createObjectURL(blob),
      a = el("a");
    a.href = u;
    a.download = name;
    a.click();
    setTimeout(() => URL.revokeObjectURL(u), 1000);
  } catch (e) {
    $("status").textContent = e.message;
  }
}
$("login").addEventListener("submit", (e) => {
  e.preventDefault();
  access = $("admin-token").value.trim();
  load();
});
$("group").addEventListener("change", () => {
  selected = $("group").value;
  load();
});
$("measure").addEventListener("change", () => {
  measure = $("measure").value;
  load();
});
$("refresh").addEventListener("click", load);
$("search").addEventListener("input", renderRows);
$("sort").addEventListener("change", renderRows);
$("logout").addEventListener("click", () => {
  access = "";
  loadId++;
  detailId++;
  $("detail-video").pause();
  $("detail-video").removeAttribute("src");
  for (const u of urls) URL.revokeObjectURL(u);
  urls = [];
  data = null;
  $("admin-token").value = "";
  $("results").hidden = true;
  $("login").hidden = false;
  $("status").textContent = "";
});
$("export").addEventListener("click", () =>
  download("/api/admin/export.csv", "human_responses.csv"),
);
$("export-comparison").addEventListener("click", () =>
  download("/api/admin/comparison.csv" + query(), "comparison.csv"),
);
$("export-interviews").addEventListener("click", () =>
  download("/api/admin/interviews.json", "interviews.json"),
);
for (const button of document.querySelectorAll("[data-panel]"))
  button.addEventListener("click", () => {
    for (const b of document.querySelectorAll("[data-panel]")) {
      const active = b === button;
      b.setAttribute("aria-selected", String(active));
      $("panel-" + b.dataset.panel).hidden = !active;
    }
  });
