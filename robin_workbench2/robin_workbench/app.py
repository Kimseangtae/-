# -*- coding: utf-8 -*-
"""로빈 요리·공구 작업실 2.0 화면 (tkinter, 파이썬 기본 포함)."""
from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import VERSION, analysis, content, flow, menus
from .schema import CRITERIA, ORIGIN_AUTO, ORIGIN_CHEF, ORIGIN_RAW, TABLES
from .store import Store, WorkbenchError, default_output

FONT = ("맑은 고딕", 11) if sys.platform.startswith("win") else ("NanumGothic", 11)
FONT_B = (FONT[0], 11, "bold")
FONT_T = (FONT[0], 14, "bold")
ORIGIN_COLOR = {ORIGIN_RAW: "#1f5fa8", ORIGIN_CHEF: "#2e7d32", ORIGIN_AUTO: "#8a5a00"}
MODE_COLOR = {"예시": "#fff3cd", "실제": "#d4edda"}


def open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except OSError as e:
        messagebox.showinfo("폴더 위치", f"폴더를 자동으로 열지 못했습니다.\n직접 여세요: {path}\n({e})")


def guarded(fn):
    """오류가 나면 원인과 해결 방법을 창으로 보여 준다."""
    def wrap(*a, **k):
        try:
            return fn(*a, **k)
        except WorkbenchError as e:
            messagebox.showwarning("확인이 필요합니다", str(e))
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("예상하지 못한 오류",
                                 f"{type(e).__name__}: {e}\n\n→ 방금 한 작업을 알려 주시면 고치겠습니다. "
                                 "자료는 저장할 때마다 자동 백업됩니다.")
    return wrap


class ScrollForm(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(win, width=e.width))
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")


