---
name: gongu-lab
description: >
  로빈님(로빈의밥상)의 공동구매 콘텐츠 레퍼런스 분석 + 일정 기반 자동 제작.
  (A) 인스타그램 레퍼런스 계정의 캐러셀·릴스를 수집해 슬라이드 이미지를 직접 판독하고,
  공구 소구점 풀이·구조·반응(좋아요/댓글)을 분석해 "어떤 콘텐츠가 효율 좋은지" 알려준다.
  (B) 공구 일정을 받으면 레퍼런스에서 확인한 구조로 일자별 콘텐츠(대본·설명글·고정댓글·쇼츠·릴스·캐러셀·스레드)를
  만들어 두고 매일 올릴 것을 알려준다.
  "공구 레퍼런스 분석", "캐러셀 분석", "공구 일정 등록", "오늘 올릴 것", "공구 콘텐츠 만들어줘", "gongu lab" 요청 시 사용.
---

# gongu-lab: 레퍼런스에서 공구 구조를 배워 일정대로 만든다

## 원칙
- **구조는 따르고 표현은 로빈님 것으로.** 순서·역할·길이·CTA 위치는 레퍼런스를 그대로 따른다. 문장, 이미지, 제품 주장은 베끼지 않는다.
- **제품 사실은 지어내지 않는다.** 가격, 수량, 마감, 성분, 단점은 `schedule.json` 에 있는 것만 쓴다. 없으면 쓰지 말고 로빈님께 묻는다.
- **표본이 작으면 결론이 아니라 가설이라고 쓴다.** 캐러셀 12개 미만, 공구 게시물 3개 미만이면 반드시 표시.
- 제작 규칙은 `gongu-lab/guidelines.md` 를 먼저 읽는다 (금지 목록, 플랫폼 규격, 공구 규칙).
- 경로는 저장소 루트 기준. 파이썬은 `python3` (Windows 는 `python`).

## 모드 A. 레퍼런스 분석

### A1. 수집
레퍼런스 채널은 `gongu-lab/references.json` (`platform`: instagram / youtube). 비어 있으면 로빈님께 채널 핸들을 묻고 등록한다.

**인스타 (캐러셀 포함, PC 에서)**
```bash
python3 gongu-lab/ig_collect.py --all            # references.json 의 instagram 전부
python3 gongu-lab/ig_collect.py 핸들 --repair     # 슬라이드가 모자란 캐러셀만 재시도
```
출력 마지막 줄의 "슬라이드 완전 수집 / 불완전" 개수를 반드시 확인한다. 불완전이 남으면 `--repair`, 그래도 안 되면
`--debug --show` 로 원인을 보고 사용자에게 알린다. **불완전한 캐러셀은 분석 대상에서 빼고 그 사실을 보고서에 적는다.**
로그인 프로필이 없으면 "`ig_collect.py --login` 필요" 한 줄 안내 후 중단.
수집 전에 `ig_collect.py --doctor` 로 토큰·권한·계정·조회 가능 여부를 점검하고, 출력의 '다음에 할 일' 을 그대로 로빈님께 전한다. 토큰이 없거나 만료면 `--set-token` 안내. 처음 쓰는 계정은 `--check 핸들…` 로 슬라이드까지 오는지 확인한다. 공식 API 가 막힌 계정은 `--all` 실행 시 로그인 브라우저 방식으로 자동 전환된다.

**인스타 릴스·유튜브 (세션 안에서 vidIQ 로)**
- 릴스: `vidiq_ig_profile_reels`(최대 12개), `vidiq_instagram_tiktok_outlier_search`, `vidiq_watch_shortform_content`
- 유튜브: `vidiq_channel_videos`(long/short, popular true/false) 결과를 `gongu-lab/data/videos/<채널>.json` 로 저장 → `analyze_videos.py` 로 분석.
  설명·고정댓글은 `vidiq_video_comments`, 대본은 `vidiq_video_transcript`. 크레딧이 드니(호출당 5) 상위 영상 위주로.
- vidIQ 는 **캐러셀을 지원하지 않는다.** 캐러셀은 위 ig_collect 만 가능.

### A2. 캐러셀 판독 (핵심)
```bash
python3 gongu-lab/ig_analyze.py rank 핸들 --k 8      # 상위 8 + 하위 8 을 queue.json 에
python3 gongu-lab/ig_analyze.py sheet 핸들 코드       # (선택) 한눈에 보는 sheet.jpg
```
- `queue.json` 에서 status 가 `needs_analysis` 인 캐러셀마다 `.claude/skills/gongu-lab/carousel-analysis.md` 의 규칙대로
  슬라이드를 **한 장씩 Read** 하고 `data/ig/<핸들>/<코드>/analysis.json` 을 쓴다. 상위와 하위를 **같은 기준으로** 읽어야 대조가 된다.
- 6개를 넘으면 Agent 로 나눠 맡길 수 있다. 각 에이전트에게 판독 규칙 파일 경로, 대상 코드, 출력 경로를 주고,
  끝난 뒤 **내가 직접** `validate` 를 돌려 결과를 확인한다(에이전트의 "완료" 보고를 그대로 믿지 않는다).
- `python3 gongu-lab/ig_analyze.py validate 핸들` 이 오류 0건일 때까지 고친다. 오류는 대개 장수 누락·허용 값 위반·빈 text.

