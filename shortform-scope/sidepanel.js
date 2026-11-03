import { analyze, makeConti, getSettings, MODELS, measurementSummary, costKRW } from "./claude.js";
import { CONTI_MODES } from "./prompts.js";

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmtT = (t) => (t == null ? "-" : Number(t).toFixed(1) + "초");

let current = null; // 지금 화면에 띄운 리포트
let running = false;

// ---------- 탭 ----------
document.querySelectorAll(".tab").forEach((b) =>
  b.addEventListener("click", () => showTab(b.dataset.tab)));
function showTab(name) {
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + name));
  if (name === "history") renderHistory();
}

// ---------- 설정 ----------
async function loadSettings() {
  const s = await getSettings();
  $("#set-key").value = s.apiKey;
  $("#set-model").innerHTML = Object.entries(MODELS).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("");
  $("#set-model").value = s.model;
  $("#set-effort").value = s.effort;
  if (!s.apiKey) showTab("settings");
}
$("#btn-save").addEventListener("click", async () => {
  await chrome.storage.local.set({
    apiKey: $("#set-key").value.trim(),
    model: $("#set-model").value,
    effort: $("#set-effort").value,
  });
  $("#save-msg").textContent = "저장했어요";
  setTimeout(() => ($("#save-msg").textContent = ""), 2000);
});

// ---------- 진행 표시 ----------
function setProgress(pct, text) {
  $("#progress").classList.remove("hidden");
  $("#progress-fill").style.width = pct + "%";
  $("#progress-text").textContent = text;
}
function hideProgress() { $("#progress").classList.add("hidden"); }
function showError(msg) { const e = $("#error"); e.textContent = msg; e.classList.remove("hidden"); }
function clearError() { $("#error").classList.add("hidden"); }

chrome.runtime.onMessage.addListener((msg) => {
  if (msg?.type === "measure-progress") setProgress(Math.round(msg.pct * 0.6), msg.text);
  if (msg?.type === "start-analysis") startAnalysis();
});

// ---------- 분석 ----------
$("#btn-analyze").addEventListener("click", startAnalysis);

async function startAnalysis() {
  if (running) return; // 버튼·단축키가 겹쳐 두 번 시작되지 않게 바로 잠근다
  running = true;
  chrome.storage.session.remove("pendingAnalyze").catch(() => {});
  showTab("analyze");
  clearError();
  const { apiKey } = await getSettings();
  if (!apiKey) { running = false; showTab("settings"); return; }
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  if (!tab || !/^https:\/\/(www\.|m\.)?(instagram\.com|threads\.(net|com)|youtube\.com)\//.test(tab.url || "")) {
    running = false;
    showError("인스타그램 · 쓰레드 · 유튜브 쇼츠 화면에서 눌러 주세요.\n(인스타·쓰레드는 로그인된 상태여야 영상이 보여요)");
    return;
  }
  $("#btn-analyze").disabled = true;
  $("#report").innerHTML = "";
  try {
    setProgress(1, "측정 도구 연결 중");
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
    const res = await chrome.tabs.sendMessage(tab.id, { type: "measure", opts: { rate: $("#opt-fast").checked ? 2 : 1 } });
    if (!res?.ok) throw new Error(res?.error || "측정에 실패했어요.");
    const m = res.data;
    const pasted = $("#opt-comments").value.split("\n").map((s) => s.trim()).filter(Boolean)
      .map((s) => s.replace(/@[\w.\-가-힣]+/g, "@○○"));
    if (pasted.length) m.comments = [...new Set([...pasted, ...m.comments])].slice(0, 200);

    setProgress(62, `Claude가 분석 중 (대표 장면 ${m.frames.length}장, 댓글 ${m.comments.length}개) · 30초~1분 걸려요`);
    const { analysis, usage, model } = await analyze(m);

    const report = {
      id: "r" + Date.now(),
      createdAt: new Date().toISOString(),
      url: m.url,
      platform: m.platform,
      title: (m.caption || m.pageTitle || "").split("\n")[0].slice(0, 80),
      cover: m.frames[0]?.dataUrl || "",
      measure: { ...measurementSummary(m), shots: m.shots, cuts: m.cuts, beats: m.beats, loudness: m.loudness, comment_count: m.comments.length },
      analysis,
      contis: [],
      cost: { analysis: costKRW(usage, model) },
      model,
    };
    await saveReport(report);
    setProgress(100, "완료");
    setTimeout(hideProgress, 600);
    current = report;
    renderReport(report);
  } catch (e) {
    hideProgress();
    showError(e.message || String(e));
  } finally {
    running = false;
    $("#btn-analyze").disabled = false;
  }
}

