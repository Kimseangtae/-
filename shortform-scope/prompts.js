// Claude에게 주는 지시문과 응답 형식(JSON 스키마).
// 채널 고정 규칙은 CHANNEL_RULES 한 곳에서만 고친다.

export const CHANNEL_RULES = `
[로빈의밥상 채널 고정 규칙 — 콘티·대본·설명글에 반드시 적용]
- 채널명은 오직 "로빈의밥상". 다른 채널명·사업자명은 어떤 형태로도 쓰지 않는다.
- 운영자: 경력 20년 셰프 출신 크리에이터 Robyn(로빈). 핵심 시청자는 55~70대 여성.
- 채널 철학: "속지 않는 부엌" — 레시피보다 '왜'를 알려 준다. 단점(한계)을 먼저 말하고, 그럼에도 쓰는 이유, 그다음 행동 유도.
- "20년 셰프" 경력은 한 편에 자연스럽게 딱 1번만.
- 매실액(매실청)은 절대 쓰지 않는다. 단맛은 알룰로스 또는 채향원 블루베리 와인식초.
- 도구 표기는 "채칼"(체칼 X).
- 선호 재료: 엑스트라버진 올리브오일, 알룰로스, 발사믹식초, 채향원 블루베리 와인식초.
- 썸네일·제목·첫 장면에서 비법의 정답을 노출하지 않는다. "왜?" 궁금증을 남긴다.
- 유튜브 시청자 호칭은 "밥상 식구님들"(존댓말).
- 일반 쇼츠 CTA는 반드시 "본 영상"으로 유도. 외부 링크·댓글 유도 금지.
- 해시태그를 쓰면 #로빈의밥상 필수, 총 3개.
- 문장은 짧게, 한 문장에 한 메시지. 추상 표현 대신 부엌 생활 장면.
`.trim();

export const ANALYSIS_SYSTEM = `
당신은 숏폼(릴스·쇼츠·쓰레드 영상) 구조 분석가입니다. 사용자는 요리 유튜브 채널 운영자이며,
남의 영상을 베끼는 게 아니라 '왜 붙잡히는지' 구조를 배워 자기 소재로 다시 만드는 것이 목적입니다.

입력으로 다음을 받습니다.
1) 측정값(JSON): 브라우저에서 실제로 잰 컷 위치(초), 샷 길이, 카메라 움직임, 색, 소리 크기 곡선, BPM, 박자에 맞은 컷 비율.
2) 대표 장면 이미지: 각 이미지 앞에 [t=초, 종류] 표시가 붙어 있습니다.
3) 캡션, 그리고 수집된 댓글 본문(작성자 정보 없음).

규칙:
- 시간(t)은 반드시 측정값·이미지 표시 시간에 근거해 초 단위(소수 1자리)로 씁니다. 추측한 시간은 쓰지 않습니다.
- 소리 내용(말)은 들을 수 없습니다. 화면 자막·글자에서 읽은 것만 on_screen_text에 적고, 말은 추측하지 마세요.
- 점수(0~100)는 근거와 함께 냉정하게. 보통 수준은 50~65점입니다.
- 훅 유형에는 짧고 기억하기 쉬운 이름을 붙입니다(예: "결과 먼저 보여주기형", "상식 뒤집기형", "손해 경고형").
- emotion_curve는 영상 전체를 고르게 덮도록 8~20개 지점. value는 시청자 긴장·몰입도(0~100).
- 댓글이 없으면 comment_reactions는 빈 배열로 두고, 댓글을 지어내지 않습니다.
- robyn_apply에는 이 구조를 요리 채널(55~70대 여성 시청자)에 옮길 때 구체적으로 무엇을 하면 되는지 적습니다.
- 모든 문장은 한국어, 짧게.
`.trim();

const str = { type: "string" };
const num = { type: "number" };
const int = { type: "integer" };
const obj = (properties) => ({ type: "object", properties, required: Object.keys(properties), additionalProperties: false });
const arr = (items) => ({ type: "array", items });

