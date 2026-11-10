# content-hub

로빈님 콘텐츠 자동화 허브. **소재 수집 → 선별 → 소재 1개를 플랫폼별로 생성 → 예약 발행 → 성과 보고·재활용**.
사용은 클로드에게 말하면 된다: "소재 모아줘", "이걸로 플랫폼별로 써줘", "내일 저녁 7시 반에 스레드 예약", "성과 봐줘", "이 영상 쇼츠로 잘라줘".
절차는 `../.claude/skills/content-hub/SKILL.md`. 마케팅 명령어 `/campaign-plan` `/draft-content` `/brand-review` `/performance-report` `/competitive-brief` 도 이 도구를 쓴다.

## 그림과 실제 파일

| 단계 | 하는 일 | 파일·명령 |
|---|---|---|
| Collector 소재 자동 수집 | 유튜브 자동완성(키 불필요), 유튜브 검색 상위(채널 평균 대비), 레퍼런스 인스타 반응 상위(경쟁사 스파이), 스레드 새 글 | `hub.py collect --suggest/--yt/--ig/--threads` |
| Picker 입력·선별 | 직접 작성/링크/파일, 사람 선별, AI 선별(클로드가 이유를 붙여 추천), 점수 자동 선별, 재활용 | `hub.py add`, `inbox`, `pick`, `review --remix` |
| Creator 브랜드 보이스 생성 | 페르소나 = `gongu-lab/guidelines.md`. 소재 → 플랫폼별 지시서 → 클로드(또는 MCP 로 연결한 ChatGPT·Gemini)가 작성 → 자동 검사 → 사람 검수 | `hub.py create`, `check`, 훅 `hooks/lint_on_write.py` |
| 카드뉴스·릴스·클리핑 | 캐러셀 문구 → 카드 이미지(JPEG), 롱폼 → 세로 1080x1920 클립(흐린 배경/가운데 자르기, 제목·자막) | `cards.py` / `hub.py cards`, `clip.py` |
| Scheduler 멀티 플랫폼 예약 | 예약 → 로빈님 승인 → 시각이 되면 자동 발행 또는 휴대폰 알림. 승인 뒤 글이 바뀌면 보류 | `hub.py queue add/approve/list/cancel`, `run`, `run_hub.ps1` |
| Reviewer 성과 | 스레드·인스타·페북 성과 자동 수집, 유튜브는 주소로 조회, 플랫폼 안 백분위, 보고서 md + CSV | `hub.py review` |
| MCP | 클로드 데스크톱·ChatGPT·Gemini 가 소재함·작성·예약을 쓰게 함 (승인·발행은 빠짐) | `mcp_server.py` |

## 플랫폼별로 실제 되는 것 (먼저 알아둘 것)

| 플랫폼 | 글 생성·검사 | 발행 | 성과 | 이유 |
|---|---|---|---|---|
| 스레드 | O | **자동** | **자동** | 공식 Threads API |
| 인스타 캐러셀·사진 | O + 카드 이미지 | **자동** (조건 있음) | **자동** | Graph API. 단 이미지가 **인터넷에서 열리는 JPEG 주소**여야 하고 토큰에 `instagram_content_publish` 권한 필요 |
| 페이스북 페이지 | O | **자동** | 자동 | 인스타와 연결된 페이지. 권한 `pages_manage_posts` |
| 인스타 릴스 | O | 알림 | 손으로 | 영상 업로드는 공개 영상 주소가 필요해 이 PC 구성으로는 안정적이지 않음 |
| 유튜브 롱폼·쇼츠 | O + 클립 | 알림 | 주소 남기면 자동 | 검수 안 된 API 프로젝트로 올린 영상은 **비공개로 잠김**(구글 정책). 스튜디오 예약 게시가 더 안전 |
| 유튜브 커뮤니티·고정댓글 | O | 알림 | - | 공식 API 없음 |
| 틱톡 | O | 알림 | - | 검수 전 앱은 비공개로만 올라감 |
| X | O (280 단위 검사) | 알림 | - | 글쓰기 API 가 유료 요금제 |
| 링크드인 | O | 알림 | - | 글쓰기 권한에 앱 승인 필요 |
| 인스타 자동 DM | DM 문구 생성(`dm`) | **ManyChat 같은 메타 공식 파트너 도구 권장** | - | 직접 만들려면 `instagram_manage_messages` 앱 검수 + 24시간 켜진 서버(웹후크)가 필요. 파트너 도구는 "댓글에 '정보' 달면 DM" 이 바로 됨 |

알림 = 시간이 되면 `hub.py run` 이 "지금 올릴 것: 파일 경로" 를 휴대폰(디스코드/슬랙)·윈도우 알림으로 보낸다. 올린 뒤 `hub.py done 예약ID --url 주소`.

## 처음 설정 (PC, 한 번만)