// ---------- 저장 ----------
async function loadAll() { return (await chrome.storage.local.get("reports")).reports || []; }
async function saveReport(r) {
  const all = await loadAll();
  const i = all.findIndex((x) => x.id === r.id);
  if (i >= 0) all[i] = r; else all.unshift(r);
  await chrome.storage.local.set({ reports: all.slice(0, 300) });
}
async function deleteReport(id) {
  const all = (await loadAll()).filter((x) => x.id !== id);
  await chrome.storage.local.set({ reports: all });
}

async function renderHistory() {
  const all = await loadAll();
  const box = $("#history-list");
  if (!all.length) { box.innerHTML = `<div class="empty">아직 분석한 영상이 없어요.</div>`; return; }
  box.innerHTML = all.map((r) => `
    <div class="card hist-item" data-id="${r.id}">
      ${r.cover ? `<img src="${r.cover}" alt="">` : ""}
      <div>
        <div class="t">${esc(r.title || "(제목 없음)")}</div>
        <div class="s">${esc(r.platform)} · 종합 ${r.analysis?.scores?.total ?? "-"}점 · ${new Date(r.createdAt).toLocaleString("ko-KR")}</div>
      </div>
      <button class="ghost del" data-del="${r.id}">삭제</button>
    </div>`).join("");
  box.querySelectorAll(".hist-item").forEach((el) => el.addEventListener("click", async (ev) => {
    const del = ev.target.closest("[data-del]");
    if (del) {
      ev.stopPropagation();
      if (confirm("이 기록을 지울까요?")) { await deleteReport(del.dataset.del); renderHistory(); }
      return;
    }
    const r = (await loadAll()).find((x) => x.id === el.dataset.id);
    if (r) { current = r; showTab("analyze"); clearError(); renderReport(r); }
  }));
}

