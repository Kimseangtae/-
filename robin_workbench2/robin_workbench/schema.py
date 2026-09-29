# -*- coding: utf-8 -*-
"""입력 양식 정의. 각 칸의 성격(원문·셰프 확인·자동 추정), 형식, 예시, 작성 안내."""
from __future__ import annotations

from dataclasses import dataclass, field

# 칸의 성격. 화면과 CSV에 그대로 표시한다.
ORIGIN_RAW = "원문"          # 외부에서 받은 그대로 (댓글, 질문 원문, 플랫폼 지표)
ORIGIN_CHEF = "셰프 확인"    # 로빈님이 직접 확인·판단한 사실
ORIGIN_INPUT = "입력"        # 일반 기록 (ID, 날짜, 메모 등)
ORIGIN_AUTO = "자동 추정"    # 규칙 기반 계산 결과. 사실로 쓰지 않는다.

PAIN_CATEGORIES = ["요리 실패", "조리 시간", "번거로움", "재료 비용", "건강 관심",
                   "제품 구매 망설임", "기타·사람 확인 필요"]
CRITERIA = [
    "시청자 불편과 연결되는가",
    "조리 전후 변화가 화면에 보이는가",
    "셰프로서 설명할 만한 조리 원리가 있는가",
    "재료를 구하기 쉬운가",
    "상품의 장점을 실제 조리로 확인할 수 있는가",
    "상품을 빼도 영상 자체가 볼 만한가",
]


@dataclass
class Field:
    key: str
    kind: str = "text"            # text, long, choice, int, float, date, datetime, score
    required: bool = False
    origin: str = ORIGIN_INPUT
    choices: list[str] = field(default_factory=list)
    help: str = ""
    example: str = ""
    in_list: bool = False          # 목록 화면에 보이는 칸


@dataclass
class Table:
    key: str
    title: str
    id_field: str
    id_prefix: str
    help: str
    fields: list[Field]
    dedupe: list[str] = field(default_factory=list)   # 중복 판정에 쓰는 칸
    aliases: dict[str, str] = field(default_factory=dict)  # 다른 CSV 제목 → 이 양식 칸

    def field(self, key: str) -> Field:
        for f in self.fields:
            if f.key == key:
                return f
        raise KeyError(key)

    @property
    def keys(self) -> list[str]:
        return [f.key for f in self.fields]


YES_NO = ["예", "아니오"]

TABLES: dict[str, Table] = {}


def _t(t: Table) -> Table:
    TABLES[t.key] = t
    return t


_t(Table("comments", "① 시청자 댓글·질문", "댓글ID", "C",
         "댓글은 원문 그대로 붙여 넣습니다. 작성자 이름·연락처는 넣지 않습니다. "
         "분류는 자동 분류(추정)를 보고 로빈님이 확정합니다.",
         [Field("댓글ID", in_list=True, help="비우면 자동으로 붙습니다."),
          Field("날짜", "date", help="댓글이 달린 날", example="2026-09-20", in_list=True),
          Field("플랫폼", "choice", choices=["유튜브", "인스타그램", "스레드", "네이버카페", "블로그", "기타"],
                in_list=True, example="유튜브"),
          Field("출처영상", help="어느 영상·게시물의 댓글인지", example="두부조림 영상"),
          Field("댓글원문", "long", required=True, origin=ORIGIN_RAW, in_list=True,
                help="고치지 말고 그대로. 개인정보는 지웁니다.", example="냄비 바닥에 자꾸 눌어붙어요ㅠ"),
          Field("URL또는댓글ID", origin=ORIGIN_RAW, help="다시 찾아갈 수 있는 주소나 댓글 번호",
                example="https://youtu.be/xxxx?lc=yyyy"),
          Field("해결하고싶은문제", "long", origin=ORIGIN_CHEF,
                help="댓글에서 읽히는 문제를 로빈님 말로. 댓글에 없는 내용은 쓰지 않습니다.",
                example="찜할 때 바닥이 타지 않게 하고 싶다"),
          Field("분류", "choice", origin=ORIGIN_CHEF, choices=PAIN_CATEGORIES, in_list=True,
                help="로빈님이 확정한 분류. 비우면 자동 분류(추정)를 참고용으로만 씁니다."),
          Field("검토상태", "choice", choices=["미검토", "검토완료", "제외"], in_list=True, example="미검토")],
         dedupe=["댓글원문", "URL또는댓글ID"],
         aliases={"댓글": "댓글원문", "원문": "댓글원문", "내용": "댓글원문", "URL": "URL또는댓글ID",
                  "링크": "URL또는댓글ID", "영상": "출처영상", "상태": "검토상태", "문제": "해결하고싶은문제"}))