class TableEditor(ttk.Frame):
    """표 하나를 보고·고치는 공통 화면: 목록 + 입력 칸 + CSV 가져오기/내보내기."""

    def __init__(self, parent, app: "App", table: str, extra_panel=None):
        super().__init__(parent)
        self.app, self.table = app, table
        self.t = TABLES[table]
        self.widgets: dict[str, object] = {}
        head = ttk.Frame(self)
        head.pack(fill="x", padx=6, pady=4)
        ttk.Label(head, text=self.t.title, font=FONT_T).pack(side="left")
        for txt, cmd in [("새 항목", self.new), ("저장", self.save), ("삭제", self.delete),
                         ("CSV 가져오기", self.import_csv), ("CSV 내보내기", self.export_csv), ("빈 양식 받기", self.template)]:
            ttk.Button(head, text=txt, command=guarded(cmd)).pack(side="left", padx=2)
        ttk.Label(self, text=self.t.help, wraplength=1100, foreground="#444", font=FONT).pack(fill="x", padx=8)
        legend = ttk.Frame(self)
        legend.pack(fill="x", padx=8)
        for o in (ORIGIN_RAW, ORIGIN_CHEF, ORIGIN_AUTO):
            tk.Label(legend, text=f"■ {o}", fg=ORIGIN_COLOR[o], font=FONT).pack(side="left", padx=6)
        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=6, pady=4)
        left = ttk.Frame(body)
        cols = [f.key for f in self.t.fields if f.in_list]
        if table == "menus":
            cols += ["자동합계(추정)", "셰프합계"]
        self.tree = ttk.Treeview(left, columns=cols, show="headings", height=18)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=110 if c != "댓글원문" and c != "질문원문" else 280, stretch=True)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.load_selected())
        ysb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=ysb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        ysb.pack(side="right", fill="y")
        body.add(left, weight=3)
        form = ScrollForm(body)
        body.add(form, weight=4)
        self.build_form(form.inner)
        self.auto_box = tk.Text(form.inner, height=7, width=40, font=FONT, bg="#fff8e6", wrap="word")
        tk.Label(form.inner, text="자동 추정\n(참고용,\n사실 아님)", fg=ORIGIN_COLOR[ORIGIN_AUTO], font=FONT_B,
                 justify="left").grid(row=0, column=0, sticky="nw", padx=4, pady=4)
        self.auto_box.grid(row=0, column=1, sticky="we", padx=4, pady=4)
        if extra_panel:
            extra_panel(form.inner)
        self.refresh()

    def build_form(self, parent):
        for i, f in enumerate(self.t.fields):
            color = ORIGIN_COLOR.get(f.origin, "#222")
            tk.Label(parent, text=f"{f.key}{' *' if f.required else ''}\n[{f.origin}]", fg=color, font=FONT,
                     justify="left").grid(row=i * 2 + 2, column=0, sticky="nw", padx=4, pady=(6, 0))
            if f.kind == "long":
                w = tk.Text(parent, height=4, width=40, font=FONT, wrap="word")
            elif f.kind == "choice":
                w = ttk.Combobox(parent, values=[""] + f.choices, state="readonly", font=FONT, width=40)
            elif f.kind == "score":
                w = ttk.Combobox(parent, values=["", "1", "2", "3", "4", "5"], state="readonly", font=FONT, width=6)
            else:
                w = ttk.Entry(parent, font=FONT, width=40)
            w.grid(row=i * 2 + 2, column=1, sticky="we", padx=4, pady=(6, 0))
            hint = " · ".join(x for x in [f.help, f"예: {f.example}" if f.example else ""] if x)
            if hint:
                tk.Label(parent, text=hint.replace("\n", " / "), fg="#777", font=(FONT[0], 9), wraplength=480,
                         justify="left").grid(row=i * 2 + 3, column=1, sticky="w", padx=4)
            self.widgets[f.key] = w
        parent.columnconfigure(1, weight=1)

    # --- 값 읽고 쓰기
    def get_values(self) -> dict:
        out = {}
        for k, w in self.widgets.items():
            out[k] = w.get("1.0", "end").rstrip("\n") if isinstance(w, tk.Text) else w.get()
        return out

    def set_values(self, rec: dict) -> None:
        for k, w in self.widgets.items():
            v = rec.get(k, "")
            if isinstance(w, tk.Text):
                w.delete("1.0", "end")
                w.insert("1.0", v)
            elif isinstance(w, ttk.Combobox):
                w.set(v)
            else:
                w.delete(0, "end")
                w.insert(0, v)
        self.show_auto(rec)

    def show_auto(self, rec: dict) -> None:
        self.auto_box.configure(state="normal")
        self.auto_box.delete("1.0", "end")
        self.auto_box.insert("1.0", self.auto_text(rec))
        self.auto_box.configure(state="disabled")

    def auto_text(self, rec: dict) -> str:
        a = rec.get("_auto", {}) if rec else {}
        extra = rec.get("_extra", {}) if rec else {}
        L = []
        if "분류" in a:
            c = a["분류"]
            L.append(f"자동 분류: {c['대표분류']} / 주제: {c['주제']}\n근거: {c['근거']}\n방식: {c['방식']}")
        if "평가" in a:
            ev = a["평가"]
            L.append(f"{ev['방식']} ({ev['계산시각']})")
            for i in range(1, 7):
                x = ev["평가"][str(i)]
                L.append(f"{i}) {CRITERIA[i-1]}: {'보류' if x['보류'] else x['점수']} — {x['이유']}")
        if extra:
            L.append("가져온 파일의 추가 열(보존): " + ", ".join(f"{k}={v}" for k, v in extra.items()))
        return "\n".join(L) or "없음"

    def selected_id(self) -> str:
        sel = self.tree.selection()
        return sel[0] if sel else ""

    def refresh(self, keep: str = "") -> None:
        self.tree.delete(*self.tree.get_children())
        for r in self.app.store.rows(self.table):
            rid = r[self.t.id_field]
            vals = [str(r.get(c, "")).replace("\n", " ")[:80] for c in self.tree["columns"]]
            if self.table == "menus":
                sm = menus.summary(r)
                vals[-2] = "계산 전" if not r.get("_auto", {}).get("평가") else \
                    f"{sm['자동합계'] if sm['자동합계'] is not None else '-'} (보류 {sm['자동보류']})"
                vals[-1] = f"{sm['셰프합계'] if sm['셰프합계'] is not None else '-'} (미평가 {sm['셰프미평가']})"
            self.tree.insert("", "end", iid=rid, values=vals)
        if keep and self.tree.exists(keep):
            self.tree.selection_set(keep)
            self.tree.see(keep)

    def load_selected(self) -> None:
        rid = self.selected_id()
        rec = self.app.store.get(self.table, rid) if rid else None
        if rec:
            self.set_values(rec)

    # --- 버튼
    def new(self):
        self.tree.selection_remove(self.tree.selection())
        self.set_values({})

    def save(self):
        vals = self.get_values()
        rec = self.app.store.upsert(self.table, vals)
        self.refresh(keep=rec[self.t.id_field])
        self.set_values(rec)
        self.app.after_change()

    def delete(self):
        rid = self.selected_id()
        if not rid:
            raise WorkbenchError("지울 항목을 목록에서 먼저 고르세요.")
        if messagebox.askyesno("삭제 확인", f"{rid}를 지울까요?\n지우기 전 상태는 자동 백업에 남습니다."):
            self.app.store.delete(self.table, rid)
            self.refresh()
            self.new()
            self.app.after_change()

    def import_csv(self):
        path = filedialog.askopenfilename(title=f"{self.t.title} CSV 고르기", filetypes=[("CSV", "*.csv"), ("모든 파일", "*.*")])
        if not path:
            return
        res = self.app.store.import_csv(self.table, Path(path))
        self.refresh()
        self.app.after_change()
        msg = f"{res['added']}건을 넣었습니다."
        if res["skipped_duplicate_lines"]:
            msg += f"\n중복이라 건너뛴 줄: {', '.join(map(str, res['skipped_duplicate_lines']))}"
        messagebox.showinfo("가져오기 완료", msg)

    def export_csv(self):
        out = self.app.store.export_csv(self.table)
        messagebox.showinfo("내보내기 완료", f"저장했습니다:\n{out}")

    def template(self):
        out = self.app.store.export_template(self.table)
        messagebox.showinfo("양식 저장", f"빈 양식(안내·예시 줄 포함)을 저장했습니다:\n{out}")