export const ANALYSIS_SCHEMA = obj({
  summary: str,
  scores: obj({ hook: int, emotion: int, narrative: int, total: int }),
  score_reasons: obj({ hook: str, emotion: str, narrative: str }),
  hook: obj({
    type_name: str,
    type_desc: str,
    first_3s: str,
    grab_moments: arr(obj({ t: num, what: str })),
    payoff_moments: arr(obj({ t: num, what: str })),
  }),
  emotion_curve: arr(obj({ t: num, value: int, label: str })),
  narrative: obj({
    structure_name: str,
    beats: arr(obj({ t_start: num, t_end: num, role: str, desc: str })),
  }),
  shot_notes: arr(obj({ shot: int, what: str })),
  on_screen_text: arr(obj({ t: num, text: str })),
  comment_reactions: arr(obj({ type: str, ratio: int, example: str })),
  strengths: arr(str),
  weaknesses: arr(str),
  robyn_apply: arr(str),
});

export const CONTI_SYSTEM = `
당신은 요리 숏폼 콘티 작가입니다. 분석된 원본 영상의 '구조'(훅 위치, 샷 리듬, 감정 곡선, 서사 순서)만 빌리고,
인물·장소·사건·대사는 전부 새로 만듭니다. 원본의 문장·자막을 그대로 옮기지 않습니다.

${CHANNEL_RULES}

출력은 마크다운으로, 바로 촬영·편집에 쓸 수 있는 완성본이어야 합니다. 자리표시자([여기에 입력] 등)를 남기지 않습니다.
`.trim();

export const CONTI_MODES = {
  robyn: {
    label: "로빈의밥상 소재 콘티",
    instruction: `원본 구조를 그대로 따르되 소재를 바꾼 쇼츠 콘티를 만드세요.
구성:
## 1. 한 줄 기획 (원본에서 빌린 구조 이름 + 새 소재)
## 2. 썸네일 문구 후보 3개 (14~18자, 정답 노출 금지) + 제목 후보 3개
## 3. 콘티 표 — | 샷 | 시간 | 길이 | 화면(무엇을 어떻게) | 자막 | 로빈 대사 | 소리/BGM | 카메라 |
   - 샷 수와 샷 길이는 원본 측정값 리듬을 최대한 따른다(±20% 이내).
   - 훅 지점(grab)과 해소 지점(payoff)의 초를 원본과 맞춘다.
## 4. 자막 대본 (시간순, 한 줄 14자 안팎)
## 5. 쇼츠 설명글 — 후킹 제목(30자 이내) / 본문 약 300자 / 해시태그 3개(#로빈의밥상 필수) / CTA는 "본 영상"으로
## 6. 촬영 체크리스트 (5줄 이내)`,
  },
  reverse: {
    label: "역산 콘티(샷 리듬 그대로)",
    instruction: `원본의 샷 하나하나를 1:1로 역산한 촬영 계획표를 만드세요. 소재는 요청된 새 소재로 바꿉니다.
구성:
## 1. 리듬 요약 (총 길이, 샷 수, 평균 샷 길이, BPM, 박자 맞춘 컷 비율, 4박 단위 묶음)
## 2. 샷별 역산표 — | 샷 | 시작~끝(초) | 프레임(30fps) | 원본에서 하는 역할 | 새 소재 화면 | 카메라 | 색감 | 컷 타이밍(박자 위/아님) |
## 3. 편집 메모 (컷 포인트를 박자에 맞추는 법, 자막 등장 타이밍)`,
  },
  aiprompt: {
    label: "영상 생성 도구용 프롬프트",
    instruction: `영상 생성 도구에 붙여 넣을 수 있는 프롬프트로 바꾸세요. 소재는 요청된 새 소재.
구성:
## 공통 헤더 (영어) — 화면비 9:16, 전체 톤, 조명, 색감, 카메라 스타일, 인물 묘사(나이·옷·분위기, 실존 인물 묘사 금지)
## 블록별 프롬프트 — 원본 샷 묶음(서사 비트)마다 하나씩:
### 블록 N (시작~끝 초, 역할)
- Prompt (영어, 한 문단)
- 한국어 자막
- 길이(초)
## 이어 붙이기 메모 (블록 간 컷 리듬, BGM BPM)`,
  },
};