_t(Table("videos", "② 영상 성과", "기록ID", "V",
         "플랫폼 화면에서 본 숫자를 그대로 적습니다. 모르는 칸은 비워 둡니다(0으로 쓰지 않기). "
         "비교는 같은 플랫폼·같은 경과시간끼리만 합니다.",
         [Field("기록ID", in_list=True),
          Field("플랫폼", "choice", required=True, choices=["유튜브", "유튜브 쇼츠", "인스타그램", "스레드", "기타"],
                in_list=True, example="유튜브"),
          Field("영상ID", required=True, in_list=True, example="abc123XYZ"),
          Field("게시일", "date", example="2026-09-20"),
          Field("메뉴", in_list=True, example="소고기 무국"),
          Field("제목", example="무국이 탁해지는 이유"),
          Field("썸네일문구", example="무국, 왜 탁할까?"),
          Field("지표확인시각", "datetime", required=True, help="숫자를 본 시각", example="2026-09-22 09:00"),
          Field("게시후경과시간", "int", required=True, in_list=True,
                help="시간 단위. 24, 72, 168(7일)처럼 같은 기준으로 맞춥니다.", example="72"),
          Field("조회수", "int", origin=ORIGIN_RAW, in_list=True, example="12000"),
          Field("클릭률", "float", origin=ORIGIN_RAW, help="% 숫자만", example="6.2"),
          Field("평균시청시간", "int", origin=ORIGIN_RAW, help="초 단위", example="245"),
          Field("시청유지메모", "long", origin=ORIGIN_CHEF, example="도입 30초 이탈 큼"),
          Field("저장수", "int", origin=ORIGIN_RAW),
          Field("공유수", "int", origin=ORIGIN_RAW),
          Field("기타지표", "long", origin=ORIGIN_RAW, help="플랫폼에서 확보한 다른 숫자와 이름")],
         dedupe=["플랫폼", "영상ID", "지표확인시각"],
         aliases={"조회": "조회수", "CTR": "클릭률", "평균시청": "평균시청시간", "경과시간": "게시후경과시간"}))

_t(Table("tests", "③ 조리 테스트", "테스트ID", "T",
         "직접 조리한 기록만 적습니다. 콘텐츠 초안은 '셰프확인=예'인 기록만 원본으로 씁니다. "
         "재료량·불 세기·시간은 적은 그대로만 초안에 들어갑니다.",
         [Field("테스트ID", in_list=True),
          Field("날짜", "date", example="2026-09-25", in_list=True),
          Field("메뉴", required=True, in_list=True, example="소고기 무국"),
          Field("사용상품ID", help="④ 상품 정보의 상품ID. 여러 개면 쉼표", example="P-0001"),
          Field("재료와양", "long", origin=ORIGIN_CHEF, help="한 줄에 하나", example="소고기 양지 300g\n무 1/3개"),
          Field("조리순서", "long", origin=ORIGIN_CHEF, help="한 줄에 한 동작", example="양지를 참기름에 볶는다"),
          Field("불세기", origin=ORIGIN_CHEF, example="중불 → 약불"),
          Field("조리시간", origin=ORIGIN_CHEF, example="총 25분"),
          Field("실패와수정", "long", origin=ORIGIN_CHEF, help="한 줄에 '실패 → 수정'",
                example="국물이 탁했다 → 핏물을 먼저 뺐다"),
          Field("맛평가", "long", origin=ORIGIN_CHEF),
          Field("촬영장면", "long", origin=ORIGIN_CHEF, help="한 줄에 한 장면"),
          Field("셰프확인", "choice", choices=YES_NO, origin=ORIGIN_CHEF, in_list=True,
                help="직접 조리·확인한 기록이면 '예'")],
         dedupe=["테스트ID"]))

_t(Table("products", "④ 상품 정보", "상품ID", "P",
         "공식 자료로 확인한 기능과, 판매처가 주장하지만 확인 안 된 내용을 나눠 적습니다. "
         "확인된 기능만 FAQ 답변 근거로 씁니다.",
         [Field("상품ID", in_list=True),
          Field("상품명", required=True, in_list=True, example="알텐바흐 저압냄비"),
          Field("정확한모델", in_list=True, help="모델명·용량까지", example="확인 필요"),
          Field("공식자료출처", origin=ORIGIN_CHEF, help="공식 상세페이지·설명서 주소나 이름"),
          Field("확인날짜", "date", origin=ORIGIN_CHEF),
          Field("확인된기능", "long", origin=ORIGIN_CHEF, help="공식 자료에서 확인한 것만, 한 줄에 하나"),
          Field("가격", origin=ORIGIN_CHEF, help="확인한 가격과 기준(정가/공구가)"),
          Field("공구조건", "long", origin=ORIGIN_CHEF),
          Field("직접사용경험", "long", origin=ORIGIN_CHEF, help="로빈님이 직접 써 보고 확인한 것"),
          Field("확인되지않은주장", "long", origin=ORIGIN_RAW, help="판매처·제조사 문구 중 아직 확인 못 한 것")],
         dedupe=["상품명", "정확한모델"]))

