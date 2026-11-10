---
name: content-hub
description: >
  로빈의밥상 콘텐츠 허브: 소재 수집 → 선별 → 소재 1개를 플랫폼별 글·카드뉴스·쇼츠 클립으로 → 예약 발행(스레드·인스타·페북 자동, 나머지 알림)
  → 성과 보고·재활용. "소재 모아줘", "소재함", "이걸로 플랫폼별로", "예약해줘", "오늘 올릴 것", "성과 봐줘", "쇼츠 잘라줘", "content hub" 요청 시.
---

# content-hub 운영 절차

도구: `content-hub/hub.py` (CLI), `cards.py`(카드뉴스), `clip.py`(롱폼→쇼츠), `mcp_server.py`(다른 AI 연결). 경로는 저장소 루트 기준.
글쓰기 규칙은 `gongu-lab/guidelines.md`. 공구 일정 기반 제작은 gongu-lab 스킬이 맡고, 여기는 공구 밖의 일상 콘텐츠와 발행·성과를 맡는다.

## 1. 수집 (Collector)
```bash
python content-hub/hub.py collect --suggest "김장 김치 보관"      # 사람들이 실제로 치는 검색어 (키 불필요)
python content-hub/hub.py collect --ig                           # 레퍼런스 인스타 반응 상위 (gongu-lab 수집 데이터)
python content-hub/hub.py collect --yt content-hub/data/yt.json  # yt_research.py search … --json 결과
python content-hub/hub.py collect --threads                      # 스레드 채널 새 글
python content-hub/hub.py add --text "…" | --url … | --file …    # 직접
```
## 2. 선별 (Picker)
`hub.py inbox` 를 보고 로빈님께 상위 3~5개를 **이유 한 줄씩** 붙여 추천한다(검색 수요·계절·공구 연결·채널 철학 적합도).
로빈님이 고르면 `hub.py pick ID…`. "알아서 골라" 면 내가 이유를 적고 고른다. `--auto N` 은 점수만 보는 기계 선별이라 보조로만.
레퍼런스 소재(ig_ref·threads)는 구조만 빌린다.

## 3. 생성 (Creator) — /draft-content 와 같음
`hub.py create ID --platforms …` → `out/<ID>/brief.md` 대로 파일 작성 → 훅이 자동 검사 → `hub.py check ID` 오류 0건.
캐러셀은 `hub.py cards ID` (JPEG). 롱폼 → 쇼츠는 대본·자막을 읽고 구간을 골라 `python content-hub/clip.py 영상 --cuts … --title … --srt …`.
큰 건(공구 오픈·키 콘텐츠)은 /brand-review 로 독립 검수 한 번 더.

## 4. 예약·발행 (Scheduler)
`hub.py queue add ID 플랫폼 --at "YYYY-MM-DD HH:MM"` → **승인은 로빈님이 직접** `hub.py queue approve QID` (내가 승인하지 않는다).
PC 의 예약 작업이 `run_hub.ps1` 로 15분마다 `hub.py run` 실행: 스레드·인스타(이미지 주소 있을 때)·페북은 자동, 나머지는 휴대폰 알림.
손으로 올린 뒤 `hub.py done QID --url 주소` → 성과 수집 대상.

## 5. 성과 (Reviewer) — /performance-report
`hub.py review --days 14 [--remix]` → `data/reports/review_날짜.md` + CSV. 상위 소재는 remix 로 소재함에 되돌아온다.

## 지킬 것
- 사실(가격·수량·마감·효능)은 지어내지 않는다. 토큰·키·웹후크 주소를 채팅으로 받지 않는다(`set-threads-token`, `set-webhook`, `ig_collect.py --set-token`).
- `content-hub/data/`, `out/` 은 커밋하지 않는다(공개 저장소). 업로드 자동화가 없는 플랫폼은 알림까지만.