```powershell
cd $HOME\Documents\robyn-threads
git pull
pip install pillow mcp
```
1. **스레드 토큰**: [Meta for Developers](https://developers.facebook.com) 의 기존 앱(robynstable)에 **Threads API 사용 사례**를 추가하고 권한 `threads_basic`, `threads_content_publish`, `threads_manage_insights` 로 토큰을 만든다.
   `python content-hub\hub.py set-threads-token` → 토큰 붙여넣기(화면에 안 보이는 게 정상). Threads 앱 시크릿을 넣으면 60일 토큰으로 바꾸고, 30일마다 `run` 이 알아서 새로 고친다.
2. **인스타·페북 발행 권한**: Graph API Explorer 에서 기존 권한에 `instagram_content_publish`, `pages_manage_posts` 를 추가해 토큰을 다시 만들고 `python gongu-lab\ig_collect.py --set-token` 으로 저장. `--doctor` 로 확인.
3. **카드 이미지 주소**: 인스타 자동 발행은 이미지가 인터넷 주소여야 한다. 이 저장소는 공개라 오픈 전 이미지를 여기 올리면 안 된다.
   가장 쉬운 길: 카드는 손으로 올리고(알림만), 스레드·페북만 자동으로. 자동까지 원하면 비공개 이미지 저장소(예: Cloudflare R2 공개 버킷 주소)를 정해 `config.json` 의 `image_base_url` 에 넣는다.
4. **휴대폰 알림**: 디스코드 서버 → 채널 설정 → 연동 → 웹후크 → 주소 복사 → `python content-hub\hub.py set-webhook`.
5. **15분마다 자동 실행**: `run_hub.ps1` 맨 위 주석의 3줄을 PowerShell 에 붙여넣는다.
6. (선택) **다른 AI 연결(MCP)**: 클로드 데스크톱 `설정 → 개발자 → 설정 편집` 의 `claude_desktop_config.json` 에
   ```json
   {"mcpServers": {"robyn-content-hub": {"command": "python", "args": ["C:\\Users\\<사용자>\\Documents\\robyn-threads\\content-hub\\mcp_server.py"]}}}
   ```
   (`<사용자>` 는 PC 의 사용자 폴더 이름으로 바꾼다.) Gemini CLI 도 같은 형식으로 붙는다. ChatGPT 는 인터넷에서 열리는 HTTPS MCP 서버만 받기 때문에 PC 서버를 바로 붙일 수 없다(별도 호스팅 필요).

## 하루 흐름 예

```powershell
python content-hub\hub.py collect --suggest "김장 김치 보관" --ig
python content-hub\hub.py inbox                       # 클로드에게 "골라줘" 해도 됨
python content-hub\hub.py pick s20261110-002
python content-hub\hub.py create s20261110-002 --platforms threads,carousel,reels,shorts
#   → 클로드가 out\s20261110-002\ 에 글을 쓰고 자동 검사
python content-hub\hub.py cards s20261110-002
python content-hub\hub.py queue add s20261110-002 threads --at "2026-11-10 19:30"
python content-hub\hub.py queue approve q0001          # 승인은 로빈님이 직접
python content-hub\hub.py review --remix               # 일주일에 한 번
python content-hub\clip.py 원본.mp4 --cuts "03:10-03:52,12:05-12:50" --title "김장 김치가 위에서부터 시는 이유" --srt 원본.srt --out clips
```

## 안전장치
- **승인 문**: 예약은 승인해야 발행된다. 승인 뒤 파일을 고치면 자동으로 보류된다. 클로드·MCP 는 승인·발행을 하지 않는다(`.claude/settings.json` 의 ask 규칙, MCP 에서 제외).
- **자동 검사 훅**: 클로드가 `out/`·`gongu-lab/output/` 에 글을 저장할 때마다 금지어·플랫폼 규격을 검사하고 오류면 스스로 고친다.
- **키 보호**: 토큰·웹후크 주소는 화면에 안 보이게 입력해 로컬 파일에만 저장(`.gitignore`). 클로드가 그 파일을 읽지 못하게 `deny` 규칙.
- **중복 발행 방지**: 발행 직전 상태를 먼저 저장해, 도중에 꺼져도 같은 글을 두 번 올리지 않는다(다음 실행 때 확인 요청). 실패는 3번까지 다시 시도 후 알림.
- **공개 저장소**: `data/`(소재·예약·성과), `out/`(초안)은 커밋하지 않는다.

## 확인되지 않은 것
- 스레드·인스타·페북 실제 발행은 로빈님 토큰으로 처음 돌려 봐야 확인된다(여기서는 가짜 응답으로 흐름만 시험). 첫 발행은 시험 글 1개로.
- 메타 권한 이름·화면은 자주 바뀐다. 막히면 오류 메시지를 그대로 알려주면 된다.
