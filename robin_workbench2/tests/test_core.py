# -*- coding: utf-8 -*-
"""작업실 2.0 핵심 기능 시험 (화면 없이). 실행: python -m unittest discover -s tests -v"""
import csv
import datetime as dt
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from robin_workbench import analysis, content, flow, menus  # noqa: E402
from robin_workbench.store import Store, WorkbenchError  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.out = Path(tempfile.mkdtemp())
        os.environ["ROBIN_WB_OUT"] = str(self.out)
        self.ex = Store(self.home, "예시")
        self.real = Store(self.home, "실제")

    def csv_file(self, rows, enc="utf-8-sig"):
        p = Path(tempfile.mkdtemp()) / "in.csv"
        with open(p, "w", newline="", encoding=enc) as f:
            csv.writer(f).writerows(rows)
        return p


class InputAndEdit(Base):
    def test_add_edit_keeps_history_and_blank_is_not_zero(self):
        r = self.real.upsert("videos", {"플랫폼": "유튜브", "영상ID": "v1", "지표확인시각": "2026-09-22 09:00",
                                        "게시후경과시간": "72", "조회수": "1,200"})
        self.assertEqual(r["기록ID"], "V-0001")
        self.assertEqual(r["조회수"], "1200")
        self.assertEqual(r["클릭률"], "")  # 빈 값은 0이 아니라 빈 값
        self.real.upsert("videos", {**{k: v for k, v in r.items() if not k.startswith("_")}, "조회수": "1500"})
        self.assertEqual(Store(self.home, "실제").get("videos", "V-0001")["조회수"], "1500")
        h = [x for x in self.real.data["history"] if x["ID"] == "V-0001" and x["칸"] == "조회수"]
        self.assertEqual((h[-1]["이전"], h[-1]["이후"]), ("1200", "1500"))

    def test_invalid_inputs_explain_fix(self):
        bad = [({"플랫폼": "유튜브", "영상ID": "v", "지표확인시각": "2026-09-22", "게시후경과시간": "72"}, "형식"),
               ({"플랫폼": "유튜브", "영상ID": "v", "지표확인시각": "2026-09-22 09:00", "게시후경과시간": "사흘"}, "정수"),
               ({"플랫폼": "유튜브", "영상ID": "v", "지표확인시각": "2026-02-30 09:00", "게시후경과시간": "1"}, "없는"),
               ({"플랫폼": "틱톡2", "영상ID": "v", "지표확인시각": "2026-09-22 09:00", "게시후경과시간": "1"}, "중 하나"),
               ({"플랫폼": "유튜브", "영상ID": "", "지표확인시각": "2026-09-22 09:00", "게시후경과시간": "1"}, "필수")]
        for vals, word in bad:
            with self.assertRaises(WorkbenchError) as c:
                self.real.upsert("videos", vals)
            self.assertIn(word, str(c.exception))
        with self.assertRaises(WorkbenchError):
            self.real.upsert("menus", {"메뉴명": "국", "셰프점수1": "7"})
        self.assertEqual(self.real.rows("videos"), [])

    def test_duplicate_blocked(self):
        self.real.upsert("comments", {"댓글원문": "바닥이 눌어붙어요", "URL또는댓글ID": "u1"})
        with self.assertRaises(WorkbenchError) as c:
            self.real.upsert("comments", {"댓글원문": "바닥이  눌어붙어요!", "URL또는댓글ID": "u1"})
        self.assertIn("같은 내용", str(c.exception))