// ---------- 차트 ----------
function emotionChart(r) {
  const W = 340, H = 150, pl = 26, pr = 6, pt = 8, pb = 28;
  const dur = r.measure.duration_s || 1;
  const x = (t) => pl + (Math.min(t, dur) / dur) * (W - pl - pr);
  const y = (v) => pt + (1 - v / 100) * (H - pt - pb);
  const path = (pts) => pts.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join("");
  const emo = (r.analysis.emotion_curve || []).slice().sort((a, b) => a.t - b.t).map((p) => [p.t, p.value]);
  const loud = (r.measure.loudness || []).map((l) => [l.t, l.v]);
  let g = "";
  for (const v of [0, 50, 100]) g += `<line x1="${pl}" x2="${W - pr}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)"/><text x="2" y="${y(v) + 3}">${v}</text>`;
  const step = dur > 60 ? 15 : dur > 30 ? 10 : 5;
  for (let t = 0; t <= dur; t += step) g += `<text x="${x(t) - 6}" y="${H - 14}">${t}s</text>`;
  // 컷 위치(아래 눈금)
  for (const c of (r.measure.cuts || []).slice(1)) g += `<line x1="${x(c)}" x2="${x(c)}" y1="${H - pb + 2}" y2="${H - pb + 8}" stroke="var(--muted)"/>`;
  // 훅 지점
  for (const m of r.analysis.hook?.grab_moments || []) g += `<line x1="${x(m.t)}" x2="${x(m.t)}" y1="${pt}" y2="${H - pb}" stroke="var(--accent)" stroke-dasharray="3 3"/>`;
  for (const m of r.analysis.hook?.payoff_moments || []) g += `<line x1="${x(m.t)}" x2="${x(m.t)}" y1="${pt}" y2="${H - pb}" stroke="var(--blue)" stroke-dasharray="3 3"/>`;
  if (loud.length > 1) g += `<path d="${path(loud)}" fill="none" stroke="var(--accent-2)" stroke-width="1.5" opacity=".9"/>`;
  if (emo.length > 1) g += `<path d="${path(emo)}" fill="none" stroke="var(--accent)" stroke-width="2.5"/>`;
  for (const p of emo) g += `<circle cx="${x(p[0])}" cy="${y(p[1])}" r="2.5" fill="var(--accent)"/>`;
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="감정 곡선과 소리 크기">${g}</svg>
  <div class="legend"><span><i style="background:var(--accent)"></i>감정(몰입도)</span>
  <span><i style="background:var(--accent-2)"></i>실제 소리 크기${r.measure.audio_available ? "" : " (측정 안 됨)"}</span>
  <span><i style="background:var(--accent);height:0;border-top:2px dashed var(--accent)"></i>붙잡는 순간</span>
  <span><i style="background:var(--blue);height:0;border-top:2px dashed var(--blue)"></i>풀리는 순간</span>
  <span>아래 눈금 = 컷</span></div>`;
}

function shotChart(r) {
  const W = 340, H = 64, pl = 4, pr = 4;
  const dur = r.measure.duration_s || 1;
  const x = (t) => pl + (Math.min(t, dur) / dur) * (W - pl - pr);
  let g = "";
  for (const s of r.measure.shots || []) {
    const w = Math.max(1, x(s.end) - x(s.start) - 1);
    g += `<rect x="${x(s.start)}" y="8" width="${w}" height="30" rx="2" fill="${s.color}" stroke="var(--line)"><title>샷 ${s.index}: ${s.start}~${s.end}초 (${s.length}초, ${s.camera})</title></rect>`;
    if (w > 12) g += `<text x="${x(s.start) + 2}" y="50">${s.index}</text>`;
  }
  const beats = r.measure.beats || [];
  beats.forEach((b, i) => { if (i % 4 === 0) g += `<line x1="${x(b)}" x2="${x(b)}" y1="4" y2="42" stroke="var(--accent)" stroke-width="1" opacity=".7"/>`; });
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="샷 측정 차트">${g}</svg>
  <div class="legend"><span>막대 색 = 샷 평균 색 · 숫자 = 샷 번호</span>${beats.length ? `<span><i style="background:var(--accent)"></i>4박마다 세로선</span>` : ""}</div>`;
}

