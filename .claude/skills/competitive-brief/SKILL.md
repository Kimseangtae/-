---
name: competitive-brief
description: >
  경쟁 채널·레퍼런스 계정과 비교해 로빈의밥상이 내세울 차별점을 정리한다. gongu-lab 레퍼런스 인스타 분석, 유튜브 검색 상위 영상,
  같은 제품을 판 다른 공구를 보고 "그들이 안 하는 것"을 찾는다. "/competitive-brief", "경쟁 분석", "차별점 정리" 요청 시.
---

# /competitive-brief — 경쟁과 비교한 차별점

## 순서
1. 범위: 인자로 받은 주제·제품(예: "김치통", "테팔 에퍼샤프 프로") 또는 경쟁 핸들.
2. 자료 (있는 것부터, 지어내지 않는다)
   - 인스타 레퍼런스: `python gongu-lab/ig_analyze.py rank <핸들>` 과 `data/ig/<핸들>/*/analysis.json`, 최신 `gongu-lab/analysis/*.md`
   - 유튜브: `python gongu-lab/yt_research.py search "<주제>" --format long --json content-hub/data/yt_<주제>.json`
     → 채널 평균 대비 2배 이상 영상의 제목·구조, `comments <영상> --grep "불편|단점|비싸|냄새"` 로 시청자 불만
   - 막힌 사이트는 우회하지 않고 로빈님께 캡처를 받는다.
3. 정리 표: | 경쟁 | 소구점(난이도 해소/속도 향상/선택 대행) | 훅·구조 | 말 안 하는 것(단점·한계) | 시청자 불만 |
4. 로빈의밥상 차별점 3개 — 각각 (근거 / 콘텐츠로 보여 줄 장면 / 쓸 플랫폼). 기본 축:
   - 단점을 먼저 공개하는 "속지 않는 부엌"
   - 20년 셰프가 레시피가 아니라 '왜'를 설명
   - 55~70대 부엌의 실제 장면(무게·손목·보관 공간)
5. 바로 쓸 소재 3개를 `python content-hub/hub.py add --text … --tags 경쟁` 으로 넣을지 묻는다.

## 하지 않는 것
- 경쟁 콘텐츠의 문장·이미지 복사, 경쟁사 비방, 확인 안 된 수치 비교.