class ModesAndFiles(Base):
    def test_example_and_real_are_separate(self):
        self.assertTrue(self.ex.rows("comments"))
        self.assertEqual(self.real.rows("comments"), [])
        self.assertTrue(all(r["댓글ID"].startswith("EX-") for r in self.ex.rows("comments")))
        self.assertNotEqual(self.ex.path, self.real.path)
        with self.assertRaises(WorkbenchError):
            self.real.upsert("comments", {"댓글ID": "EX-C-0001", "댓글원문": "예시를 실제에"})

    def test_csv_import_refuses_example_rows_in_real_mode(self):
        p = self.csv_file([["댓글원문", "데이터구분"], ["진짜 댓글", "실제"], ["예시 댓글", "예시"]])
        with self.assertRaises(WorkbenchError) as c:
            self.real.import_csv("comments", p)
        self.assertIn("섞을 수 없습니다", str(c.exception))
        self.assertEqual(self.real.rows("comments"), [])  # 일부만 들어가지 않음

    def test_csv_import_aliases_extra_columns_duplicates_cp949(self):
        p = self.csv_file([["댓글", "링크", "작성일메모", "플랫폼"],
                           ["인덕션에서 되나요", "u9", "1.0에서 온 열", "유튜브"],
                           ["인덕션에서 되나요", "u9", "", "유튜브"],
                           ["", "", "", ""]], enc="cp949")
        res = self.real.import_csv("comments", p)
        self.assertEqual(res["added"], 1)
        self.assertEqual(res["skipped_duplicate_lines"], [3])
        r = self.real.rows("comments")[0]
        self.assertEqual(r["댓글원문"], "인덕션에서 되나요")
        self.assertEqual(r["_extra"], {"작성일메모": "1.0에서 온 열"})

    def test_csv_errors(self):
        with self.assertRaises(WorkbenchError):
            self.real.import_csv("comments", Path("/없는/파일.csv"))
        with self.assertRaises(WorkbenchError):
            self.real.import_csv("comments", self.csv_file([["아무", "제목"], ["a", "b"]]))
        p = self.csv_file([["플랫폼", "영상ID", "지표확인시각", "게시후경과시간"], ["유튜브", "v", "어제", "72"]])
        with self.assertRaises(WorkbenchError) as c:
            self.real.import_csv("videos", p)
        self.assertIn("2번째 줄", str(c.exception))
        bad = Path(tempfile.mkdtemp()) / "x.csv"
        bad.write_bytes(b"\xff\xfe\x00\xd8\x00\xdc")
        with self.assertRaises(WorkbenchError):
            self.real.import_csv("comments", bad)

    def test_export_and_template_roundtrip(self):
        out = self.ex.export_csv("comments")
        self.assertTrue(out.exists() and str(out).startswith(str(self.out)))
        tpl = self.real.export_template("comments")
        rows = list(csv.reader(tpl.read_text(encoding="utf-8-sig").splitlines()))
        self.assertTrue(rows[1][0].startswith("[안내]") or rows[1][1].startswith("[안내]"))
        with self.assertRaises(WorkbenchError) as c:  # 안내 줄은 건너뛰고, 예시 줄은 실제 모드라 거절
            self.real.import_csv("comments", tpl)
        self.assertIn("3번째 줄", str(c.exception))
        self.assertEqual(self.ex.import_csv("comments", tpl)["added"], 1)  # 예시 모드에서는 예시 줄이 들어감

    def test_backup_restore_and_corrupt_file(self):
        self.real.upsert("comments", {"댓글원문": "첫 댓글"})
        z = self.real.backup_zip(self.out)
        self.assertIn("workbench.json", zipfile.ZipFile(z).namelist())
        self.real.upsert("comments", {"댓글원문": "둘째 댓글"})
        self.real.restore(z)
        self.assertEqual([r["댓글원문"] for r in self.real.rows("comments")], ["첫 댓글"])
        with self.assertRaises(WorkbenchError):
            self.real.restore(self.ex.backup_zip(self.out))  # 다른 모드 백업
        self.real.path.write_text("{깨진", encoding="utf-8")
        with self.assertRaises(WorkbenchError) as c:
            Store(self.home, "실제")
        self.assertIn("백업에서 복원", str(c.exception))
        self.assertTrue(list(self.real.backup_dir.glob("workbench_*.json")))


class PainAnalysis(Base):
    def test_classify_group_trace(self):
        analysis.classify_all(self.ex)
        groups = analysis.group_pains(self.ex)
        self.assertEqual(sum(g["건수"] for g in groups), len(self.ex.rows("comments")))
        for g in groups:
            for cid in g["댓글ID"]:  # 묶인 뒤에도 원문·출처로 돌아간다
                c = self.ex.get("comments", cid)
                self.assertTrue(c["댓글원문"] and c["URL또는댓글ID"])
        other = [g for g in groups if g["분류"] == "기타·사람 확인 필요"]
        self.assertTrue(other)
        rep = analysis.pain_report(self.ex)
        self.assertIn("규칙 기반", rep)
        self.assertIn("(추정, 댓글에 직접 없음)", rep)
        self.assertNotIn("AI 분석", rep)

    def test_chef_category_wins_and_is_kept(self):
        c = self.ex.get("comments", "EX-C-0001")
        self.assertEqual(c["분류"], "요리 실패")
        analysis.classify_all(self.ex)
        self.assertEqual(self.ex.get("comments", "EX-C-0001")["분류"], "요리 실패")
        self.assertEqual(analysis.effective_category(c), ("요리 실패", "셰프 확정"))


