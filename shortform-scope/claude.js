// Claude Messages API 호출. 확장 프로그램은 빌드 과정 없이 바로 설치하는 구조라
// SDK 대신 fetch로 직접 부릅니다. API 키는 이 브라우저의 확장 저장소에만 보관됩니다.
import { ANALYSIS_SYSTEM, ANALYSIS_SCHEMA, CONTI_SYSTEM, CONTI_MODES } from "./prompts.js";

const API_URL = "https://api.anthropic.com/v1/messages";
export const MODELS = {
  "claude-opus-5-5": "Claude Opus 5.5 (기본·가장 정확)",
  "claude-sonnet-5-5": "Claude Sonnet 5.5 (더 저렴)",
};

export async function getSettings() {
  const s = await chrome.storage.local.get(["apiKey", "model", "effort"]);
  return { apiKey: s.apiKey || "", model: s.model || "claude-opus-5-5", effort: s.effort || "medium" };
}

async function callClaude(body, { retries = 2 } = {}) {
  const { apiKey } = await getSettings();
  if (!apiKey) throw new Error("API 키가 없어요. ⚙ 설정 탭에서 Claude API 키를 넣어 주세요.");
  const headers = {
    "content-type": "application/json",
    "x-api-key": apiKey,
    "anthropic-version": "2026-10-21",
    "anthropic-dangerous-direct-browser-access": "true",
  };
  // 안전 분류기가 요청을 거절하면 서버가 알아서 다른 모델로 다시 돌린다.
  if (body.model !== "claude-haiku-5-5") {
    headers["anthropic-beta"] = "server-side-fallback-2026-07-01";
    body = { ...body, fallbacks: "default" };
  }
  for (let attempt = 0; ; attempt++) {
    let res;
    try {
      res = await fetch(API_URL, { method: "POST", headers, body: JSON.stringify(body) });
    } catch (e) {
      if (attempt < retries) { await new Promise((r) => setTimeout(r, 2000 * (attempt + 1))); continue; }
      throw new Error("인터넷 연결을 확인해 주세요. (" + e.message + ")");
    }
    if (res.ok) {
      const msg = await res.json();
      if (msg.stop_reason === "refusal") throw new Error("Claude가 이 요청을 처리하지 않았어요. 다른 영상으로 시도해 주세요.");
      if (msg.stop_reason === "max_tokens") throw new Error("응답이 너무 길어 중간에 끊겼어요. 다시 시도해 주세요.");
      const text = msg.content.filter((b) => b.type === "text").map((b) => b.text).join("");
      return { text, usage: msg.usage, model: msg.model };
    }
    const errText = await res.text().catch(() => "");
    if ((res.status === 429 || res.status >= 500) && attempt < retries) {
      const wait = Number(res.headers.get("retry-after")) * 1000 || 3000 * (attempt + 1);
      await new Promise((r) => setTimeout(r, wait));
      continue;
    }
    if (res.status === 401) throw new Error("API 키가 맞지 않아요. 설정 탭에서 키를 다시 확인해 주세요.");
    if (res.status === 402 || /credit|billing/i.test(errText)) throw new Error("API 크레딧(잔액)이 부족해요. console.anthropic.com 에서 충전해 주세요.");
    if (res.status === 429) throw new Error("요청이 많아 잠시 막혔어요. 1분 뒤 다시 시도해 주세요.");
    throw new Error(`Claude 호출 실패 (${res.status}) ${errText.slice(0, 300)}`);
  }
}

// 측정값에서 이미지(용량 큼)를 뺀 요약본
export function measurementSummary(m) {
  return {
    platform: m.platform,
    duration_s: m.duration,
    truncated: m.truncated,
    shot_count: m.shots.length,
    avg_shot_length_s: m.avgShotLength,
    cuts_per_minute: m.cutsPerMinute,
    main_camera: m.mainCamera,
    bpm: m.bpm,
    bpm_confidence: m.bpmConfidence,
    beat_aligned_cut_ratio_pct: m.beatAlignedRatio,
    audio_available: m.audioAvailable,
    shots: m.shots.map((s) => ({ shot: s.index, start: s.start, end: s.end, len: s.length, camera: s.camera, color: s.colorName, brightness: s.brightness })),
    loudness_0to100_every_0_5s: m.loudness.map((l) => [l.t, l.v]),
  };
}

export async function analyze(m) {
  const { model, effort } = await getSettings();
  const content = [];
  content.push({ type: "text", text: "## 측정값\n```json\n" + JSON.stringify(measurementSummary(m)) + "\n```" });
  content.push({ type: "text", text: "## 캡션\n" + (m.caption || "(없음)") });
  content.push({
    type: "text",
    text: "## 댓글 본문 " + m.comments.length + "개\n" + (m.comments.length ? m.comments.map((c, i) => `${i + 1}. ${c}`).join("\n") : "(수집된 댓글 없음)"),
  });
  content.push({ type: "text", text: "## 대표 장면" });
  for (const f of m.frames) {
    content.push({ type: "text", text: `[t=${f.t}s, ${f.kind}]` });
    content.push({ type: "image", source: { type: "base64", media_type: "image/jpeg", data: f.dataUrl.split(",")[1] } });
  }
  content.push({ type: "text", text: "위 자료로 이 숏폼을 분석해 주세요." });

  const { text, usage, model: served } = await callClaude({
    model,
    max_tokens: 16000,
    system: ANALYSIS_SYSTEM,
    output_config: { effort, format: { type: "json_schema", schema: ANALYSIS_SCHEMA } },
    messages: [{ role: "user", content }],
  });
  let parsed;
  try { parsed = JSON.parse(text); } catch (e) { throw new Error("분석 결과를 읽지 못했어요. 다시 시도해 주세요."); }
  return { analysis: parsed, usage, model: served };
}

export async function makeConti(report, modeKey, topic) {
  const { model, effort } = await getSettings();
  const mode = CONTI_MODES[modeKey];
  const userText = [
    "## 원본 분석 결과",
    "```json\n" + JSON.stringify(report.analysis) + "\n```",
    "## 원본 측정값",
    "```json\n" + JSON.stringify(report.measure) + "\n```",
    "## 새 소재",
    topic || "로빈의밥상 쇼츠에 어울리는 제철 집밥 소재를 하나 골라서",
    "## 만들 것: " + mode.label,
    mode.instruction,
  ].join("\n\n");
  const { text, usage, model: served } = await callClaude({
    model,
    max_tokens: 16000,
    system: CONTI_SYSTEM,
    output_config: { effort },
    messages: [{ role: "user", content: userText }],
  });
  return { markdown: text, usage, model: served };
}

// 대략적인 비용(원). 1달러 = 1,400원 가정.
const PRICE = { "claude-opus-5-5": [4, 20], "claude-sonnet-5-5": [2, 10] };
export function costKRW(usage, model) {
  if (!usage) return null;
  const key = Object.keys(PRICE).find((k) => (model || "").startsWith(k)) || "claude-opus-5-5";
  const [pi, po] = PRICE[key];
  const usd = ((usage.input_tokens || 0) * pi + (usage.output_tokens || 0) * po) / 1e6;
  return Math.round(usd * 1400);
}