class App(tk.Tk):
    def __init__(self, home: Path | None = None, mode: str = "예시"):
        super().__init__()
        self.title(f"로빈 요리·공구 작업실 {VERSION}")
        self.geometry("1320x860")
        self.option_add("*Font", FONT)
        style = ttk.Style(self)
        style.configure("Treeview", font=FONT, rowheight=26)
        style.configure("Treeview.Heading", font=FONT_B)
        style.configure("TNotebook.Tab", font=FONT_B, padding=(12, 6))
        self.home = home
        self.store = Store(home, mode)
        self.banner = tk.Label(self, font=FONT_B, anchor="w", padx=10, pady=6)
        self.banner.pack(fill="x")
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)
        self.build()

    # --- 화면 구성
    def build(self):
        for tab in self.nb.tabs():
            self.nb.forget(tab)
        self.editors: dict[str, TableEditor] = {}
        self.tab_start()
        self.tab_input()
        self.tab_pain()
        self.tab_menus()
        self.tab_tests()
        self.tab_content()
        self.tab_retro()
        self.after_change()

    def after_change(self):
        s = self.store
        self.banner.configure(text=f"  지금 {s.mode} 자료를 보고 있습니다  ·  {flow.current_stage(s)}  ·  "
                                   f"자료 위치: {s.folder}", bg=MODE_COLOR[s.mode])
        if hasattr(self, "status_box"):
            self._set_text(self.status_box, flow.status_text(s))

    @staticmethod
    def _set_text(w: tk.Text, text: str, readonly: bool = True):
        w.configure(state="normal")
        w.delete("1.0", "end")
        w.insert("1.0", text)
        if readonly:
            w.configure(state="disabled")

    def tab_start(self):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="시작")
        top = ttk.Frame(f)
        top.pack(fill="x", padx=10, pady=8)
        ttk.Label(top, text="자료 모드:", font=FONT_B).pack(side="left")
        self.mode_var = tk.StringVar(value=self.store.mode)
        for m in ("예시", "실제"):
            ttk.Radiobutton(top, text=f"{m} 자료", value=m, variable=self.mode_var,
                            command=guarded(self.switch_mode)).pack(side="left", padx=6)
        for txt, cmd in [("결과 폴더 열기", lambda: open_folder(self.store.output_dir())),
                         ("자료 폴더 열기", lambda: open_folder(self.store.folder)),
                         ("백업 만들기", self.backup), ("백업에서 복원", self.restore)]:
            ttk.Button(top, text=txt, command=guarded(cmd)).pack(side="left", padx=4)
        ttk.Label(f, text="작업 순서: 자료 입력 → 불편 분석 → 메뉴 후보 → 조리 기록 → 콘텐츠 초안 → 성과 회고",
                  font=FONT_T).pack(anchor="w", padx=10, pady=(4, 2))
        self.status_box = tk.Text(f, height=16, font=FONT, bg="#fafafa", wrap="word")
        self.status_box.pack(fill="x", padx=10)
        guide = ("안내\n"
                 "· 예시 자료와 실제 자료는 폴더가 따로입니다. 위 띠 색이 노랑이면 예시, 초록이면 실제입니다.\n"
                 "· 저장할 때마다 이전 상태가 자동 백업됩니다(최근 50개, 자료 폴더의 backups). '백업 만들기'는 다운로드 폴더에 zip을 만듭니다.\n"
                 "· 복원: '백업에서 복원'으로 zip 또는 backups의 json을 고르면, 지금 상태를 먼저 백업한 뒤 되돌립니다.\n"
                 "· 결과물(보고서·초안·CSV)은 다운로드\\로빈_요리공구작업실2_결과 폴더에 저장됩니다.\n"
                 "· 분류·평가는 모두 규칙 기반 자동 추정입니다. 외부 AI·인터넷을 쓰지 않으며, 게시·발송 기능은 없습니다.\n"
                 "· 최종 메뉴, 맛, 조리 안전성, 상품 사용 경험은 로빈님이 판단합니다.")
        ttk.Label(f, text=guide, justify="left", wraplength=1200, font=FONT).pack(anchor="w", padx=10, pady=8)

    def tab_input(self):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="1 자료 입력")
        inner = ttk.Notebook(f)
        inner.pack(fill="both", expand=True)
        for key in ("comments", "videos", "products", "inquiries", "results"):
            ed = TableEditor(inner, self, key)
            inner.add(ed, text=TABLES[key].title)
            self.editors[key] = ed

    def tab_pain(self):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="2 불편 분석")
        top = ttk.Frame(f)
        top.pack(fill="x", padx=8, pady=6)
        ttk.Button(top, text="분류 다시 하기 (규칙 기반)", command=guarded(self.reclassify)).pack(side="left")
        ttk.Button(top, text="보고서 저장", command=guarded(self.save_pain_report)).pack(side="left", padx=6)
        ttk.Label(top, text=f"방식: {analysis.METHOD} — 로빈님이 확정한 분류는 바꾸지 않습니다.").pack(side="left", padx=10)
        pw = ttk.PanedWindow(f, orient="vertical")
        pw.pack(fill="both", expand=True, padx=8, pady=4)
        cols = ("분류", "주제", "건수", "셰프확정", "대표 댓글")
        self.pain_tree = ttk.Treeview(pw, columns=cols, show="headings", height=12)
        for c, w in zip(cols, (140, 200, 60, 80, 600)):
            self.pain_tree.heading(c, text=c)
            self.pain_tree.column(c, width=w)
        self.pain_tree.bind("<<TreeviewSelect>>", lambda e: self.show_group())
        pw.add(self.pain_tree, weight=2)
        self.pain_detail = tk.Text(pw, height=14, font=FONT, wrap="word")
        pw.add(self.pain_detail, weight=3)
        self.fill_pain()

    def tab_menus(self):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="3 메뉴 후보")
        bar = ttk.Frame(f)
        bar.pack(fill="x", padx=8, pady=4)
        ttk.Button(bar, text="자동 평가 다시 계산 (추정)", command=guarded(self.reevaluate)).pack(side="left")
        ttk.Button(bar, text="메뉴 선정표 저장", command=guarded(self.save_menu_report)).pack(side="left", padx=4)
        ttk.Label(bar, text="  이전 회고 검색:").pack(side="left")
        self.retro_q = ttk.Entry(bar, width=18)
        self.retro_q.pack(side="left")
        ttk.Button(bar, text="검색", command=guarded(self.search_retro)).pack(side="left", padx=4)
        ttk.Label(bar, text="  테마 추천 — 생년월일").pack(side="left")
        self.th_birth = ttk.Entry(bar, width=11)
        self.th_birth.pack(side="left")
        ttk.Label(bar, text="성격유형").pack(side="left")
        self.th_mbti = ttk.Entry(bar, width=5)
        self.th_mbti.pack(side="left")
        ttk.Button(bar, text="테마 밥상 추천", command=guarded(self.theme)).pack(side="left", padx=4)
        ed = TableEditor(f, self, "menus")
        ed.pack(fill="both", expand=True)
        self.editors["menus"] = ed

    def tab_tests(self):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="4 조리 기록")
        ed = TableEditor(f, self, "tests")
        ed.pack(fill="both", expand=True)
        self.editors["tests"] = ed

    def tab_content(self):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="5 콘텐츠 초안")
        bar = ttk.Frame(f)
        bar.pack(fill="x", padx=8, pady=6)
        ttk.Label(bar, text="셰프 확인된 조리 테스트:").pack(side="left")
        self.ct_test = ttk.Combobox(bar, state="readonly", width=28)
        self.ct_test.pack(side="left", padx=4)
        self.ct_kind = ttk.Combobox(bar, state="readonly", values=content.KINDS, width=12)
        self.ct_kind.set(content.KINDS[0])
        self.ct_kind.pack(side="left", padx=4)
        ttk.Label(bar, text="시청자 호칭").pack(side="left")
        self.ct_aud = ttk.Entry(bar, width=8)
        self.ct_aud.insert(0, "여러분")
        self.ct_aud.pack(side="left", padx=4)
        ttk.Button(bar, text="초안 만들기", command=guarded(self.make_draft)).pack(side="left", padx=4)
        ttk.Label(bar, text="   초안:").pack(side="left")
        self.ct_draft = ttk.Combobox(bar, state="readonly", width=30)
        self.ct_draft.bind("<<ComboboxSelected>>", lambda e: self.show_draft())
        self.ct_draft.pack(side="left", padx=4)
        body = ttk.PanedWindow(f, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8)
        self.ct_sections = tk.Listbox(body, font=FONT, width=18, exportselection=False)
        self.ct_sections.bind("<<ListboxSelect>>", lambda e: self.show_section())
        body.add(self.ct_sections, weight=1)
        right = ttk.Frame(body)
        body.add(right, weight=5)
        self.ct_tag = tk.Label(right, font=FONT_B, anchor="w")
        self.ct_tag.pack(fill="x")
        self.ct_text = tk.Text(right, font=FONT, wrap="word", undo=True)
        self.ct_text.pack(fill="both", expand=True)
        btns = ttk.Frame(right)
        btns.pack(fill="x", pady=4)
        for txt, cmd in [("이 항목 저장 (셰프 수정)", self.save_section), ("수정 취소 → 자동 초안", self.undo_section),
                         ("자동 초안 다시 만들기 (수정본 유지)", self.regen), ("변경 기록 보기", self.show_history),
                         ("파일로 저장", self.export_draft)]:
            ttk.Button(btns, text=txt, command=guarded(cmd)).pack(side="left", padx=3)
        self.ct_warn = tk.Label(right, fg="#b00020", font=FONT, anchor="w", justify="left", wraplength=1000)
        self.ct_warn.pack(fill="x")
        self.fill_content_lists()

    def tab_retro(self):
        f = ttk.Frame(self.nb)
        self.nb.add(f, text="6 성과 회고")
        bar = ttk.Frame(f)
        bar.pack(fill="x", padx=8, pady=4)
        ttk.Button(bar, text="지표 비교·공구 결과 보기", command=guarded(self.show_compare)).pack(side="left")
        ttk.Button(bar, text="회고 보고서 저장", command=guarded(self.save_retro_report)).pack(side="left", padx=4)
        ttk.Label(bar, text="비교는 같은 플랫폼·같은 경과시간끼리만, 선예약은 주문·매출에 넣지 않습니다.").pack(side="left", padx=8)
        ed = TableEditor(f, self, "retros")
        ed.pack(fill="both", expand=True)
        self.editors["retros"] = ed

    # --- 동작
    def switch_mode(self):
        m = self.mode_var.get()
        if m == self.store.mode:
            return
        self.store = Store(self.home, m)
        remember_mode(self.store.home, m)
        self.build()
        self.nb.select(0)

    def backup(self):
        out = self.store.backup_zip()
        messagebox.showinfo("백업 완료", f"백업을 만들었습니다:\n{out}")

    def restore(self):
        path = filedialog.askopenfilename(title="백업 파일 고르기", initialdir=str(default_output() / "백업"),
                                          filetypes=[("백업", "*.zip *.json")])
        if not path:
            return
        if not messagebox.askyesno("복원 확인", "지금 자료를 먼저 백업한 뒤 고른 백업으로 되돌립니다. 진행할까요?"):
            return
        safety = self.store.restore(Path(path))
        self.build()
        messagebox.showinfo("복원 완료", f"복원했습니다. 복원 전 상태는 여기 있습니다:\n{safety}")

    def reclassify(self):
        n = analysis.classify_all(self.store)
        self.fill_pain()
        self.editors["comments"].refresh()
        self.after_change()
        messagebox.showinfo("분류 완료", f"댓글 {n}건을 규칙 기반으로 다시 분류했습니다.\n로빈님이 확정한 '분류' 칸은 그대로입니다.")

    def fill_pain(self):
        self.pain_tree.delete(*self.pain_tree.get_children())
        self.groups = analysis.group_pains(self.store)
        for i, g in enumerate(self.groups):
            self.pain_tree.insert("", "end", iid=str(i), values=(g["분류"], g["주제"], g["건수"], g["확정수"],
                                                                g["대표댓글"][:120]))
        self._set_text(self.pain_detail, "묶음을 고르면 원문과 출처가 보입니다.", readonly=False)

    def show_group(self):
        sel = self.pain_tree.selection()
        if not sel:
            return
        g = self.groups[int(sel[0])]
        L = [f"{g['분류']} — {g['주제']} ({g['건수']}건)", f"영상 아이디어: {g['영상아이디어']}"]
        if g["추정"]:
            L.append(f"(추정, 댓글에 직접 없음) {g['추정']}")
        L.append("\n원문과 출처:")
        for cid in g["댓글ID"]:
            c = self.store.get("comments", cid)
            cat, src = analysis.effective_category(c)
            L.append(f"- {cid} [{c.get('날짜')}, {c.get('플랫폼')}, {c.get('출처영상')}] ({src}) \"{c.get('댓글원문')}\"\n"
                     f"   주소: {c.get('URL또는댓글ID') or '미입력'}")
        self._set_text(self.pain_detail, "\n".join(L), readonly=False)

    def _save_md(self, name: str, text: str) -> Path:
        out = self.store.output_dir() / f"{name}_{dt.datetime.now():%Y%m%d_%H%M%S}.md"
        out.write_text(text + "\n", encoding="utf-8")
        return out

    def save_pain_report(self):
        messagebox.showinfo("저장", f"저장했습니다:\n{self._save_md('불편분석', analysis.pain_report(self.store))}")

    def reevaluate(self):
        menus.evaluate_all(self.store)
        self.editors["menus"].refresh()
        self.editors["menus"].load_selected()
        messagebox.showinfo("계산 완료", "자동 평가(추정)를 다시 계산했습니다. 셰프 점수는 바꾸지 않았습니다.")

    def save_menu_report(self):
        messagebox.showinfo("저장", f"저장했습니다:\n{self._save_md('메뉴선정표', menus.menu_report(self.store))}")

    def search_retro(self):
        q = self.retro_q.get().strip()
        if not q:
            raise WorkbenchError("검색어를 넣으세요. 예: 메뉴 이름, '인덕션'")
        hits = analysis.search_retros(self.store, q)
        msg = "\n".join(f"- {h['회고ID']} [{h['종류']} {h['대상']}] {h['메뉴'] or ''}\n   {h['요점']}" for h in hits)
        messagebox.showinfo("이전 회고", msg or f"'{q}'가 들어간 회고가 없습니다.")

    def theme(self):
        b = self.th_birth.get().strip()
        birth = None
        if b:
            try:
                birth = dt.date.fromisoformat(b)
            except ValueError:
                raise WorkbenchError(f"생년월일 형식이 맞지 않습니다. 예: 1966-09-10 (지금: '{b}')")
        try:
            text = menus.theme_report(self.store, birth, self.th_mbti.get().strip() or None, dt.date.today())
        except ValueError as e:
            raise WorkbenchError(str(e))
        out = self._save_md("테마밥상", text)
        messagebox.showinfo("테마 밥상 추천", f"재미·기획용 추천을 저장했습니다(규칙 기반):\n{out}")

    def fill_content_lists(self):
        tests = [t for t in self.store.rows("tests") if t.get("셰프확인") == "예"]
        self.ct_test.configure(values=[f"{t['테스트ID']} {t.get('메뉴', '')}" for t in tests])
        if tests and not self.ct_test.get():
            self.ct_test.current(0)
        drafts = self.store.data.get("drafts", {})
        self.ct_draft.configure(values=[f"{d} ({v['테스트ID']}, {v['종류']})" for d, v in drafts.items()])
        self.ct_sections.delete(0, "end")
        for s in content.SECTIONS:
            self.ct_sections.insert("end", s)

    def _draft_id(self) -> str:
        v = self.ct_draft.get()
        if not v:
            raise WorkbenchError("초안을 먼저 만들거나 고르세요.")
        return v.split(" ")[0]

    def _section(self) -> str:
        sel = self.ct_sections.curselection()
        if not sel:
            raise WorkbenchError("왼쪽 목록에서 항목을 고르세요.")
        return content.SECTIONS[sel[0]]

    def make_draft(self):
        v = self.ct_test.get()
        if not v:
            raise WorkbenchError("셰프 확인된 조리 테스트가 없습니다.\n→ 4 조리 기록에서 직접 조리한 기록의 '셰프확인'을 '예'로 저장하세요.")
        did = content.create_draft(self.store, v.split(" ")[0], self.ct_kind.get(), self.ct_aud.get().strip() or "여러분")
        self.fill_content_lists()
        idx = list(self.store.data["drafts"]).index(did)
        self.ct_draft.current(idx)
        self.ct_sections.selection_set(0)
        self.show_draft()
        self.after_change()

    def show_draft(self):
        self.ct_sections.selection_clear(0, "end")
        self.ct_sections.selection_set(0)
        self.show_section()

    def show_section(self):
        did, sec = self._draft_id(), self._section()
        d = content.get_draft(self.store, did)
        s = d["sections"][sec]
        tag = f"{sec} — " + ("셰프 수정본" if s.get("chef") is not None else "자동 초안") + f"  ·  {d['상태']}"
        self.ct_tag.configure(text=tag, fg="#2e7d32" if s.get("chef") is not None else "#8a5a00")
        self._set_text(self.ct_text, content.current(s), readonly=False)
        prod = self.store.get("products", d["근거"].get("상품ID", "")) if d["근거"].get("상품ID") else None
        warns = content.qa_check(content.current(s), prod)
        self.ct_warn.configure(text="\n".join("⚠ " + w for w in warns))

    def save_section(self):
        did, sec = self._draft_id(), self._section()
        changed = content.save_edit(self.store, did, sec, self.ct_text.get("1.0", "end"))
        self.show_section()
        messagebox.showinfo("저장", "셰프 수정본으로 저장했습니다. 이전 내용은 버전 기록에 남았습니다." if changed else "바뀐 내용이 없습니다.")

    def undo_section(self):
        did, sec = self._draft_id(), self._section()
        content.undo_edit(self.store, did, sec)
        self.show_section()

    def regen(self):
        res = content.regenerate(self.store, self._draft_id())
        self.show_section()
        messagebox.showinfo("다시 만들기", f"자동 초안 {len(res['바뀐자동안'])}개가 바뀌었습니다.\n"
                                          f"셰프 수정본 {len(res['유지된셰프수정'])}개는 그대로 유지했습니다: "
                                          f"{', '.join(res['유지된셰프수정']) or '없음'}")

    def show_history(self):
        d = content.get_draft(self.store, self._draft_id())
        L = [f"버전 {v['버전']} · {v['시각']} · {v['주체']} · {v['메모']}" for v in d["versions"]]
        win = tk.Toplevel(self)
        win.title(f"{d['초안ID']} 변경 기록")
        t = tk.Text(win, font=FONT, width=90, height=24)
        t.pack(fill="both", expand=True)
        hist = [h for h in self.store.data["history"] if h["ID"] == d["초안ID"]]
        t.insert("1.0", "\n".join(L) + "\n\n[세부 변경]\n" + "\n".join(
            f"{h['시각']} {h['칸']} ({h['사유']})" for h in hist))

    def export_draft(self):
        out = content.export_draft(self.store, self._draft_id())
        messagebox.showinfo("저장", f"저장했습니다(대본 초안, 완성 영상 아님):\n{out}")

    def show_compare(self):
        messagebox.showinfo("성과 비교", analysis.retro_report(self.store)[:3500])

    def save_retro_report(self):
        messagebox.showinfo("저장", f"저장했습니다:\n{self._save_md('성과회고', analysis.retro_report(self.store))}")


def remember_mode(home: Path, mode: str) -> None:
    try:
        home.mkdir(parents=True, exist_ok=True)
        (home / "마지막모드.txt").write_text(mode, encoding="utf-8")
    except OSError:
        pass


def last_mode(home: Path) -> str:
    try:
        m = (home / "마지막모드.txt").read_text(encoding="utf-8").strip()
        return m if m in ("예시", "실제") else "예시"
    except OSError:
        return "예시"


def main():
    from .store import default_home
    mode = "실제" if "--real" in sys.argv else "예시" if "--example" in sys.argv else last_mode(default_home())
    try:
        App(mode=mode).mainloop()
    except WorkbenchError as e:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("시작하지 못했습니다", str(e))


if __name__ == "__main__":
    main()
