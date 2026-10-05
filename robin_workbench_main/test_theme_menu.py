# -*- coding: utf-8 -*-
import datetime as dt
import tempfile
import unittest
from pathlib import Path

import theme_menu as tm
from seed import initialize
from core import Store, UserError, theme_report

HERE = Path(__file__).parent
EXAMPLE = HERE / "예시_테마메뉴후보.csv"


def write(text: str, enc: str = "utf-8") -> Path:
    d = Path(tempfile.mkdtemp())
    p = d / "m.csv"
    p.write_bytes(text.encode(enc))
    return p


class Calendar(unittest.TestCase):
    def test_day_pillar_anchors(self):
        self.assertTrue(tm.day_pillar(dt.date(2000, 1, 1))[1].startswith("무오"))
        self.assertTrue(tm.day_pillar(dt.date(1900, 1, 1))[1].startswith("갑술"))
        self.assertEqual(tm.day_pillar(dt.date(2000, 1, 1))[2], "토")

    def test_year_and_ipchun(self):
        self.assertEqual(tm.year_info(dt.date(1968, 6, 1)).animal, "원숭이")
        self.assertTrue(tm.year_info(dt.date(1968, 6, 1)).pillar.startswith("무신"))
        jan = tm.year_info(dt.date(1968, 1, 20))
        self.assertEqual((jan.saju_year, jan.animal), (1967, "양"))
        self.assertIn("확인 필요", tm.year_info(dt.date(1968, 2, 4)).boundary_note)

    def test_zodiac_boundaries(self):
        cases = {(1, 19): "염소자리", (1, 20): "물병자리", (3, 20): "물고기자리", (3, 21): "양자리",
                 (12, 21): "사수자리", (12, 22): "염소자리", (8, 23): "처녀자리"}
        for (m, d), name in cases.items():
            self.assertEqual(tm.zodiac_sign(dt.date(1970, m, d))[0], name, (m, d))

    def test_mbti(self):
        self.assertEqual(tm.parse_mbti(" isfj "), "ISFJ")
        for bad in ("", "ISF", "XSFJ", "ISFJX"):
            with self.assertRaises(ValueError):
                tm.parse_mbti(bad)


class Loading(unittest.TestCase):
    def test_example_loads(self):
        menus = tm.load_menus(EXAMPLE)
        self.assertEqual(len(menus), 9)
        self.assertEqual({m.data_kind for m in menus}, {"예시"})

    def test_missing_file(self):
        with self.assertRaises(tm.InputError):
            tm.load_menus(Path("/없는/경로.csv"))

    def test_missing_column(self):
        with self.assertRaises(tm.InputError):
            tm.load_menus(write("메뉴ID,메뉴명\nA,B\n"))

    def test_duplicate_id(self):
        with self.assertRaises(tm.InputError):
            tm.load_menus(write("메뉴ID,메뉴명,데이터구분\nA,국,실제\nA,찜,실제\n"))

    def test_mixed_kinds_refused(self):
        with self.assertRaises(tm.InputError):
            tm.load_menus(write("메뉴ID,메뉴명,데이터구분\nA,국,실제\nB,찜,예시\n"))

    def test_bad_kind(self):
        with self.assertRaises(tm.InputError):
            tm.load_menus(write("메뉴ID,메뉴명,데이터구분\nA,국,진짜\n"))

    def test_cp949_excel_file(self):
        menus = tm.load_menus(write("메뉴ID,메뉴명,데이터구분,색\nA,무국,실제,백\n", "cp949"))
        self.assertEqual(menus[0].name, "무국")


