---
name: draft-content
description: >
  소재 1개를 로빈의밥상 채널별 글(스레드·인스타 캐러셀·릴스·쇼츠·커뮤니티·틱톡·X·페이스북·링크드인·DM·롱폼 설명글)로 한 번에 쓴다.
  content-hub 의 지시서·검사를 거쳐 바로 붙여넣을 완성본을 만든다. "/draft-content", "채널별로 써줘", "이 소재로 글 써줘" 요청 시.
---

# /draft-content — 소재 1개 → 채널별 완성본

## 순서
1. 소재 정하기: 인자가 소재 ID(`s2026…`)면 그대로. 문장·링크면 `python content-hub/hub.py add --text "…"`(또는 `--url`)로 넣고 ID 를 받는다.
2. 플랫폼: 인자에 없으면 config 의 기본(threads,carousel,reels,shorts,community). 공구 글이면 로빈님께 공구인지 먼저 확인(CTA 구조가 다름).
3. `python content-hub/hub.py create <ID> --platforms …` → `content-hub/out/<ID>/brief.md` 를 읽는다.
4. 반드시 먼저 읽기: `gongu-lab/guidelines.md`, 지시서의 read_first.
5. 플랫폼마다 파일을 쓴다. 같은 내용이라도 호칭·어미를 다시 쓴다
   (유튜브 '밥상 식구님들' 존댓말 / 스레드 '스친이들' 반말 / 인스타 존댓말+프로필 링크 / 틱톡 '프로필 링크를 눌러 확인해줘').
   파일을 저장하면 훅이 자동으로 지침 검사를 돌린다. 오류가 돌아오면 고쳐서 다시 저장.
6. `python content-hub/hub.py check <ID>` 오류 0건 확인.
7. 캐러셀이면 `python content-hub/hub.py cards <ID>` 로 카드 이미지까지.
8. 대화에는 플랫폼별 완성본을 그대로 붙이고, 끝에 대안·개선점을 짧게. 예약은 로빈님이 시간을 말하면 `hub.py queue add`.

## 지킬 것
- 가격·수량·마감·효능은 소재·schedule.json 에 있는 것만. 없으면 쓰기 전에 묻는다.
- 레퍼런스 소재(ig_ref·threads·yt)는 구조만 빌린다.