class MenuSelection(Base):
    def test_auto_and_chef_scores_are_separate(self):
        analysis.classify_all(self.ex)
        menus.evaluate_all(self.ex)
        m = self.ex.get("menus", "EX-M-0001")
        self.assertEqual(m["셰프점수1"], "4")
        self.assertEqual(m["셰프점수2"], "")  # 자동 점수로 채우지 않음
        s = menus.summary(m)
        self.assertEqual(s["셰프합계"], 4)
        self.assertIsNotNone(s["자동합계"])
        reloaded = Store(self.home, "예시")
        self.assertIn("보류", menus.menu_report(reloaded))

    def test_hold_when_evidence_missing(self):
        menus.evaluate_all(self.ex)
        ev = self.ex.get("menus", "EX-M-0004")["_auto"]["평가"]["평가"]
        self.assertTrue(all(v["보류"] for k, v in ev.items() if k != "2" and k != "3"))
        self.assertTrue(ev["5"]["보류"])

    def test_unconfirmed_product_is_held(self):
        p = self.real.upsert("products", {"상품명": "냄비"})
        self.real.upsert("menus", {"메뉴명": "국", "관련상품ID": p["상품ID"], "설명": "색이 변한다"})
        menus.evaluate_all(self.real)
        ev = self.real.rows("menus")[0]["_auto"]["평가"]["평가"]
        self.assertTrue(ev["5"]["보류"])
        self.assertIn("공식 자료", ev["5"]["이유"])

    def test_theme_report(self):
        text = menus.theme_report(self.ex, dt.date(1966, 9, 10), "ISFJ", dt.date(2026, 10, 5))
        self.assertIn("말띠", text)
        self.assertIn("평가 보류", text)
        with self.assertRaises(WorkbenchError):
            menus.theme_report(self.real, None, None, dt.date.today())


class Content(Base):
    def test_requires_chef_confirmed_test(self):
        with self.assertRaises(WorkbenchError) as c:
            content.create_draft(self.ex, "EX-T-0002")
        self.assertIn("셰프 확인", str(c.exception))

    def test_draft_uses_only_recorded_values_and_evidence(self):
        analysis.classify_all(self.ex)
        did = content.create_draft(self.ex, "EX-T-0001", "키 콘텐츠")
        d = content.get_draft(self.ex, did)
        body = content.current(d["sections"]["본문 대본"])
        t = self.ex.get("tests", "EX-T-0001")
        self.assertIn(t["불세기"], body)
        self.assertIn(t["조리시간"], body)
        for line in t["재료와양"].splitlines():
            self.assertIn(line, body)
        ev = d["근거"]
        self.assertEqual(ev["테스트ID"], "EX-T-0001")
        self.assertIn("EX-C-0004", ev["댓글ID"])  # 무국 댓글이 근거
        self.assertTrue(ev["문의ID"])
        faq = content.current(d["sections"]["공구 FAQ"])
        self.assertIn("근거:", faq)  # 근거 있는 답변
        self.assertIn("[확인 필요: 답변 없음]", faq)
        self.assertIn("[확인 필요: 답변 근거 없음", faq)
        self.assertIn("필요 없을 수 있는 분", faq)
        for k in content.SECTIONS:
            txt = content.current(d["sections"][k])
            self.assertEqual(content.qa_check(txt, None), [], k)
        self.assertIn("완성 영상 아님", content.current(d["sections"]["근거·확인 필요"]))
        for th in content.current(d["sections"]["썸네일 문구"]).splitlines():
            if th.startswith("- "):
                self.assertLessEqual(len(th[2:].split(" (")[0]), content.THUMB_MAX)
        self.assertIn("여러분", content.current(d["sections"]["도입부 대본"]))
        shorts = content.current(d["sections"]["쇼츠·릴스"]).split("쇼츠 ")[1:]
        self.assertEqual(len({s.split("\n")[1] for s in shorts}), len(shorts))  # 쇼츠마다 다른 문제

    def test_missing_values_marked_not_invented(self):
        t = self.real.upsert("tests", {"메뉴": "달걀찜", "조리순서": "달걀을 푼다", "셰프확인": "예"})
        d = content.get_draft(self.real, content.create_draft(self.real, t["테스트ID"]))
        body = content.current(d["sections"]["본문 대본"])
        self.assertIn("[확인 필요: 불 세기]", body)
        self.assertIn("[확인 필요: 조리 시간]", body)
        self.assertIn("[확인 필요: 재료와 양]", body)
        self.assertNotRegex(body, r"\d+\s*(분|g|큰술|ml)")

    def test_edit_regenerate_keeps_chef_version_and_history(self):
        did = content.create_draft(self.ex, "EX-T-0001")
        self.assertTrue(content.save_edit(self.ex, did, "제목 후보", "셰프가 고친 제목"))
        self.assertFalse(content.save_edit(self.ex, did, "제목 후보", "셰프가 고친 제목"))
        t = self.ex.get("tests", "EX-T-0001")
        self.ex.upsert("tests", {**{k: v for k, v in t.items() if not k.startswith("_")}, "불세기": "약불"})
        res = content.regenerate(self.ex, did)
        d = content.get_draft(Store(self.home, "예시"), did)
        self.assertEqual(content.current(d["sections"]["제목 후보"]), "셰프가 고친 제목")
        self.assertIn("제목 후보", res["유지된셰프수정"])
        self.assertIn("약불", content.current(d["sections"]["본문 대본"]))
        self.assertGreaterEqual(len(d["versions"]), 3)
        self.assertTrue(any(v["내용"]["제목 후보"] != "셰프가 고친 제목" for v in d["versions"]))  # 이전 버전 보존
        content.undo_edit(self.ex, did, "제목 후보")
        self.assertNotEqual(content.current(content.get_draft(self.ex, did)["sections"]["제목 후보"]), "셰프가 고친 제목")
        out = content.export_draft(self.ex, did)
        self.assertIn("완성 영상 아님", out.read_text(encoding="utf-8"))

    def test_qa_flags_forbidden_and_claims(self):
        prod = self.ex.get("products", "EX-P-0001")
        w = content.qa_check("밥깡패 냄비로 조리 시간이 절반으로 줄어든다, 효능 최고", prod)
        self.assertEqual(len(w), 3)


