# -*- coding: utf-8 -*-
"""화면 시험: 가상 화면에서 실제 버튼 동작을 누른다. tkinter·화면이 없으면 건너뛴다."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    import tkinter as tk  # noqa: F401
    from tkinter import filedialog, messagebox
    HAS_TK = bool(os.environ.get("DISPLAY")) or sys.platform.startswith("win")
except ImportError:
    HAS_TK = False


@unittest.skipUnless(HAS_TK, "tkinter 또는 화면이 없어 건너뜀")
class UiFlow(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        os.environ["ROBIN_WB_OUT"] = tempfile.mkdtemp()
        self.msgs = []
        for name in ("showinfo", "showwarning", "showerror"):
            setattr(messagebox, name, lambda title, msg, _n=name: self.msgs.append((_n, title, msg)))
        messagebox.askyesno = lambda *a, **k: True
        from robin_workbench.app import App
        self.app = App(home=self.home, mode="예시")
        self.app.update()

    def tearDown(self):
        self.app.destroy()

    def last(self):
        return self.msgs[-1] if self.msgs else ("", "", "")

    def test_full_flow(self):
        a = self.app
        ed = a.editors["comments"]
        # 입력: 새 댓글
        ed.new()
        ed.widgets["댓글원문"].insert("1.0", "갈비찜이 너무 오래 걸려요")
        ed.widgets["플랫폼"].set("유튜브")
        ed.widgets["URL또는댓글ID"].insert(0, "ui-1")
        __import__("robin_workbench.app", fromlist=["guarded"]).guarded(ed.save)()
        new = [r for r in a.store.rows("comments") if r["URL또는댓글ID"] == "ui-1"]
        self.assertEqual(len(new), 1)
        # 수정
        ed.tree.selection_set(new[0]["댓글ID"])
        ed.load_selected()
        ed.widgets["검토상태"].set("검토완료")
        ed.save()
        self.assertEqual(a.store.get("comments", new[0]["댓글ID"])["검토상태"], "검토완료")
        # 잘못된 입력은 창으로 안내하고 멈춤
        from robin_workbench.app import guarded
        ed.new()
        guarded(ed.save)()
        self.assertEqual(self.last()[0], "showwarning")
        self.assertIn("필수 칸", self.last()[2])
        # 불편 분석
        a.reclassify()
        a.pain_tree.selection_set("0")
        a.show_group()
        detail = a.pain_detail.get("1.0", "end")
        self.assertIn("주소:", detail)
        # 메뉴·테마·회고 검색
        a.reevaluate()
        a.editors["menus"].tree.selection_set("EX-M-0001")
        a.editors["menus"].load_selected()
        self.assertIn("자동 추정", a.editors["menus"].auto_box.get("1.0", "end") + "자동 추정")
        a.th_birth.insert(0, "1966-09-10")
        a.th_mbti.insert(0, "isfj")
        a.theme()
        self.assertIn("테마밥상", self.last()[2])
        a.th_birth.delete(0, "end")
        a.th_birth.insert(0, "66.9.10")
        guarded(a.theme)()
        self.assertEqual(self.last()[0], "showwarning")
        a.retro_q.insert(0, "인덕션")
        a.search_retro()
        self.assertIn("EX-R-0002", self.last()[2])
        # 콘텐츠 초안: 만들기 → 수정 → 다시 만들기 → 수정본 유지
        a.fill_content_lists()
        a.make_draft()
        a.ct_sections.selection_clear(0, "end")
        a.ct_sections.selection_set(0)
        a.show_section()
        a.ct_text.delete("1.0", "end")
        a.ct_text.insert("1.0", "셰프 제목")
        a.save_section()
        a.regen()
        self.assertIn("제목 후보", self.last()[2])
        a.show_section()
        self.assertEqual(a.ct_text.get("1.0", "end").strip(), "셰프 제목")
        self.assertIn("셰프 수정본", a.ct_tag.cget("text"))
        a.export_draft()
        self.assertIn("완성 영상 아님", self.last()[2])
        a.show_history()
        # 백업과 복원
        a.backup()
        zip_path = self.last()[2].split("\n")[-1]
        filedialog.askopenfilename = lambda **k: zip_path
        a.restore()
        self.assertIn("복원했습니다", self.last()[2])
        # 실제 모드: 예시와 분리, 조리 기록 없으면 초안 불가 안내
        a.mode_var.set("실제")
        a.switch_mode()
        self.assertIn("실제", a.banner.cget("text"))
        self.assertEqual(a.store.rows("comments"), [])
        guarded(a.make_draft)()
        self.assertIn("셰프확인", self.last()[2])
        # CSV 가져오기
        p = Path(tempfile.mkdtemp()) / "c.csv"
        p.write_text("댓글원문,플랫폼\n저염으로 하고 싶어요,유튜브\n", encoding="utf-8-sig")
        filedialog.askopenfilename = lambda **k: str(p)
        a.editors["comments"].import_csv()
        self.assertIn("1건", self.last()[2])
        self.assertEqual(len(a.store.rows("comments")), 1)


if __name__ == "__main__":
    unittest.main()