_t(Table("inquiries", "⑤-1 공동구매 문의", "문의ID", "Q",
         "고객 질문은 원문으로, 이름·연락처는 빼고 적습니다. 답변마다 근거를 적어야 FAQ에 '근거 있음'으로 들어갑니다.",
         [Field("문의ID", in_list=True),
          Field("날짜", "date", in_list=True),
          Field("상품ID", in_list=True),
          Field("질문원문", "long", required=True, origin=ORIGIN_RAW, in_list=True, example="인덕션에서도 되나요?"),
          Field("답변", "long", origin=ORIGIN_CHEF),
          Field("답변근거", "long", origin=ORIGIN_CHEF, help="공식 자료 쪽수, 직접 확인 등"),
          Field("구매영향", "choice", choices=["구매를 이끔", "구매를 막음", "모름"], origin=ORIGIN_CHEF, in_list=True),
          Field("운영메모", "long")],
         dedupe=["질문원문", "날짜", "상품ID"]))

_t(Table("results", "⑤-2 공동구매 결과", "결과ID", "S",
         "판매 수치는 지표 종류와 집계 기준을 꼭 적습니다. 선예약은 주문·매출에 더하지 않습니다.",
         [Field("결과ID", in_list=True),
          Field("상품ID", required=True, in_list=True),
          Field("기간", required=True, in_list=True, example="2026-10-05~2026-10-09"),
          Field("지표종류", "choice", required=True, in_list=True,
                choices=["방문", "선예약", "주문", "매출", "반품", "불만", "기타"]),
          Field("값", "float", origin=ORIGIN_RAW, in_list=True, help="비우면 '미확보'. 0은 실제로 0일 때만"),
          Field("집계기준", required=True, help="어디서 어떻게 센 숫자인지", example="스마트스토어 주문 확정 기준"),
          Field("사유메모", "long", help="반품·불만이면 사유")],
         dedupe=["상품ID", "기간", "지표종류", "집계기준"]))

_t(Table("menus", "⑥ 메뉴 후보와 평가", "메뉴ID", "M",
         "자동 평가(추정)와 셰프 평가는 따로 저장됩니다. 근거가 부족하면 '보류'로 둡니다. 최종 선택은 로빈님이 합니다.",
         [Field("메뉴ID", in_list=True),
          Field("메뉴명", required=True, in_list=True, example="소고기 무국"),
          Field("요리권역", "choice", choices=["한식", "일식", "지중해식", "기타"], in_list=True),
          Field("관련불편", "choice", choices=PAIN_CATEGORIES, help="이 메뉴가 해결하려는 시청자 불편"),
          Field("관련상품ID"),
          Field("관련테스트ID", help="③ 조리 테스트 ID, 여러 개면 쉼표"),
          Field("설명", "long", help="메뉴 아이디어·화면에 보일 변화·조리 원리"),
          Field("색", help="테마 추천용: 청·적·황·백·흑 중 쉼표로", example="백,적"),
          Field("맛", help="테마 추천용: 신맛·쓴맛·단맛·매운맛·짠맛", example="짠맛"),
          Field("스타일태그", help="테마 추천용: 국물, 찜, 한그릇, 1인분 등", example="국물,추억음식")]
         + [f for i in range(1, 7) for f in (
             Field(f"셰프점수{i}", "score", origin=ORIGIN_CHEF, help=f"{i}) {CRITERIA[i-1]} — 1~5, 비우면 미평가"),
             Field(f"셰프이유{i}", "long", origin=ORIGIN_CHEF))]
         + [Field("셰프결정", "choice", choices=["미정", "선택", "보류", "제외"], origin=ORIGIN_CHEF, in_list=True)],
         dedupe=["메뉴명"]))

_t(Table("retros", "⑦ 콘텐츠·공구 회고", "회고ID", "R",
         "다음 메뉴를 기획할 때 검색해서 참고합니다. 짧게, 한 가지씩.",
         [Field("회고ID", in_list=True),
          Field("종류", "choice", required=True, choices=["영상", "공구"], in_list=True),
          Field("대상", required=True, help="영상ID 또는 상품ID", in_list=True),
          Field("메뉴", in_list=True),
          Field("회고일", "date"),
          Field("해결하려던문제", "long", origin=ORIGIN_CHEF),
          Field("실제성과", "long", origin=ORIGIN_CHEF, help="같은 경과시간 기준으로 적습니다"),
          Field("시청자반응", "long", origin=ORIGIN_CHEF),
          Field("다음에바꿀한가지", "long", origin=ORIGIN_CHEF),
          Field("구매를이끈질문", "long", origin=ORIGIN_CHEF),
          Field("구매를막은질문", "long", origin=ORIGIN_CHEF),
          Field("불만반품사유", "long", origin=ORIGIN_CHEF),
          Field("다음개선점", "long", origin=ORIGIN_CHEF)],
         dedupe=["종류", "대상", "회고일"]))

FLOW = [("자료 입력", ["comments", "videos", "products", "inquiries", "results"]),
        ("불편 분석", ["comments"]),
        ("메뉴 후보", ["menus"]),
        ("조리 기록", ["tests"]),
        ("콘텐츠 초안", ["tests"]),
        ("성과 회고", ["retros", "videos", "results"])]