// ---------- 리포트 ----------
function renderReport(r) {
  const a = r.analysis, m = r.measure;
  const sc = a.scores || {};
  const moments = (list, cls) => (list || []).map((x) => `<div class="moment"><span class="t ${cls}">${fmtT(x.t)}</span><span>${esc(x.what)}</span></div>`).join("") || `<p class="hint">없음</p>`;
  const reactions = (a.comment_reactions || []).slice().sort((p, q) => q.ratio - p.ratio);
  const totalCost = (r.cost?.analysis || 0) + (r.contis || []).reduce((s, c) => s + (c.cost || 0), 0);

  $("#report").innerHTML = `
  <div class="card">
    <div class="cover">
      ${r.cover ? `<img src="${r.cover}" alt="">` : ""}
      <div><div><b>${esc(r.title || "(제목 없음)")}</b></div>
      <div class="meta">${esc(r.platform)} · ${new Date(r.createdAt).toLocaleString("ko-KR")}<br><a href="${esc(r.url)}" target="_blank">원본 열기</a></div></div>
    </div>
    <p class="summary">${esc(a.summary)}</p>
    <div class="scores">
      <div class="score total"><b>${sc.total ?? "-"}</b><span>종합</span></div>
      <div class="score"><b>${sc.hook ?? "-"}</b><span>훅</span></div>
      <div class="score"><b>${sc.emotion ?? "-"}</b><span>감정</span></div>
      <div class="score"><b>${sc.narrative ?? "-"}</b><span>서사</span></div>
    </div>
    <p class="reason"><b>훅</b> ${esc(a.score_reasons?.hook)}</p>
    <p class="reason"><b>감정</b> ${esc(a.score_reasons?.emotion)}</p>
    <p class="reason"><b>서사</b> ${esc(a.score_reasons?.narrative)}</p>
  </div>

  <div class="card">
    <h3>훅 · <span class="chip red">${esc(a.hook?.type_name)}</span></h3>
    <p class="hint">${esc(a.hook?.type_desc)}</p>
    <p class="reason"><b>첫 3초</b> ${esc(a.hook?.first_3s)}</p>
    <h4>붙잡는 순간</h4>${moments(a.hook?.grab_moments, "grab")}
    <h4>궁금증이 풀리는 순간</h4>${moments(a.hook?.payoff_moments, "pay")}
  </div>

  <div class="card">
    <h3>감정 곡선 vs 소리 크기</h3>
    ${emotionChart(r)}
  </div>

  <div class="card">
    <h3>서사 · ${esc(a.narrative?.structure_name)}</h3>
    ${(a.narrative?.beats || []).map((b) => `<div class="moment"><span class="t">${fmtT(b.t_start)}</span><span><b>${esc(b.role)}</b> ${esc(b.desc)}</span></div>`).join("")}
  </div>

  <div class="card">
    <h3>측정</h3>
    <div class="tiles">
      <div class="tile"><b>${m.duration_s}초</b><span>길이${m.truncated ? " (앞 3분)" : ""}</span></div>
      <div class="tile"><b>${m.shot_count}개</b><span>샷</span></div>
      <div class="tile"><b>${m.avg_shot_length_s}초</b><span>평균 샷 길이</span></div>
      <div class="tile"><b>${m.bpm ?? "-"}</b><span>BPM${m.bpm_confidence != null && m.bpm_confidence < 0.3 ? " (불확실)" : ""}</span></div>
      <div class="tile"><b>${m.beat_aligned_cut_ratio_pct != null ? m.beat_aligned_cut_ratio_pct + "%" : "-"}</b><span>박자에 맞은 컷</span></div>
      <div class="tile"><b>${esc(m.main_camera)}</b><span>주 카메라</span></div>
    </div>
    <h4>샷 측정 차트</h4>
    ${shotChart(r)}
    <details><summary class="hint">샷별 측정값 보기</summary>
      <div class="tablewrap"><table><tr><th>샷</th><th>시작</th><th>길이</th><th>프레임</th><th>색</th><th>카메라</th><th>메모</th></tr>
      ${(m.shots || []).map((s) => {
        const note = (a.shot_notes || []).find((n) => n.shot === s.index);
        return `<tr><td>${s.index}</td><td>${s.start}</td><td>${s.length}초</td><td>${s.frames30}</td><td><span class="swatch" style="background:${s.color}"></span> ${esc(s.colorName)}</td><td>${esc(s.camera)}</td><td>${esc(note?.what || "")}</td></tr>`;
      }).join("")}</table></div>
    </details>
  </div>

  <div class="card">
    <h3>댓글 반응 <span class="hint">(${m.comment_count}개 기준)</span></h3>
    ${reactions.length ? `<div class="bars">${reactions.map((c) => `
      <div class="b"><span class="lbl">${esc(c.type)}</span><span class="track"><span class="fill" style="width:${Math.min(100, c.ratio)}%;display:block"></span></span><span class="pct">${c.ratio}%</span></div>
      <div class="ex">"${esc(c.example)}"</div>`).join("")}</div>`
      : `<p class="hint">수집된 댓글이 없어요. 댓글 창을 열어 스크롤한 뒤 다시 분석하거나, 측정 옵션에 댓글을 붙여넣어 주세요.</p>`}
  </div>

  <div class="card">
    <h3>대사 · 자막 대본 <span class="hint">(화면 글자 기준)</span></h3>
    ${(a.on_screen_text || []).length ? (a.on_screen_text || []).map((s) => `<div class="moment"><span class="t">${fmtT(s.t)}</span><span>${esc(s.text)}</span></div>`).join("") : `<p class="hint">화면에 글자가 없어요.</p>`}
  </div>

  <div class="card">
    <h3>잘한 점 / 아쉬운 점</h3>
    <ul class="plain">${(a.strengths || []).map((s) => `<li>👍 ${esc(s)}</li>`).join("")}${(a.weaknesses || []).map((s) => `<li>⚠ ${esc(s)}</li>`).join("")}</ul>
    <h4>로빈의밥상에 옮기면</h4>
    <ul class="plain">${(a.robyn_apply || []).map((s) => `<li>${esc(s)}</li>`).join("")}</ul>
  </div>

  <div class="card">
    <h3>콘티 만들기</h3>
    <p class="hint">이 영상의 구조만 빌려서 새 소재로 다시 만듭니다.</p>
    <input type="text" id="conti-topic" placeholder="새 소재 (예: 알룰로스로 만드는 무 깍두기)">
    <div class="row">
      ${Object.entries(CONTI_MODES).map(([k, v]) => `<button class="ghost" data-conti="${k}">${esc(v.label)}</button>`).join("")}
    </div>
    <div id="conti-out">${(r.contis || []).map(contiBlock).join("")}</div>
  </div>

  <div class="card">
    <div class="row">
      <button class="ghost" id="btn-md">마크다운 저장</button>
      <button class="ghost" id="btn-copy">마크다운 복사</button>
      <button class="ghost" id="btn-pdf">PDF로 인쇄</button>
    </div>
    <p class="cost">${esc(r.model || "")} · 이 리포트 사용 금액 약 ${totalCost.toLocaleString()}원(추정)</p>
  </div>`;

  document.querySelectorAll("[data-conti]").forEach((b) => b.addEventListener("click", () => runConti(b.dataset.conti)));
  $("#btn-md").addEventListener("click", () => download(fileName(r) + ".md", toMarkdown(r), "text/markdown"));
  $("#btn-copy").addEventListener("click", async () => { await navigator.clipboard.writeText(toMarkdown(r)); $("#btn-copy").textContent = "복사됨"; });
  $("#btn-pdf").addEventListener("click", () => printReport(r));
}

