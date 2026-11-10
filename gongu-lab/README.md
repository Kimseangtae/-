# gongu-lab

로빈님 공동구매용 **레퍼런스 분석 → 일정 기반 자동 제작** 도구.

1. 인스타그램 레퍼런스 계정의 캐러셀을 슬라이드 이미지까지 모아 클로드가 직접 읽고, 반응이 좋은 구조와 나쁜 구조를 대조한다.
2. 공구 일정을 넣으면 일자별 제작 캘린더를 만들고, 그날 올릴 대본·설명글·고정댓글·쇼츠·릴스·캐러셀·스레드를 준비한다.
3. 로빈님 지침(금지 목록, 플랫폼 규격)을 `lint_content.py` 가 기계적으로 검사한다.

사용법은 클로드에게 말하면 된다: **"공구 레퍼런스 분석해줘"**, **"공구 일정 등록할게"**, **"오늘 올릴 것 알려줘"**.
절차는 `../.claude/skills/gongu-lab/SKILL.md`.

## 구성
| 파일 | 역할 |
|---|---|
| `references.json` | 레퍼런스 채널 목록 (instagram / youtube) |
| `ig_collect.py` | 인스타 수집: 공식 API → 로그인 브라우저 순으로 시도, 슬라이드 이미지 저장, 장수 검증 |
| `ig_analyze.py` | 캐러셀 반응 순위, 상위·하위 대기열, 분석 결과 검증, 패턴 통계, 슬라이드 모아보기 |
| `yt_research.py` | vidIQ 없이 유튜브 조사: 자동완성 검색어(키 불필요), 검색 상위 영상·채널 평균 대비 배수, 댓글, 채널 영상 |
| `analyze_videos.py` | 유튜브 영상 반응 분석 (`yt_research.py channel --save` 또는 vidIQ 결과 JSON 입력) |
| `schedule.json` | 공구 일정 (`schedule.example.json` 참고) |
| `playbook.json` | 공구 타임라인 틀. 레퍼런스 분석 후 갱신 |
| `plan_calendar.py` | 일정 → 캘린더, 오늘 할 일, 제작 지시서, 진행 현황 |
| `lint_content.py` | 금지어·자리표시자·플랫폼 규격 검사 |
| `guidelines.md` | 제작 지침 요약 (PC 의 클로드용) |
| `run_daily.sh` / `run_daily.ps1` | 매일 아침 자동 실행 |
| `data/ig/<핸들>/` | 수집 데이터. `posts.json`, `<코드>/analysis.json` 은 커밋, 이미지는 제외 |
| `analysis/` | 분석 보고서 |
| `output/<캠페인>/` | 생성한 콘텐츠 파일 |
| `calendar/` | 생성된 캘린더 |

## 인스타 수집 설정 (둘 중 하나, 둘 다 하면 서로 보완)

### 방법 1. 공식 Graph API (권장, 계정 위험 없음)
조건
- 로빈님 인스타가 **프로페셔널 계정**(크리에이터 가능)이고, **페이스북 페이지에 연결**돼 있어야 한다. 공식 문서상 크리에이터 계정은 페이지 연결이 있을 때 이 방식을 쓴다. 페이지 연결이 없으면 먼저 연결한다(인스타 앱 → 프로필 편집 → 페이지).
- 레퍼런스 계정도 프로페셔널(비즈니스/크리에이터) 계정이어야 한다. 개인 계정은 조회되지 않는다.