### A3. 통계와 보고서
```bash
python3 gongu-lab/ig_analyze.py stats --out gongu-lab/analysis/carousel-patterns.md
python3 gongu-lab/analyze_videos.py gongu-lab/data/videos/*.json --tags gongu-lab/data/tags.json   # 유튜브가 있을 때
```
`gongu-lab/analysis/YYYY-MM-DD.md` 를 쓴다. 구성:
1. **공구 소구점 풀이** — 난이도 해소 / 속도 향상 / 선택 대행 별로 레퍼런스가 실제로 어떻게 풀었는지 대표 사례 1~2개(게시물 링크 + 슬라이드/컷 구조).
2. **반응 상위 vs 하위 대조** — 같은 계정의 상위·하위가 구조/훅/CTA/글자 밀도에서 어떻게 다른지. 수치(점수, 좋아요 대비, 댓글)와 함께.
3. **공구 게시물의 타임라인** — 공구 연결 게시물(`gongu: true`)이 오픈 며칠 전부터 어떤 형식으로 나오는지. 날짜는 `taken_at`.
4. **로빈님께 효율 좋은 콘텐츠 3가지** — 각각 (무엇을 / 어떤 구조로 / 근거 수치 / 로빈님 지침과 충돌 여부). 지침과 충돌하면(예: 과장, 단점 숨김) 구조만 빌리고 충돌 부분은 바꾼다고 명시.
5. **한계** — 표본 수, 저장·공유·도달 미확인, 좋아요 숨김 게시물 수, 불완전 수집 건수, 공구 여부는 정황 판단(확정은 로빈님).

3번 결과가 기본 타임라인과 다르면 `playbook.json` 수정안을 **제안만** 하고, 로빈님이 승인하면 반영한다. 승인 없이 바꾸지 않는다.

## 모드 B. 일정 → 제작 → 매일 전달

### B1. 일정 등록
`gongu-lab/schedule.json` (형식은 `schedule.example.json`). 필수: id, product, category, appeal, open_date, **drawbacks 1개 이상**.
로빈님이 말로 알려주면 대신 만든다. 빠진 값은 지어내지 말고 묻는다 (특히 가격, 수량, 단점, 마감일).
```bash
python3 gongu-lab/plan_calendar.py plan          # calendar/<ID>.md 생성, 빠진 정보는 알려주고 멈춤
```

### B2. 제작
```bash
python3 gongu-lab/plan_calendar.py brief <캠페인ID> <날짜>     # 그 날 만들 산출물 지시서(JSON)
```
- 지시서의 각 `items[].file` 경로에 파일을 쓴다. 파일명이 곧 산출물 종류다(`lint_content.py` 가 이름으로 규칙을 정한다).
- 쓰기 전에 읽을 것: `guidelines.md`, 가장 최근 `analysis/YYYY-MM-DD.md`(구조), 해당 슬롯의 `rule`.
- 대본(`script`)은 **썸네일 문구 + 제목 후보를 먼저** 확정한 뒤 6막으로. 캐러셀(`carousel`)은 분석에서 확인한 상위 구조(장수·역할 순서·CTA 위치)를 따라 슬라이드별 문구를 쓴다.
- 파일 맨 위 `<!-- ... -->` 주석에 근거를 남긴다(어느 분석의 어느 패턴을 따랐는지). 검사에서 제외된다.
- 쓴 뒤 반드시:
```bash
python3 gongu-lab/lint_content.py gongu-lab/output/<캠페인ID>/<날짜>_*.md
```
오류 0건이 될 때까지 고친다. 경고는 읽고 판단한다.
- 스레드·릴스 등 여러 플랫폼에 같은 내용을 쓸 때 호칭·어미를 플랫폼별로 다시 쓴다.

### B3. 매일 전달
```bash
python3 gongu-lab/plan_calendar.py today          # 오늘 올릴 것 + 밀린 것 + 검사 결과
python3 gongu-lab/plan_calendar.py done <항목ID>   # 업로드 후 표시
python3 gongu-lab/plan_calendar.py status
```
`today` 결과를 대화에 붙이고, 오늘·내일 항목 중 미작성이 있으면 B2 로 만든다(기본 2일 앞까지).
이 도구는 **파일을 준비할 뿐 업로드는 하지 않는다.** 유튜브 스튜디오 예약 게시, 인스타·스레드 게시는 로빈님이 한다.

### B4. 커밋
`git add gongu-lab && git commit -m "gongu-lab: <캠페인ID> <날짜> 콘텐츠"` 후 현재 브랜치 push.
슬라이드 이미지는 `.gitignore` 로 제외돼 있다(타인 저작물, 용량). `posts.json` 과 `analysis.json`, `analysis/` 보고서만 올라간다.
**저장소가 공개일 때** `schedule.json`, `output/`, `calendar/`, `state/` 도 제외돼 있다(오픈 전 가격·일정·초안 유출 방지). 이 파일들을 `git add -f` 로 억지로 올리지 않는다.
저장소가 비공개로 바뀌었다고 로빈님이 확인해 줄 때만 `.gitignore` 의 보호 블록을 지우고 올린다.

## 하지 않는 것
- 레퍼런스의 문장·이미지·제품 주장 복사
- 확인하지 않은 가격·수량·마감·효능 서술, 허위 희소성
- 로그인 계정으로 대량 수집 (기본 40개, 게시물 사이 지연 유지. 제한이 걸리면 멈추고 알린다)
- 업로드 자동화 (자격 증명이 필요한 별도 작업. 요청이 있을 때만 별도 설계)