function contiBlock(c) {
  return `<div class="md" style="border-top:1px solid var(--line);margin-top:12px;padding-top:6px">
    <p class="hint">${esc(CONTI_MODES[c.mode]?.label)} · ${esc(c.topic || "소재 자동 선택")} · 약 ${c.cost ?? "-"}원</p>
    ${mdToHtml(c.markdown)}</div>`;
}

async function runConti(mode) {
  if (!current || running) return;
  const topic = $("#conti-topic").value.trim();
  running = true;
  document.querySelectorAll("[data-conti]").forEach((b) => (b.disabled = true));
  const out = $("#conti-out");
  const wait = document.createElement("p");
  wait.className = "hint"; wait.textContent = "콘티 작성 중 · 30초~1분 걸려요";
  out.prepend(wait);
  try {
    const { markdown, usage, model } = await makeConti(current, mode, topic);
    const c = { mode, topic, markdown, cost: costKRW(usage, model), createdAt: new Date().toISOString() };
    current.contis = [c, ...(current.contis || [])];
    await saveReport(current);
    renderReport(current);
  } catch (e) {
    wait.textContent = e.message;
    wait.style.color = "var(--accent)";
  } finally {
    running = false;
    document.querySelectorAll("[data-conti]").forEach((b) => (b.disabled = false));
  }
}

