// 밥상스코프 측정 엔진: 페이지에서 지금 보이는 영상을 처음부터 한 번 재생하며
// 컷·샷·움직임·색·소리 크기·박자를 재고, 대표 장면 이미지와 캡션·댓글을 모은다.
// 영상 파일은 어디에도 저장하지 않는다. 측정이 끝나면 원래 재생 상태로 되돌린다.
(() => {
  if (window.__bapsangScopeLoaded) return;
  window.__bapsangScopeLoaded = true;

  const MAX_SECONDS = 180;      // 이보다 긴 영상은 앞부분만 잰다
  const MAX_FRAMES = 24;        // Claude에게 보낼 대표 장면 수 상한
  const SMALL_W = 64, SMALL_H = 36;
  const SHOT_W = 512;

  const progress = (pct, text) =>
    chrome.runtime.sendMessage({ type: "measure-progress", pct, text }).catch(() => {});

  function platformOf() {
    const h = location.hostname;
    if (h.includes("instagram")) return "instagram";
    if (h.includes("threads")) return "threads";
    if (h.includes("youtube")) return "youtube";
    return "other";
  }

  // 화면에 가장 크게 보이는 영상을 고른다(재생 중이면 가산점).
  function pickVideo() {
    const vids = [...document.querySelectorAll("video")];
    let best = null, bestScore = 0;
    for (const v of vids) {
      const r = v.getBoundingClientRect();
      const w = Math.max(0, Math.min(r.right, innerWidth) - Math.max(r.left, 0));
      const h = Math.max(0, Math.min(r.bottom, innerHeight) - Math.max(r.top, 0));
      let score = w * h;
      if (!v.paused) score *= 2;
      if (v.readyState < 2) score *= 0.5;
      if (score > bestScore) { bestScore = score; best = v; }
    }
    return best;
  }

  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  function once(el, ev, timeout = 5000) {
    return new Promise((resolve) => {
      const t = setTimeout(resolve, timeout);
      el.addEventListener(ev, () => { clearTimeout(t); resolve(); }, { once: true });
    });
  }

  // ---------- 텍스트 수집 ----------
  function maskMentions(s) { return s.replace(/@[\w.\-가-힣]+/g, "@○○"); }

  function collectCaption() {
    const parts = [];
    const og = document.querySelector('meta[property="og:description"]')?.content;
    const ogt = document.querySelector('meta[property="og:title"]')?.content;
    if (ogt) parts.push(ogt);
    if (og && og !== ogt) parts.push(og);
    if (platformOf() === "youtube") {
      const t = document.querySelector("ytd-reel-video-renderer[is-active] h2, yt-shorts-video-title-view-model, h1.ytd-watch-metadata")?.innerText;
      if (t) parts.unshift(t);
    }
    if (!parts.length) parts.push(document.title);
    return maskMentions([...new Set(parts.map((s) => s.trim()).filter(Boolean))].join("\n").slice(0, 2000));
  }

  // 댓글: 작성자 이름은 모으지 않고 본문만. @멘션은 가린다.
  function collectComments(captionText) {
    const out = new Set();
    const p = platformOf();
    if (p === "youtube") {
      document.querySelectorAll("ytd-comment-thread-renderer #content-text, ytd-comment-view-model #content-text")
        .forEach((el) => out.add(el.innerText.trim()));
    } else {
      // 인스타·쓰레드는 클래스 이름이 수시로 바뀌므로 구조로 추정한다.
      // 링크 안의 글(=계정 이름)은 빼고, 2자 이상 본문만.
      const scope = document.querySelector('div[role="dialog"]') || document.querySelector("main") || document.body;
      scope.querySelectorAll('span[dir="auto"]').forEach((el) => {
        if (el.closest("a")) return;
        const t = el.innerText.trim();
        if (t.length < 2 || t.length > 500) return;
        if (/^(좋아요|답글|댓글|번역 보기|더 보기|숨기기|\d+[주일시분초]|\d+\s*(likes?|replies?))/.test(t)) return;
        if (captionText && captionText.includes(t)) return;
        out.add(t);
      });
    }
    return [...out].filter(Boolean).slice(0, 150).map(maskMentions);
  }

  // ---------- 영상 측정 ----------
  function histAndLuma(data) {
    const hist = new Float32Array(48);
    const luma = new Float32Array(SMALL_W * SMALL_H);
    let rs = 0, gs = 0, bs = 0;
    for (let i = 0, p = 0; i < data.length; i += 4, p++) {
      const r = data[i], g = data[i + 1], b = data[i + 2];
      hist[r >> 4]++; hist[16 + (g >> 4)]++; hist[32 + (b >> 4)]++;
      luma[p] = 0.299 * r + 0.587 * g + 0.114 * b;
      rs += r; gs += g; bs += b;
    }
    const n = SMALL_W * SMALL_H;
    for (let i = 0; i < 48; i++) hist[i] /= n;
    return { hist, luma, rgb: [rs / n, gs / n, bs / n] };
  }
  function histDist(a, b) { let s = 0; for (let i = 0; i < 48; i++) s += Math.abs(a[i] - b[i]); return s / 6; } // 0~1
  function lumaDiff(a, b) { let s = 0; for (let i = 0; i < a.length; i++) s += Math.abs(a[i] - b[i]); return s / a.length; }

  function rgbToHsl([r, g, b]) {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    const l = (max + min) / 2;
    let h = 0, s = 0;
    if (max !== min) {
      const d = max - min;
      s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
      h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
      h *= 60;
    }
    return { h: Math.round(h), s: Math.round(s * 100), l: Math.round(l * 100) };
  }
  function hueName(h, s, l) {
    if (l < 15) return "어두움"; if (l > 88) return "밝은 흰색"; if (s < 15) return "무채색";
    if (h < 20 || h >= 340) return "빨강"; if (h < 45) return "주황"; if (h < 70) return "노랑";
    if (h < 160) return "초록"; if (h < 200) return "청록"; if (h < 260) return "파랑"; return "보라";
  }

  // 박자 추정: 소리 에너지 변화(온셋)의 자기상관으로 BPM을 찾고, 박 위치를 맞춘다.
  function estimateBeats(onsets, rate, duration) {
    if (onsets.length < rate * 4) return null;
    const mean = onsets.reduce((a, b) => a + b, 0) / onsets.length;
    const x = onsets.map((v) => Math.max(0, v - mean));
    let bestLag = 0, bestVal = 0;
    const minLag = Math.round((60 / 180) * rate), maxLag = Math.round((60 / 70) * rate);
    for (let lag = minLag; lag <= maxLag; lag++) {
      let s = 0;
      for (let i = 0; i + lag < x.length; i++) s += x[i] * x[i + lag];
      s /= (x.length - lag);
      if (s > bestVal) { bestVal = s; bestLag = lag; }
    }
    if (!bestLag || bestVal <= 0) return null;
    let bestOff = 0, bestSum = -1;
    for (let off = 0; off < bestLag; off++) {
      let s = 0; for (let i = off; i < x.length; i += bestLag) s += x[i];
      if (s > bestSum) { bestSum = s; bestOff = off; }
    }
    const period = bestLag / rate;
    const beats = [];
    for (let t = bestOff / rate; t <= duration; t += period) beats.push(+t.toFixed(3));
    // 신뢰도: 박 위치의 평균 에너지 / 전체 평균 에너지
    const xm = x.reduce((a, b) => a + b, 0) / x.length || 1;
    const confidence = Math.min(1, (bestSum / Math.max(1, beats.length)) / xm / 4);
    return { bpm: Math.round(60 / period), beats, confidence: +confidence.toFixed(2) };
  }

  async function measure(opts = {}) {
    const video = pickVideo();
    if (!video) throw new Error("화면에서 영상을 찾지 못했어요. 영상이 보이는 상태에서 다시 눌러 주세요.");
    if (!isFinite(video.duration) || video.duration <= 0) {
      await once(video, "loadedmetadata", 4000);
      if (!isFinite(video.duration) || video.duration <= 0) throw new Error("영상 길이를 읽지 못했어요. 영상이 재생된 뒤 다시 시도해 주세요.");
    }
    const duration = Math.min(video.duration, MAX_SECONDS);
    const saved = { t: video.currentTime, muted: video.muted, paused: video.paused, rate: video.playbackRate, loop: video.loop };

    const small = document.createElement("canvas"); small.width = SMALL_W; small.height = SMALL_H;
    const sctx = small.getContext("2d", { willReadFrequently: true });
    const aspect = (video.videoHeight || 16) / (video.videoWidth || 9);
    const big = document.createElement("canvas"); big.width = SHOT_W; big.height = Math.round(SHOT_W * aspect);
    const bctx = big.getContext("2d");

    // 캔버스 읽기 가능 여부(다른 도메인 영상이면 막힘) 확인
    try { sctx.drawImage(video, 0, 0, SMALL_W, SMALL_H); sctx.getImageData(0, 0, 1, 1); }
    catch (e) { throw new Error("이 영상은 브라우저 보안 정책 때문에 화면을 읽을 수 없어요."); }

    progress(3, "영상을 처음으로 되감는 중");
    video.loop = false;
    video.pause();
    video.currentTime = 0;
    await once(video, "seeked", 4000);

    // 소리 측정 준비: 영상의 소리를 복제해서 듣는다(원래 소리 출력은 그대로).
    let audioCtx = null, analyser = null, freqPrev = null, audioOk = false;
    try {
      video.muted = false;
      const stream = video.captureStream ? video.captureStream() : null;
      if (stream && stream.getAudioTracks().length) {
        audioCtx = new AudioContext();
        const src = audioCtx.createMediaStreamSource(new MediaStream(stream.getAudioTracks()));
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 1024;
        src.connect(analyser); // 스피커에는 연결하지 않음(소리 이중 출력 방지)
        if (audioCtx.state === "suspended") await audioCtx.resume().catch(() => {});
        audioOk = true;
      }
    } catch (e) { audioOk = false; }

    const frameStats = [];   // {t, hd, ld, rgb}
    const cuts = [0];
    const frames = [];       // {t, kind, dataUrl}
    const audio = [];        // {t, rms, flux}
    let prev = null, lastCut = 0, lastCapture = -10, pendingCutCapture = null;

    const capture = (t, kind) => {
      bctx.drawImage(video, 0, 0, big.width, big.height);
      frames.push({ t: +t.toFixed(2), kind, dataUrl: big.toDataURL("image/jpeg", 0.72) });
      lastCapture = t;
    };

    const AUDIO_RATE = 50;
    const audioTimer = audioOk ? setInterval(() => {
      if (video.paused) return;
      const td = new Float32Array(analyser.fftSize);
      analyser.getFloatTimeDomainData(td);
      let s = 0; for (const v of td) s += v * v;
      const rms = Math.sqrt(s / td.length);
      const fd = new Uint8Array(analyser.frequencyBinCount);
      analyser.getByteFrequencyData(fd);
      let flux = 0;
      if (freqPrev) for (let i = 0; i < fd.length; i++) { const d = fd[i] - freqPrev[i]; if (d > 0) flux += d; }
      freqPrev = fd;
      audio.push({ t: +video.currentTime.toFixed(3), rms, flux });
    }, 1000 / AUDIO_RATE) : null;

    await new Promise(async (resolve, reject) => {
      let done = false;
      const finish = () => { if (!done) { done = true; resolve(); } };
      const hasRVFC = "requestVideoFrameCallback" in HTMLVideoElement.prototype;
      const onFrame = (now, meta) => {
        if (done) return;
        const t = meta ? meta.mediaTime : video.currentTime;
        if (t >= duration - 0.04 || (prev && t + 0.5 < prev.t)) { finish(); return; } // 끝 또는 되감김(반복 재생)
        sctx.drawImage(video, 0, 0, SMALL_W, SMALL_H);
        const { hist, luma, rgb } = histAndLuma(sctx.getImageData(0, 0, SMALL_W, SMALL_H).data);
        let hd = 0, ld = 0;
        if (prev) { hd = histDist(hist, prev.hist); ld = lumaDiff(luma, prev.luma); }
        const isCut = prev && (t - lastCut) > 0.25 && (hd > 0.42 || (hd > 0.22 && ld > 42));
        if (isCut) { cuts.push(+t.toFixed(3)); lastCut = t; pendingCutCapture = t + 0.12; }
        frameStats.push({ t, hd, ld: isCut ? 0 : ld, rgb });
        prev = { t, hist, luma };
        if (frames.length === 0) capture(t, "시작");
        else if (pendingCutCapture !== null && t >= pendingCutCapture) { capture(t, "컷"); pendingCutCapture = null; }
        else if (t - lastCapture >= 1.5) capture(t, "흐름");
        progress(5 + Math.round((t / duration) * 85), `측정 중 ${t.toFixed(1)}초 / ${duration.toFixed(1)}초`);
        if (hasRVFC) video.requestVideoFrameCallback(onFrame); else setTimeout(() => onFrame(0, null), 33);
      };
      video.addEventListener("ended", finish, { once: true });
      // 안전장치: 영상 길이 + 15초 지나면 강제 종료
      setTimeout(finish, (duration / (opts.rate || 1)) * 1000 + 15000);
      try {
        video.playbackRate = opts.rate || 1;
        await video.play();
      } catch (e) { reject(new Error("영상을 재생하지 못했어요. 영상을 한 번 클릭한 뒤 다시 시도해 주세요.")); return; }
      if (hasRVFC) video.requestVideoFrameCallback(onFrame); else onFrame(0, null);
    });

    if (audioTimer) clearInterval(audioTimer);
    if (audioCtx) audioCtx.close().catch(() => {});

    // 원래 상태로 복구
    video.playbackRate = saved.rate;
    video.loop = saved.loop;
    video.muted = saved.muted;
    try { video.currentTime = saved.t; } catch (e) {}
    if (saved.paused) video.pause(); else video.play().catch(() => {});

    progress(92, "측정값 정리 중");

    // ---------- 샷 정리 ----------
    const endT = frameStats.length ? frameStats[frameStats.length - 1].t : duration;
    const bounds = [...cuts, endT];
    const shots = [];
    for (let i = 0; i < bounds.length - 1; i++) {
      const s = bounds[i], e = bounds[i + 1];
      const fs = frameStats.filter((f) => f.t >= s && f.t < e);
      if (!fs.length || e - s < 0.05) continue;
      const rgb = [0, 1, 2].map((k) => fs.reduce((a, f) => a + f.rgb[k], 0) / fs.length);
      const motion = fs.reduce((a, f) => a + f.ld, 0) / fs.length;
      const hsl = rgbToHsl(rgb);
      shots.push({
        index: shots.length + 1,
        start: +s.toFixed(3), end: +e.toFixed(3), length: +(e - s).toFixed(3),
        frames30: Math.round((e - s) * 30),
        color: `rgb(${rgb.map(Math.round).join(",")})`,
        colorName: hueName(hsl.h, hsl.s, hsl.l), brightness: hsl.l, saturation: hsl.s,
        motion: +motion.toFixed(1),
        camera: motion < 3.5 ? "고정" : motion < 10 ? "약한 움직임" : "큰 움직임",
      });
    }

    // ---------- 소리 ----------
    const audioSilent = !audio.length || audio.every((a) => a.rms < 0.0005);
    const loudness = [];
    if (!audioSilent) {
      const maxRms = Math.max(...audio.map((a) => a.rms)) || 1;
      for (let t = 0; t < endT; t += 0.5) {
        const seg = audio.filter((a) => a.t >= t && a.t < t + 0.5);
        if (!seg.length) continue;
        const r = seg.reduce((a, b) => a + b.rms, 0) / seg.length;
        // dB 비슷하게 눌러서 0~100으로
        const v = Math.max(0, 100 + 20 * Math.log10(r / maxRms) * 2.5);
        loudness.push({ t: +t.toFixed(1), v: Math.round(Math.min(100, v)) });
      }
    }
    // 타이머 간격이 들쭉날쭉하므로 실제 재생 시각 기준 격자(1/50초)에 다시 놓는다.
    const onsets = new Array(Math.ceil(endT * AUDIO_RATE) + 1).fill(0);
    for (const a of audio) {
      const k = Math.round(a.t * AUDIO_RATE);
      if (k >= 0 && k < onsets.length) onsets[k] = Math.max(onsets[k], a.flux);
    }
    const beat = audioSilent ? null : estimateBeats(onsets, AUDIO_RATE, endT);
    let beatAlignedRatio = null;
    if (beat && cuts.length > 1) {
      const tol = Math.min(0.1, (60 / beat.bpm) / 4);
      const realCuts = cuts.slice(1);
      const hit = realCuts.filter((c) => beat.beats.some((b) => Math.abs(b - c) <= tol)).length;
      beatAlignedRatio = Math.round((hit / realCuts.length) * 100);
    }

    // ---------- 대표 장면 줄이기 ----------
    let sendFrames = frames;
    if (frames.length > MAX_FRAMES) {
      const cutsF = frames.filter((f) => f.kind !== "흐름");
      const flowF = frames.filter((f) => f.kind === "흐름");
      let pick = cutsF.length > MAX_FRAMES
        ? cutsF.filter((_, i) => i % Math.ceil(cutsF.length / MAX_FRAMES) === 0)
        : [...cutsF, ...flowF.filter((_, i) => i % Math.ceil(flowF.length / Math.max(1, MAX_FRAMES - cutsF.length)) === 0)];
      sendFrames = pick.sort((a, b) => a.t - b.t).slice(0, MAX_FRAMES);
    }

    const avgShot = shots.length ? shots.reduce((a, s) => a + s.length, 0) / shots.length : endT;
    const camCount = shots.reduce((m, s) => ((m[s.camera] = (m[s.camera] || 0) + s.length), m), {});
    const mainCamera = Object.entries(camCount).sort((a, b) => b[1] - a[1])[0]?.[0] || "알 수 없음";

    const caption = collectCaption();
    progress(97, "캡션·댓글 모으는 중");
    const comments = collectComments(caption);

    return {
      platform: platformOf(),
      url: location.href,
      pageTitle: document.title,
      measuredAt: new Date().toISOString(),
      duration: +endT.toFixed(2),
      truncated: video.duration > MAX_SECONDS,
      shots,
      cuts,
      avgShotLength: +avgShot.toFixed(2),
      cutsPerMinute: +((Math.max(0, cuts.length - 1) / Math.max(1, endT)) * 60).toFixed(1),
      mainCamera,
      audioAvailable: !audioSilent,
      loudness,
      bpm: beat ? beat.bpm : null,
      bpmConfidence: beat ? beat.confidence : null,
      beats: beat ? beat.beats : [],
      beatAlignedRatio,
      frames: sendFrames,
      caption,
      comments,
    };
  }

  let busy = false;
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg?.type === "ping") { sendResponse({ ok: true, platform: platformOf() }); return; }
    if (msg?.type === "collect-comments") {
      sendResponse({ ok: true, comments: collectComments(collectCaption()) });
      return;
    }
    if (msg?.type !== "measure") return;
    if (busy) { sendResponse({ ok: false, error: "이미 측정 중이에요." }); return; }
    busy = true;
    measure(msg.opts)
      .then((data) => sendResponse({ ok: true, data }))
      .catch((e) => sendResponse({ ok: false, error: e.message || String(e) }))
      .finally(() => { busy = false; });
    return true; // 비동기 응답
  });
})();