설정
1. [Meta for Developers](https://developers.facebook.com) 에서 앱 생성 (Instagram 사용 설정 포함, Facebook 로그인 방식).
2. [Graph API Explorer](https://developers.facebook.com/tools/explorer/) 에서 그 앱을 고르고 권한 `instagram_basic`, `instagram_manage_insights`, `pages_show_list`, `pages_read_engagement` 를 추가해 **사용자 액세스 토큰**을 만든다. 권한 목록은 [Business Discovery 문서](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/business_discovery) 기준이며 바뀔 수 있다.
3. 짧은 토큰은 1시간 정도면 끝난다. 앱 설정의 앱 ID·앱 시크릿으로 **장기 토큰**으로 교환한다(Meta 의 `fb_exchange_token` 방식, 약 60일).
4. 토큰 저장 (한 번만): `python gongu-lab/ig_collect.py --set-token` → 토큰을 붙여넣는다(화면에 안 보이는 게 정상).
   앱 ID·앱 시크릿 코드(앱 설정 → 기본 설정)를 넣으면 **60일짜리 장기 토큰**으로 바꿔 저장한다. 시크릿은 저장하지 않는다.
   토큰은 `gongu-lab/.ig_token.json` 에만 저장되고 `.gitignore` 로 저장소에 올라가지 않는다. 창을 닫아도 다시 넣을 필요 없다. 내 인스타 계정 ID 도 자동으로 찾는다.
5. **점검**: `python gongu-lab/ig_collect.py --doctor` — 토큰, 권한, 계정 연결, 레퍼런스 조회 가능 여부를 차례로 보고 **다음에 할 일 1개**를 알려준다. 빠진 권한 이름과 앱 대시보드 링크까지 짚어준다.
6. **시험**: `python gongu-lab/ig_collect.py --check 레퍼런스핸들1 레퍼런스핸들2` — 슬라이드 이미지까지 오는지 계정별로 판정한다.
7. 수집: `python3 gongu-lab/ig_collect.py --all` — 공식 API 가 막힌 계정은 **자동으로 로그인 브라우저 방식으로 전환**한다(방법 2 준비 필요).

앱이 개발 모드인 상태에서 앱 관리자 본인 계정으로 쓰는 것은 보통 앱 검수 없이 되지만, 막히면 오류 메시지를 알려주면 원인을 같이 본다.
**확인되지 않은 점**: 이 경로로 슬라이드(`children`)를 받을 수 있는지는 공식 문서에 없다. 6번 시험이 그 답이다. 수집기는 필드를 줄여가며 자동 재시도하고 어디까지 받았는지를 `posts.json` 의 `source_level` 에 남긴다.

### 방법 2. 로그인 브라우저 (공식 API 가 못 채우는 슬라이드 보충, 비즈니스 계정이 아닌 경우)
```bash
pip install playwright pillow
python3 -m playwright install chromium
python3 gongu-lab/ig_collect.py --login        # 창에서 인스타 로그인 후 터미널에서 Enter
python3 gongu-lab/ig_collect.py 핸들 --show --max-posts 10   # 처음엔 10개만, 창을 보면서 시험
```
로그인 정보는 `gongu-lab/.browser-profile/` 에만 저장되고 git 에는 올라가지 않는다.
**주의**: 인스타는 자동화된 열람에 제한을 걸 수 있다. 로빈님 본 계정 대신 **분석 전용 보조 계정**을 쓰는 것을 권한다.
수집기는 게시물 사이 4~9초를 두고 기본 40개까지만 읽는다. 처음 한 번은 반드시 `--show --max-posts 10` 으로 시험한다.
인스타 화면 구조는 자주 바뀌어, 이 경로는 실제 계정으로 돌려 보기 전에는 작동을 보증할 수 없다. 막히면 `--debug --show` 로 응답을 저장해 알려주면 고친다.

## 유튜브 조사 키 (무료, 한 번만)
`yt_research.py` 의 `search`·`comments`·`channel` 은 YouTube Data API 키가 필요하다(`suggest` 는 키 없이 된다).
1. [Google Cloud 콘솔](https://console.cloud.google.com/)에서 프로젝트를 만들고 **YouTube Data API v3** 를 사용 설정한다.
2. **사용자 인증 정보 → API 키 만들기**. 키 제한에서 YouTube Data API v3 만 허용해 두면 안전하다.
3. PC: `python gongu-lab\yt_research.py set-key` 로 저장(화면에 안 보임, 커밋 제외).
   클라우드 세션: 환경 설정의 환경변수에 `YOUTUBE_API_KEY` 로 넣는다. 키를 채팅에 붙여넣지 않는다.
무료 할당량은 하루 10,000 단위(검색 1회 100, 나머지 1).

## 매일 쓰기
- 수동: 저장소 폴더에서 `claude` → "오늘 올릴 것 알려줘"
- 자동: `run_daily.sh`(맥) / `run_daily.ps1`(윈도우)를 매일 아침 예약. 설정 방법은 `../threads-watch/README.md` 의 예약 등록과 같고 파일 이름만 바꾼다.
  윈도우 작업 스케줄러 인수: `-ExecutionPolicy Bypass -File "C:\...\gongu-lab\run_daily.ps1"`

## 저장소 공개 여부 (중요)
이 저장소는 **공개(public)** 라서 `schedule.json`(일정·가격·단점), `output/`(오픈 전 초안), `calendar/`, `state/` 는 `.gitignore` 로 커밋에서 제외했다.
그래서 이 파일들은 **그 PC 안에만** 있고 휴대폰·다른 PC 로 동기화되지 않는다. 동기화가 필요하면 저장소를 **비공개(private)로 바꾼 뒤**
`.gitignore` 아래쪽 "공개 저장소 보호" 블록을 지운다. 공개 상태에서는 마진·수익 구조·미공개 가격을 어떤 파일에도 쓰지 않는다.

## 한계 (먼저 알아둘 것)
- **업로드는 하지 않는다.** 파일을 준비하고 알려줄 뿐, 올리는 건 로빈님이 한다.
- 캐러셀의 반응 지표는 **좋아요·댓글뿐**이다. 저장·공유·도달은 외부에서 보이지 않아, 캐러셀에서 가장 중요한 저장 수를 알 수 없다. 좋아요를 숨긴 게시물은 댓글만으로 점수를 낸다.
- 이미지 속 글자는 클로드가 직접 읽는다. 작은 글씨나 저대비는 오독 가능성이 있어 `[판독불가]` 표시 규칙과 `validate` 장수 검증을 둔다. 영상 슬라이드는 첫 프레임만 본다.
- 공구 여부는 캡션·링크 안내 같은 정황 판단이다. 확정은 로빈님이 한다.
- 표본이 12개 미만이면 결과는 결론이 아닌 가설이다. 통계표는 항목을 따로 본 것이라 원인을 가르지 못한다.
- 수집한 타인의 이미지는 분석용이며 `.gitignore` 로 저장소에서 제외했다. 콘텐츠에 그대로 쓰지 않는다.