// ---------- 내보내기 ----------
function fileName(r) {
  return ("밥상스코프_" + (r.title || r.id)).replace(/[\\/:*?"<>|\n]/g, " ").slice(0, 60).trim();
}
function download(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type: type + ";charset=utf-8" }));
  const a = document.createElement("a"); a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

function toMarkdown(r) {
  const a = r.analysis, m = r.measure, L = [];
  L.push(`# ${r.title || "숏폼 분석"}`, "", `- 원본: ${r.url}`, `- 분석일: ${new Date(r.createdAt).toLocaleString("ko-KR")}`, "");
  L.push(`> ${a.summary}`, "");
  L.push(`## 점수`, `| 종합 | 훅 | 감정 | 서사 |`, `|---|---|---|---|`, `| ${a.scores.total} | ${a.scores.hook} | ${a.scores.emotion} | ${a.scores.narrative} |`, "");
  L.push(`- 훅: ${a.score_reasons.hook}`, `- 감정: ${a.score_reasons.emotion}`, `- 서사: ${a.score_reasons.narrative}`, "");
  L.push(`## 훅 — ${a.hook.type_name}`, a.hook.type_desc, "", `- 첫 3초: ${a.hook.first_3s}`);
  a.hook.grab_moments.forEach((x) => L.push(`- 붙잡는 순간 ${fmtT(x.t)}: ${x.what}`));
  a.hook.payoff_moments.forEach((x) => L.push(`- 풀리는 순간 ${fmtT(x.t)}: ${x.what}`));
  L.push("", `## 감정 곡선`, ...a.emotion_curve.map((p) => `- ${fmtT(p.t)} ${p.value} — ${p.label}`), "");
  L.push(`## 서사 — ${a.narrative.structure_name}`, ...a.narrative.beats.map((b) => `- ${fmtT(b.t_start)}~${fmtT(b.t_end)} **${b.role}** ${b.desc}`), "");
  L.push(`## 측정`, `- 길이 ${m.duration_s}초 · 샷 ${m.shot_count}개 · 평균 샷 ${m.avg_shot_length_s}초 · 분당 컷 ${m.cuts_per_minute}`,
    `- BPM ${m.bpm ?? "-"} · 박자에 맞은 컷 ${m.beat_aligned_cut_ratio_pct ?? "-"}% · 주 카메라 ${m.main_camera}`, "");
  L.push(`| 샷 | 시작 | 길이 | 프레임(30fps) | 색 | 카메라 |`, `|---|---|---|---|---|---|`,
    ...m.shots.map((s) => `| ${s.index} | ${s.start} | ${s.length} | ${s.frames30} | ${s.colorName} | ${s.camera} |`), "");
  L.push(`## 댓글 반응 (${m.comment_count}개 기준)`, ...a.comment_reactions.map((c) => `- ${c.type} ${c.ratio}% — "${c.example}"`), "");
  L.push(`## 자막 대본`, ...a.on_screen_text.map((s) => `- ${fmtT(s.t)} ${s.text}`), "");
  L.push(`## 잘한 점`, ...a.strengths.map((s) => `- ${s}`), "", `## 아쉬운 점`, ...a.weaknesses.map((s) => `- ${s}`), "");
  L.push(`## 로빈의밥상에 옮기면`, ...a.robyn_apply.map((s) => `- ${s}`), "");
  for (const c of r.contis || []) L.push(`---`, `# 콘티: ${CONTI_MODES[c.mode]?.label} (${c.topic || "소재 자동"})`, "", c.markdown, "");
  return L.join("\n");
}