class Ranking(unittest.TestCase):
    def setUp(self):
        self.menus = tm.load_menus(EXAMPLE)

    def test_blank_tags_are_on_hold_not_zero(self):
        picks = tm.by_mbti(self.menus, "ISFJ")
        held = [p for p in picks if p.menu.menu_id == "EX-M09"][0]
        self.assertTrue(held.on_hold)
        self.assertEqual(picks[-1].menu.menu_id, "EX-M09")

    def test_mbti_reasons_are_traceable(self):
        top = tm.by_mbti(self.menus, "ISFJ")[0]
        self.assertGreater(top.score, 0)
        self.assertTrue(all("—" in r for r in top.reasons))

    def test_element_uses_color_and_taste(self):
        top = tm.by_element(self.menus, "수", "테스트")[0]
        self.assertEqual(top.menu.menu_id, "EX-M04")  # 흑·짠맛


class Report(unittest.TestCase):
    def test_report_rules(self):
        menus = tm.load_menus(EXAMPLE)
        r = tm.build_report(menus, dt.date(1968, 3, 15), "ISFJ", dt.date(2026, 10, 5))
        for must in ("규칙 기반", "재미·기획용", "예시 데이터", "셰프 확인 칸", "평가 보류", "여러분"):
            self.assertIn(must, r)
        for banned in ("밥깡패", "매실", "체칼", "AI 분석"):
            self.assertNotIn(banned, r)

    def test_cli_writes_file_and_reports_errors(self):
        out = Path(tempfile.mkdtemp())
        self.assertEqual(tm.main(["--menus", str(EXAMPLE), "--birth", "1968-03-15", "--mbti", "enfp",
                                  "--day", "2026-10-05", "--out", str(out)]), 0)
        files = list(out.glob("테마밥상_예시_*.md"))
        self.assertEqual(len(files), 1)
        self.assertEqual(tm.main(["--menus", str(EXAMPLE), "--birth", "68-3-15", "--out", str(out)]), 2)
        self.assertEqual(tm.main(["--menus", str(EXAMPLE), "--mbti", "ABCD", "--out", str(out)]), 2)


class Integration(unittest.TestCase):
    """본부 작업실의 메뉴후보 표와 연결."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name); initialize(self.root)
        self.out = self.root / 'out'; self.s = Store(self.root, out_root=self.out)

    def tearDown(self):
        self.temp.cleanup()

    def test_example_report_has_hold_and_viewer_greeting(self):
        r = theme_report(self.s, dt.date(1966, 9, 10), "ISFJ", dt.date(2026, 10, 5))
        for must in ("규칙 기반", "재미·기획용", "예시 데이터", "평가 보류", "밥상 식구님들"):
            self.assertIn(must, r)
        self.assertIn("평가 보류(태그 없음): M006", r)  # 태그 없는 채소 스튜는 0점이 아니라 보류
        for banned in ("밥깡패", "매실", "체칼"):
            self.assertNotIn(banned, r)

    def test_no_menus_or_bad_mbti_have_fix(self):
        empty = Store(self.root, 'actual', self.out)
        with self.assertRaises(UserError) as e:
            theme_report(empty)
        self.assertIn("해결 방법", str(e.exception))
        with self.assertRaises(UserError) as e:
            theme_report(self.s, mbti="ABCD")
        self.assertIn("해결 방법", str(e.exception))

    def test_chef_choice_is_not_auto_set(self):
        before = [r['최종판단'] for r in self.s.read('메뉴후보')]
        theme_report(self.s, dt.date(1966, 9, 10), "ENFP", dt.date(2026, 10, 5))
        self.assertEqual(before, [r['최종판단'] for r in self.s.read('메뉴후보')])

    def test_old_menu_file_gets_new_columns(self):
        old = self.root / 'data' / 'actual' / '메뉴후보.csv'
        old.write_text('id,구분,원문,메뉴,요리권\nM1,실제,국이 필요해요,무국,한식\n', encoding='utf-8')
        s = Store(self.root, 'actual', self.out); r = s.read('메뉴후보')[0]
        self.assertEqual((r['메뉴'], r['색'], r['맛'], r['스타일태그']), ('무국', '', '', ''))
        self.assertIn('메뉴후보', s.migrated)
        self.assertTrue(list((self.root / 'backups' / 'actual').glob('*메뉴후보_양식갱신전.csv')))


if __name__ == "__main__":
    unittest.main()