class Retro(Base):
    def test_comparison_same_platform_and_hours_only(self):
        groups = analysis.compare_videos(self.ex)
        keys = {(g["플랫폼"], g["경과시간"]) for g in groups}
        self.assertIn(("유튜브", "72"), keys)
        self.assertIn(("유튜브 쇼츠", "24"), keys)
        yt = next(g for g in groups if g["플랫폼"] == "유튜브")
        self.assertTrue(yt["비교가능"])
        self.assertEqual(next(v for v in yt["영상"] if v["영상ID"] == "EX-vid-02")["클릭률"], "미확보")

    def test_gb_conversion_rules(self):
        s = analysis.gb_summary(self.ex)[0]
        self.assertIn("8.0%", s["전환율"])  # 96 / 1200
        self.assertIn("주문·매출에 넣지 않음", s["선예약"])
        self.assertEqual(s["주문"], "96")
        self.assertIn("계산 안 함", s["반품률"])  # 반품 값 비어 있음
        self.real.upsert("results", {"상품ID": "P", "기간": "1", "지표종류": "선예약", "값": "50", "집계기준": "폼"})
        r = analysis.gb_summary(self.real)[0]
        self.assertIn("계산 안 함", r["전환율"])
        self.assertEqual(r["주문"], "미확보")

    def test_retro_searchable_for_next_planning(self):
        hits = analysis.search_retros(self.ex, "인덕션")
        self.assertEqual([h["회고ID"] for h in hits], ["EX-R-0002"])
        self.assertEqual(analysis.search_retros(self.ex, "두부조림 도입"), [
            {"회고ID": "EX-R-0001", "종류": "영상", "대상": "EX-vid-01", "메뉴": "두부조림",
             "요점": "다음에바꿀한가지: 도입 30초 안에 실패 장면을 먼저 보여 주기"}])
        self.assertEqual(analysis.search_retros(self.ex, ""), [])


class Flow(Base):
    def test_stage_status(self):
        self.assertEqual(flow.current_stage(self.real), "1. 자료 입력")
        txt = flow.status_text(self.ex)
        self.assertIn("예시 모드", txt)
        self.assertIn("미검토 댓글", txt)

    def test_cli_example_writes_outputs(self):
        from robin_workbench import cli
        os.environ["ROBIN_WB_HOME"] = str(self.home)
        try:
            files = cli.run_example(self.home)
        finally:
            os.environ.pop("ROBIN_WB_HOME", None)
        self.assertEqual(len(files), 6)
        for f in files:
            text = f.read_text(encoding="utf-8")
            for banned in ("밥깡패", "매실", "체칼"):
                self.assertNotIn(banned, text)
        self.assertTrue(all(str(f).startswith(str(self.out)) for f in files))


if __name__ == "__main__":
    unittest.main()