function printReport(r) {
  const html = `<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>${esc(fileName(r))}</title>
  <style>body{font:13px/1.6 "Malgun Gothic","Apple SD Gothic Neo",sans-serif;max-width:760px;margin:24px auto;color:#1f1d1a}
  table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccc;padding:4px 6px;font-size:12px}h1{font-size:20px}h2{font-size:16px;margin-top:20px}
  blockquote{border-left:4px solid #c8402a;margin:0;padding:4px 12px;background:#f7f5f1}</style></head>
  <body>${mdToHtml(toMarkdown(r))}</body></html>`;
  const url = URL.createObjectURL(new Blob([html], { type: "text/html;charset=utf-8" }));
  const w = window.open(url, "_blank");
  // 확장 보안 정책상 새 창 안의 스크립트는 못 쓰므로 여기서 인쇄 창을 띄운다.
  if (w) w.addEventListener("load", () => setTimeout(() => w.print(), 300));
}

// 아주 작은 마크다운 변환기(제목·표·목록·굵게·코드·인용). 입력은 먼저 이스케이프한다.
function mdToHtml(md) {
  const lines = esc(md || "").split("\n");
  const out = [];
  let i = 0;
  const inline = (s) => s.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
  while (i < lines.length) {
    const l = lines[i];
    if (/^```/.test(l)) {
      const buf = []; i++;
      while (i < lines.length && !/^```/.test(lines[i])) buf.push(lines[i++]);
      out.push(`<pre>${buf.join("\n")}</pre>`); i++; continue;
    }
    if (/^\s*\|/.test(l)) {
      const rows = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) rows.push(lines[i++]);
      const cells = (row) => row.trim().replace(/^\||\|$/g, "").split("|").map((c) => inline(c.trim()));
      const body = rows.filter((row) => !/^\s*\|?\s*:?-{2,}/.test(row));
      const [head, ...rest] = body;
      out.push(`<div class="tablewrap"><table><tr>${cells(head).map((c) => `<th>${c}</th>`).join("")}</tr>${rest.map((row) => `<tr>${cells(row).map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</table></div>`);
      continue;
    }
    if (/^\s*[-*] /.test(l)) {
      const buf = [];
      while (i < lines.length && /^\s*[-*] /.test(lines[i])) buf.push(`<li>${inline(lines[i++].replace(/^\s*[-*] /, ""))}</li>`);
      out.push(`<ul>${buf.join("")}</ul>`); continue;
    }
    if (/^\s*\d+\. /.test(l)) {
      const buf = [];
      while (i < lines.length && /^\s*\d+\. /.test(lines[i])) buf.push(`<li>${inline(lines[i++].replace(/^\s*\d+\. /, ""))}</li>`);
      out.push(`<ol>${buf.join("")}</ol>`); continue;
    }
    const h = l.match(/^(#{1,4}) (.*)/);
    if (h) { out.push(`<h${Math.min(4, h[1].length + 1)}>${inline(h[2])}</h${Math.min(4, h[1].length + 1)}>`); i++; continue; }
    if (/^&gt; /.test(l)) { out.push(`<blockquote>${inline(l.slice(5))}</blockquote>`); i++; continue; }
    if (/^---+$/.test(l.trim())) { out.push("<hr>"); i++; continue; }
    if (l.trim()) out.push(`<p>${inline(l)}</p>`);
    i++;
  }
  return out.join("\n");
}

// ---------- 시작 ----------
(async () => {
  await loadSettings();
  // 단축키로 패널이 막 열린 경우 바로 분석 시작
  const { pendingAnalyze } = await chrome.storage.session.get("pendingAnalyze");
  if (pendingAnalyze && Date.now() - pendingAnalyze < 10000) {
    await chrome.storage.session.remove("pendingAnalyze");
    startAnalysis();
  }
})();
