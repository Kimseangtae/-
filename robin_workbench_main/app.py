"""로빈의밥상 요리·공구 작업실. 외부 연결 없는 로컬 앱. start.cmd 또는 python app.py"""
import argparse, os, tkinter as tk
from datetime import datetime
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
from schema import FIELDS, ENUMS, REQUIRED, CRITERIA, VERSION, IDEAS, OTHER
from core import (Store, Drafts, UserError, run_all, analysis, classify, classify_detail, evaluate, chef_scores, representative,
                  score_summary, linked_reviews, progress, STEPS, MODE_TITLE, DEFAULT_OUT)
from seed import initialize
from core import theme_report
from tkinter import simpledialog
import datetime as dt

ROOT = Path(__file__).resolve().parent
FONT = ('맑은 고딕', 11); BOLD = ('맑은 고딕', 11, 'bold'); SMALL = ('맑은 고딕', 10)
COLORS = {'example': ('#FFF3CD', '#7A5A00', '예시 연습 중 — 가상 자료입니다. 실제 실적·조리 근거로 쓰지 마세요.'),
          'actual': ('#D8F0DC', '#1E5B2A', '실제 운영 중 — 입력한 자료는 이 PC에만 저장됩니다.')}
STEP_TAB = {'자료 입력': (0, '댓글'), '불편 분석': (1, None), '메뉴 후보': (2, None), '조리 기록': (0, '조리테스트'), '콘텐츠 초안': (3, None), '성과 회고': (4, None)}


def friendly(e):
    if isinstance(e, UserError): return str(e)
    if isinstance(e, PermissionError): return f'파일을 쓸 수 없습니다: {getattr(e, "filename", "")}\n\n해결 방법: Excel 등에서 열어 둔 파일을 닫고 다시 시도하세요.'
    if isinstance(e, FileNotFoundError): return f'파일이나 폴더를 찾을 수 없습니다: {getattr(e, "filename", "")}\n\n해결 방법: 위치를 다시 선택하거나 [백업·도움말] 탭의 복원 안내를 보세요.'
    if isinstance(e, ValueError): return str(e)
    return f'예상하지 못한 오류: {type(e).__name__}: {e}\n\n해결 방법: 앱을 다시 켜 보세요. 계속되면 결과 폴더의 오류기록.txt를 보여 주세요.'


class App:
    def __init__(self, win, folder=ROOT, out_root=None):
        self.win = win; self.folder = Path(folder); self.out_root = Path(out_root) if out_root else DEFAULT_OUT
        initialize(self.folder)
        self.show_error = messagebox.showerror; self.ask = messagebox.askyesno  # 시험에서 바꿔 끼울 수 있게
        self.mode = tk.StringVar(value='예시 연습'); self.kind = tk.StringVar(value='댓글')
        self.widgets = {}; self.loaded_id = None; self.rows = []; self.draft_name = None
        win.title(f'로빈의밥상 | 요리·공구 작업실 {VERSION}'); win.geometry('1320x900'); win.minsize(1000, 700)
        style = ttk.Style()
        style.configure('.', font=FONT); style.configure('TButton', padding=6); style.configure('Treeview', rowheight=28, font=FONT)
        style.configure('Treeview.Heading', font=BOLD); style.configure('TNotebook.Tab', font=BOLD, padding=(14, 6))

        top = ttk.Frame(win, padding=(12, 10, 12, 4)); top.pack(fill='x')
        ttk.Label(top, text='로빈의밥상 · 요리에서 시작하는 작업실', font=('맑은 고딕', 17, 'bold')).pack(side='left')
        box = ttk.Combobox(top, textvariable=self.mode, values=['예시 연습', '실제 운영'], state='readonly', width=11, font=BOLD)
        box.pack(side='right'); box.bind('<<ComboboxSelected>>', lambda e: self.refresh_all())
        ttk.Label(top, text='자료 모드 ').pack(side='right')
        self.banner = tk.Label(win, font=BOLD, anchor='w', padx=14, pady=5); self.banner.pack(fill='x')
        ttk.Label(win, text='이 PC에만 저장 · 외부 AI 연결 없음(규칙 기반) · 실행 요금 0원 · 게시/발송 기능 없음', font=SMALL, padding=(14, 2)).pack(fill='x')

        steps = ttk.Frame(win, padding=(12, 4)); steps.pack(fill='x'); self.step_buttons = []
        for i, name in enumerate(STEPS):
            b = tk.Button(steps, font=SMALL, relief='groove', justify='center', command=lambda n=name: self.goto_step(n), cursor='hand2')
            b.pack(side='left', fill='x', expand=True, padx=2); self.step_buttons.append(b)
            if i < len(STEPS) - 1: ttk.Label(steps, text='→').pack(side='left')
        self.todo = tk.StringVar(); ttk.Label(win, textvariable=self.todo, foreground='#8A1C1C', padding=(14, 2), font=SMALL, wraplength=1250).pack(fill='x')

        self.tabs = ttk.Notebook(win); self.tabs.pack(fill='both', expand=True, padx=12, pady=6)
        self.t_input, self.t_analysis, self.t_menu, self.t_draft, self.t_search, self.t_help = [ttk.Frame(self.tabs, padding=6) for _ in range(6)]
        for tab, title in [(self.t_input, '① 자료 입력·조리 기록'), (self.t_analysis, '② 불편 분석'), (self.t_menu, '③ 메뉴 선정'),
                           (self.t_draft, '④ 콘텐츠 초안'), (self.t_search, '⑤ 성과 회고·검색'), (self.t_help, '백업·도움말')]:
            self.tabs.add(tab, text=title)
        self.build_input(); self.build_analysis(); self.build_menu(); self.build_draft(); self.build_search(); self.build_help()
        self.status = tk.StringVar(); ttk.Label(win, textvariable=self.status, padding=(14, 6), relief='sunken').pack(fill='x', side='bottom')
        self.refresh_all()

    # ---------- 공통 ----------
    def store(self): return Store(self.folder, 'example' if self.mode.get() == '예시 연습' else 'actual', self.out_root)
    def notify(self, text): self.status.set(f'{datetime.now():%H:%M} {text}')

    def fail(self, title, e):
        msg = friendly(e)
        try:
            self.out_root.mkdir(parents=True, exist_ok=True)
            with (self.out_root / '오류기록.txt').open('a', encoding='utf-8') as f: f.write(f'{datetime.now():%Y-%m-%d %H:%M:%S} [{title}] {type(e).__name__}: {e}\n')
        except OSError: pass
        self.show_error(title, msg); self.notify(f'{title}: {msg.splitlines()[0]}')

    def open_path(self, p):
        p = Path(p); p.mkdir(parents=True, exist_ok=True) if not p.suffix else None
        try: os.startfile(p)
        except OSError as e: self.fail('폴더 열기', e)

    def refresh_all(self):
        try:
            s = self.store(); data = s.all()
            if s.migrated: self.notify('이전 양식을 새 양식으로 갱신했습니다(원본은 backups에 보관): ' + ', '.join(s.migrated))
        except Exception as e: self.fail('자료 확인', e); return
        bg, fg, text = COLORS[s.mode]; self.banner.configure(bg=bg, fg=fg, text=text)
        self.update_steps(data); self.reload(); self.refresh_analysis(data); self.refresh_menu(data); self.refresh_drafts(keep=self.draft_name)

    def update_steps(self, data=None):
        data = data or self.store().all(); prog = progress(data); current = next((p for p in prog if not p['done']), None)
        for i, (b, p) in enumerate(zip(self.step_buttons, prog)):
            mark = '✔' if p['done'] else ('▶' if p is current else '·')
            b.configure(text=f'{mark} {i + 1}. {p["name"]}\n{p["summary"]}', bg='#E3F2E1' if p['done'] else ('#FFE8B3' if p is current else '#F4F4F4'))
        self.todo.set(f'지금 단계: {current["name"]} — 부족한 자료: ' + ' / '.join(current['missing']) if current else '모든 단계에 필요한 자료가 있습니다. 내용의 사실·맛·안전은 셰프가 최종 확인하세요.')

    def goto_step(self, name):
        tab, kind = STEP_TAB[name]
        if kind: self.kind.set(kind); self.reload()
        self.tabs.select(tab)

    # ---------- ① 자료 입력 ----------
    def build_input(self):
        bar = ttk.Frame(self.t_input); bar.pack(fill='x', pady=(0, 6))
        ttk.Label(bar, text='자료 종류').pack(side='left')
        kinds = ttk.Combobox(bar, textvariable=self.kind, values=list(FIELDS), state='readonly', width=11, font=BOLD)
        kinds.pack(side='left', padx=4); kinds.bind('<<ComboboxSelected>>', lambda e: self.reload())
        for title, fn in [('새 기록', self.new), ('저장', self.save), ('CSV 가져오기', self.import_csv), ('CSV 내보내기', self.export_csv),
                          ('빈 양식 폴더', lambda: self.open_path(self.folder / 'templates')), ('작성 안내', lambda: self.open_path(self.folder / '입력안내.md'))]:
            ttk.Button(bar, text=title, command=fn).pack(side='left', padx=2)
        pan = ttk.Panedwindow(self.t_input, orient='horizontal'); pan.pack(fill='both', expand=True)
        left = ttk.Frame(pan); pan.add(left, weight=2)
        self.tree = ttk.Treeview(left, columns=('id', 'summary', 'state'), show='headings')
        for c, t, w in [('id', 'ID', 70), ('summary', '기록 요약', 300), ('state', '상태·규칙 분류', 170)]: self.tree.heading(c, text=t); self.tree.column(c, width=w)
        ys = ttk.Scrollbar(left, orient='vertical', command=self.tree.yview); self.tree.configure(yscrollcommand=ys.set)
        ys.pack(side='right', fill='y'); self.tree.pack(fill='both', expand=True); self.tree.bind('<<TreeviewSelect>>', self.select)
        right = ttk.Frame(pan); pan.add(right, weight=3)
        self.form_title = tk.StringVar(); ttk.Label(right, textvariable=self.form_title, font=BOLD, foreground='#1F4E79').pack(anchor='w')
        self.canvas = tk.Canvas(right, highlightthickness=0); sb = ttk.Scrollbar(right, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=sb.set); sb.pack(side='right', fill='y'); self.canvas.pack(side='left', fill='both', expand=True)
        self.form = ttk.Frame(self.canvas, padding=8); wid = self.canvas.create_window((0, 0), window=self.form, anchor='nw')
        self.form.bind('<Configure>', lambda e: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(wid, width=e.width))
        self.canvas.bind('<Enter>', lambda e: self.canvas.bind_all('<MouseWheel>', lambda ev: self.canvas.yview_scroll(int(-ev.delta / 120), 'units')))
        self.canvas.bind('<Leave>', lambda e: self.canvas.unbind_all('<MouseWheel>'))

    def row_state(self, kind, r):
        if kind == '댓글': return f'{r.get("검토상태") or "미검토"} · ' + ', '.join(classify(r))
        return {'조리테스트': r.get('검토상태') or '미검토', '메뉴후보': r.get('최종판단') or '미정', '상품': '기능 ' + (r.get('기능검토') or '미검토'),
                '공구문의': r.get('기록유형') or '문의', '회고': r.get('유형', '')}.get(kind, r.get('날짜', '') or r.get('플랫폼', ''))

    def reload(self):
        kind = self.kind.get()
        try: s = self.store(); self.rows = s.read(kind); ex = Store(self.folder, 'example', self.out_root).read(kind)
        except Exception as e: self.fail('자료 확인', e); return
        sample = ex[0] if ex else {}
        self.tree.delete(*self.tree.get_children())
        for r in self.rows:
            summary = r.get('메뉴') or r.get('상품명') or r.get('질문') or r.get('원문', '')
            if kind == '댓글': summary = r.get('원문', '')
            self.tree.insert('', 'end', iid=r['id'], values=(r['id'], summary.replace('\n', ' ')[:70], self.row_state(kind, r)))
        for child in self.form.winfo_children(): child.destroy()
        self.widgets = {}; required = {k for g in REQUIRED[kind] for k in g}
        for field, helptext in FIELDS[kind].items():
            ttk.Label(self.form, text=field + (' *' if field in required or field == 'id' else ''), font=BOLD).pack(anchor='w', pady=(8, 0))
            ttk.Label(self.form, text=helptext, font=SMALL, foreground='#555555', wraplength=720).pack(anchor='w')
            if sample.get(field) and field not in ('id', '구분'):
                ttk.Label(self.form, text='예시: ' + sample[field].replace('\n', ' ')[:110], font=SMALL, foreground='#9A7B00', wraplength=720).pack(anchor='w')
            allowed = ENUMS.get((kind, field))
            if allowed:
                w = ttk.Combobox(self.form, values=[''] + allowed, state='readonly', font=FONT, width=20); w.pack(anchor='w')
            else:
                tall = 4 if field in ('원문', '조리순서', '재료와양', '실패와수정', '질문', '확인답변') else 2
                w = tk.Text(self.form, height=tall, wrap='word', font=FONT, relief='solid', borderwidth=1); w.pack(fill='x')
            self.widgets[field] = w
        self.form_title.set(f'{kind} — {"예시" if s.mode == "example" else "실제"} 기록 {len(self.rows)}건 · * 는 필수')
        self.new(); self.notify(f'{self.mode.get()} / {kind} {len(self.rows)}건')

    def get_field(self, f):
        w = self.widgets[f]; return w.get().strip() if isinstance(w, ttk.Combobox) else w.get('1.0', 'end-1c').strip()

    def set_field(self, f, v):
        w = self.widgets[f]
        if isinstance(w, ttk.Combobox): w.set(v)
        else: w.delete('1.0', 'end'); w.insert('1.0', v)

    def new(self):
        self.loaded_id = None
        for f in self.widgets: self.set_field(f, '')
        try: self.set_field('id', self.store().next_id(self.kind.get()))
        except Exception: pass
        self.set_field('구분', '예시' if self.mode.get() == '예시 연습' else '실제')
        for f, default in [('검토상태', '미검토'), ('기능검토', '미검토'), ('조건검토', '미검토'), ('경험확인', '미확인'), ('답변검토', '미검토'), ('최종판단', '미정'), ('기록유형', '문의')]:
            if f in self.widgets: self.set_field(f, default)
        self.canvas.yview_moveto(0)

    def select(self, event=None):
        sel = self.tree.selection()
        if not sel: return
        r = next((r for r in self.rows if r['id'] == sel[0]), None)
        if not r: return
        self.loaded_id = r['id']
        for f in self.widgets: self.set_field(f, r.get(f, ''))
        self.notify(f'{r["id"]} 기록을 불러왔습니다. 고친 뒤 [저장]을 누르세요.')

    def open_record(self, kind, rid):
        self.kind.set(kind); self.reload(); self.tabs.select(self.t_input)
        if self.tree.exists(rid): self.tree.selection_set(rid); self.tree.see(rid); self.select()

    def save(self):
        row = {f: self.get_field(f) for f in self.widgets}
        try:
            if self.loaded_id and row['id'] != self.loaded_id: raise UserError('기존 기록의 ID는 바꿀 수 없습니다.', '[새 기록]을 눌러 새 ID로 추가하세요.')
            if not self.loaded_id and any(r['id'] == row['id'] for r in self.rows): raise UserError(f'이미 있는 ID입니다: {row["id"]}', '왼쪽 목록에서 그 기록을 골라 수정하거나 [새 기록]을 누르세요.')
            self.store().upsert(self.kind.get(), row); rid = row['id']
            self.refresh_all(); self.open_record(self.kind.get(), rid); self.notify(f'{rid} 저장했습니다. 이전 입력은 backups 폴더에 보관했습니다.')
        except Exception as e: self.fail('저장하지 못했습니다', e)

    def import_csv(self, path=None):
        path = path or filedialog.askopenfilename(title=f'{self.kind.get()} CSV 고르기', filetypes=[('CSV', '*.csv')])
        if not path: return
        try:
            n = self.store().import_new(self.kind.get(), path); self.refresh_all()
            from core import duplicates
            dup = duplicates(self.store().read(self.kind.get())) if self.kind.get() in ('댓글', '공구문의') else []
            self.notify(f'{n}건 추가했습니다. 기존 ID는 덮어쓰지 않습니다.' + (f' 같은 내용 의심: {dup}' if dup else ''))
        except Exception as e: self.fail('가져오기 확인', e)

    def export_csv(self):
        try: p = self.store().export(self.kind.get()); self.notify(f'내보냈습니다: {p}'); self.open_path(p.parent)
        except Exception as e: self.fail('내보내기', e)

    # ---------- ② 불편 분석 ----------
    def build_analysis(self):
        bar = ttk.Frame(self.t_analysis); bar.pack(fill='x', pady=(0, 6))
        ttk.Label(bar, text='규칙 기반 분류 (AI 분석 아님) · 항목을 두 번 누르면 원문 기록으로 이동', font=BOLD).pack(side='left')
        for title, fn in [('새로고침', lambda: self.refresh_analysis()), ('원문 기록 열기', self.open_selected_comment), ('선택 댓글 확인 처리', self.mark_reviewed)]:
            ttk.Button(bar, text=title, command=fn).pack(side='right', padx=2)
        pan = ttk.Panedwindow(self.t_analysis, orient='horizontal'); pan.pack(fill='both', expand=True)
        self.atree = ttk.Treeview(pan, columns=('src',), show='tree headings'); self.atree.heading('#0', text='분류 → 주제 → 원문'); self.atree.heading('src', text='출처')
        self.atree.column('#0', width=520); self.atree.column('src', width=220); pan.add(self.atree, weight=3)
        self.atree.bind('<<TreeviewSelect>>', self.analysis_detail); self.atree.bind('<Double-1>', lambda e: self.open_selected_comment())
        self.adetail = tk.Text(pan, wrap='word', font=FONT); pan.add(self.adetail, weight=2); self.aitems = {}

    def refresh_analysis(self, data=None):
        try: data = data or self.store().all()
        except Exception as e: self.fail('분석', e); return
        self.atree.delete(*self.atree.get_children()); self.aitems = {}
        self.adetail.delete('1.0', 'end'); self.adetail.insert('1.0', '왼쪽에서 분류나 주제를 누르면 대표 댓글과 영상 아이디어(추정)가 여기에 나옵니다.')
        for cat, topics in analysis(data).items():
            ids = {it[1]['id'] for items in topics.values() for it in items}
            c = self.atree.insert('', 'end', text=f'{cat}  ({len(ids)}건)', open=True); self.aitems[c] = ('cat', cat)
            for topic, items in sorted(topics.items(), key=lambda kv: -len(kv[1])):
                t = self.atree.insert(c, 'end', text=f'{topic}  ({len(items)}건)', open=False); self.aitems[t] = ('topic', cat, topic)
                for kind, r, word in items:
                    src = ' / '.join(x for x in [r.get('플랫폼'), r.get('영상ID'), r.get('URL')] if x) or '출처 미기재'
                    leaf = self.atree.insert(t, 'end', text=f'[{r["id"]}] {(r.get("질문") or r.get("원문", "")).replace(chr(10), " ")[:60]}', values=(src,))
                    self.aitems[leaf] = ('row', kind, r, word)

    def analysis_detail(self, event=None):
        sel = self.atree.selection(); self.adetail.delete('1.0', 'end')
        if not sel or sel[0] not in self.aitems: return
        item = self.aitems[sel[0]]
        if item[0] == 'cat': self.adetail.insert('1.0', f'{item[1]}\n\n영상 아이디어 (추정 — 댓글에 직접 나온 요청 아님):\n{IDEAS.get(item[1], IDEAS[OTHER])}')
        elif item[0] == 'topic':
            items = analysis(self.store().all()).get(item[1], {}).get(item[2], [])
            if not items: return
            _, rep, _ = representative(items)
            self.adetail.insert('1.0', f'{item[1]} → {item[2]}  ({len(items)}건)\n\n대표 원문 [{rep["id"]}]:\n{rep.get("질문") or rep.get("원문", "")}\n\n'
                                f'묶인 기록: {", ".join(r["id"] for _, r, _ in items)}\n\n왼쪽 [+]를 펼친 뒤 원문을 두 번 누르면 입력 화면으로 이동합니다.')
        else:
            _, kind, r, word = item
            lines = [f'[{kind} {r["id"]}] 검토상태: {r.get("검토상태") or r.get("답변검토") or "미검토"}', '', '원문:', r.get('질문') or r.get('원문', ''), '',
                     f'출처: 플랫폼 {r.get("플랫폼") or "-"} / 영상 {r.get("영상ID") or "-"} / 댓글ID {r.get("댓글ID") or "-"} / {r.get("URL") or "-"}',
                     f'규칙 분류: {", ".join(f"{c}·{t}" for c, t, _ in classify_detail(r))}' + (f' (걸린 표현 "{word}")' if word else ''),
                     f'시청자가 직접 말한 해결 희망: {r.get("해결문제") or "없음"}', f'셰프 확인 메모: {r.get("직접확인") or "없음"}']
            self.adetail.insert('1.0', '\n'.join(lines))

    def selected_row(self):
        sel = self.atree.selection()
        item = self.aitems.get(sel[0]) if sel else None
        return item if item and item[0] == 'row' else None

    def open_selected_comment(self):
        item = self.selected_row()
        if item: self.open_record(item[1], item[2]['id'])

    def mark_reviewed(self):
        item = self.selected_row()
        if not item or item[1] != '댓글': self.notify('댓글 원문을 먼저 고르세요.'); return
        try:
            r = dict(item[2]); r['검토상태'] = '확인'; self.store().upsert('댓글', r); self.refresh_all(); self.tabs.select(self.t_analysis)
            self.notify(f'{r["id"]} 확인 처리했습니다.')
        except Exception as e: self.fail('확인 처리', e)

    # ---------- ③ 메뉴 선정 ----------
    def build_menu(self):
        bar = ttk.Frame(self.t_menu); bar.pack(fill='x', pady=(0, 6))
        ttk.Label(bar, text='요리권').pack(side='left'); self.cuisine = tk.StringVar(value='전체')
        cb = ttk.Combobox(bar, textvariable=self.cuisine, values=['전체', '한식', '일식', '지중해식', '기타'], state='readonly', width=9); cb.pack(side='left', padx=4)
        cb.bind('<<ComboboxSelected>>', lambda e: self.refresh_menu())
        for title, fn in [('새로고침', lambda: self.refresh_menu()), ('셰프 점수·최종판단 입력', self.edit_candidate), ('새 후보 추가', self.new_candidate), ('테마 밥상 추천', self.theme)]:
            ttk.Button(bar, text=title, command=fn).pack(side='left', padx=2)
        ttk.Label(bar, text='자동 점수 = 규칙 기반 추정 · 최종 메뉴는 셰프가 결정', foreground='#8A1C1C').pack(side='right')
        pan = ttk.Panedwindow(self.t_menu, orient='vertical'); pan.pack(fill='both', expand=True)
        cols = ('id', 'menu', 'cuisine', 'type', 'auto', 'chef', 'final')
        self.mtree = ttk.Treeview(pan, columns=cols, show='headings', height=8)
        for c, t, w in zip(cols, ['ID', '메뉴', '요리권', '유형', '자동(규칙)', '셰프 점수', '최종판단'], [60, 220, 90, 70, 130, 130, 90]): self.mtree.heading(c, text=t); self.mtree.column(c, width=w)
        pan.add(self.mtree, weight=1); self.mtree.bind('<<TreeviewSelect>>', self.menu_detail); self.mtree.bind('<Double-1>', lambda e: self.edit_candidate())
        self.mdetail = tk.Text(pan, wrap='word', font=FONT); pan.add(self.mdetail, weight=2)

    def refresh_menu(self, data=None):
        try: self.mdata = data or self.store().all()
        except Exception as e: self.fail('메뉴 선정', e); return
        self.mtree.delete(*self.mtree.get_children()); want = self.cuisine.get()
        for c in self.mdata['메뉴후보']:
            region = c['요리권'] if c['요리권'] in ('한식', '일식', '지중해식') else '기타'
            if want != '전체' and region != want: continue
            self.mtree.insert('', 'end', iid=c['id'], values=(c['id'], c['메뉴'], c['요리권'] or '미기재', c['콘텐츠유형'] or '미정',
                                                          score_summary(evaluate(c, self.mdata)), score_summary(chef_scores(c)), c['최종판단'] or '미정'))

    def menu_detail(self, event=None):
        sel = self.mtree.selection(); self.mdetail.delete('1.0', 'end')
        if not sel: return
        c = next(c for c in self.mdata['메뉴후보'] if c['id'] == sel[0]); auto = evaluate(c, self.mdata); chef = chef_scores(c)
        out = [f'{c["메뉴"]} [{c["id"]}] · {c["요리권"]} · {c["콘텐츠유형"] or "키/풀링 미정"} · 해결 문제: {c["해결문제"] or "확인 필요"}', '']
        for i, name in enumerate(CRITERIA):
            out.append(f'{i + 1}) {name}\n   자동(규칙): {auto[i][0]} — {auto[i][1]}\n   셰프: ' + (f'{chef[i][0]} — {chef[i][1]}' if chef else '미평가'))
        out.append(f'\n자동 합계 {score_summary(auto)} / 셰프 합계 {score_summary(chef)} / 최종 판단(셰프 입력): {c["최종판단"] or "미정"}')
        revs = linked_reviews(self.mdata, c)
        out.append('\n참고할 이전 회고:' + (''.join(f'\n - [{r["id"]}] {r["메뉴"]} ({r["유형"]}): 다음 변경 = {r["다음변경"] or "미기재"}' for r in revs) if revs else ' 없음'))
        self.mdetail.insert('1.0', '\n'.join(out))

    def edit_candidate(self):
        sel = self.mtree.selection()
        if sel: self.open_record('메뉴후보', sel[0]); self.notify('아래쪽 셰프점수·셰프이유·최종판단 칸을 채우고 [저장]을 누르세요.')

    def theme(self):
        try:
            b = simpledialog.askstring('테마 밥상 추천', '생년월일 YYYY-MM-DD (비워 두면 선택일 밥상만)', parent=self.win)
            if b is None: return
            mbti = simpledialog.askstring('테마 밥상 추천', '성격유형 네 글자 예: ISFJ (비워 두면 건너뜀)', parent=self.win)
            if mbti is None: return
            try: birth = dt.date.fromisoformat(b.strip()) if b.strip() else None
            except ValueError: raise UserError(f'생년월일 형식이 맞지 않습니다: {b}', '예: 1966-09-10')
            text = theme_report(self.store(), birth, mbti.strip() or None)
            dest = self.store().out / '테마밥상' / f'테마밥상_{datetime.now():%Y%m%d_%H%M%S}.md'
            dest.parent.mkdir(parents=True, exist_ok=True); dest.write_text(text, encoding='utf-8')
            self.mdetail.delete('1.0', 'end'); self.mdetail.insert('1.0', text); self.notify(f'재미·기획용 추천을 저장했습니다: {dest}')
        except Exception as e: self.fail('테마 밥상 추천', e)

    def new_candidate(self): self.kind.set('메뉴후보'); self.reload(); self.tabs.select(self.t_input)

    # ---------- ④ 콘텐츠 초안 ----------
    def build_draft(self):
        bar = ttk.Frame(self.t_draft); bar.pack(fill='x', pady=(0, 6))
        for title, fn in [('초안 만들기 / 다시 만들기', self.run), ('수정본 저장', self.save_output), ('새 생성본 보기', self.show_generated),
                          ('새 생성본으로 교체', self.adopt), ('변경 기록', self.show_history), ('결과 폴더 열기', lambda: self.open_path(self.store().out))]:
            ttk.Button(bar, text=title, command=fn).pack(side='left', padx=2)
        ttk.Label(self.t_draft, text='셰프확인된 조리 기록만 원본으로 씁니다. 다시 만들어도 셰프가 고친 파일은 덮어쓰지 않습니다. 대본은 완성 영상이 아닙니다.',
                  foreground='#8A1C1C', font=SMALL).pack(anchor='w')
        pan = ttk.Panedwindow(self.t_draft, orient='horizontal'); pan.pack(fill='both', expand=True)
        self.dlist = tk.Listbox(pan, font=FONT, width=38, activestyle='none', exportselection=False); pan.add(self.dlist, weight=1)
        self.dlist.bind('<<ListboxSelect>>', self.load_output)
        right = ttk.Frame(pan); pan.add(right, weight=4)
        self.dstate = tk.StringVar(); ttk.Label(right, textvariable=self.dstate, font=BOLD).pack(anchor='w')
        self.editor = tk.Text(right, wrap='word', font=('맑은 고딕', 12), undo=True); self.editor.pack(fill='both', expand=True)

    def drafts(self): return Drafts(self.store().out)

    def refresh_drafts(self, keep=None):
        try: d = self.drafts(); names = d.names()
        except Exception as e: self.fail('초안 목록', e); return
        self.dnames = names; self.dlist.delete(0, 'end')
        for n in names:
            st = d.status(n); self.dlist.insert('end', ('✎ ' if st.startswith('수정됨') else '   ') + n + (' ●' if '대기' in st else ''))
        target = keep if keep in names else (names[0] if names else None)
        if target: i = names.index(target); self.dlist.selection_clear(0, 'end'); self.dlist.selection_set(i); self.dlist.see(i); self.load_output(force=True)
        else:
            self.draft_name = None; self.editor.delete('1.0', 'end')
            self.editor.insert('1.0', '[초안 만들기]를 누르세요.\n셰프확인된 조리 기록이 있어야 대본·제목·쇼츠 등이 만들어집니다.'); self.dstate.set('')

    def load_output(self, event=None, force=False):
        sel = self.dlist.curselection()
        if not sel: return
        name = self.dnames[sel[0]]
        if not force and self.draft_name and name != self.draft_name and self.editor.edit_modified():
            if self.ask('저장 확인', f'{self.draft_name}에 저장하지 않은 수정이 있습니다. 저장할까요?'): self.save_output(refresh=False)
        self.draft_name = name; d = self.drafts()
        self.editor.delete('1.0', 'end'); self.editor.insert('1.0', d.path(name).read_text(encoding='utf-8')); self.editor.edit_modified(False)
        st = d.status(name); self.dstate.set(f'{name} · {st}' + (' — 셰프 수정본. 다시 만들어도 덮어쓰지 않습니다' if st.startswith('수정됨') else ''))

    def run(self):
        try:
            if self.draft_name and self.editor.edit_modified() and self.ask('저장 확인', '저장하지 않은 수정이 있습니다. 먼저 저장할까요?'): self.save_output(refresh=False)
            res = run_all(self.store()); self.refresh_all(); self.tabs.select(self.t_draft)
            made = sum(1 for a in res['actions'].values() if a in ('생성', '재생성 반영'))
            self.notify(f'초안 {made}개 생성·갱신 · 셰프 수정본 유지 {len(res["kept"])}개 · 미검토라 제외한 조리기록 {len(res["skipped"])}개 · 게시 안 함')
            return res
        except Exception as e: self.fail('초안 만들기', e)

    def save_output(self, refresh=True):
        if not self.draft_name: return
        try:
            self.drafts().save_user(self.draft_name, self.editor.get('1.0', 'end-1c')); self.editor.edit_modified(False)
            if refresh: self.refresh_drafts(keep=self.draft_name)
            self.notify('수정본을 저장했습니다. 이전 내용은 _기록/이전본에 보관했습니다.')
        except Exception as e: self.fail('저장 오류', e)

    def popup(self, title, text):
        top = tk.Toplevel(self.win); top.title(title); top.geometry('900x650')
        t = tk.Text(top, wrap='word', font=FONT); t.pack(fill='both', expand=True); t.insert('1.0', text); t.configure(state='disabled'); return t

    def show_generated(self):
        if not self.draft_name: return
        g = self.drafts().latest_generated(self.draft_name)
        if g: self.popup(f'최근 자동 생성본 — {self.draft_name} (읽기 전용)', g.read_text(encoding='utf-8'))
        else: self.notify('아직 자동 생성본이 없습니다.')

    def adopt(self):
        if not self.draft_name: return
        if not self.ask('교체 확인', f'{self.draft_name}을(를) 최근 자동 생성본으로 바꿀까요?\n지금 내용은 _기록/이전본에 보관됩니다.'): return
        try: self.drafts().adopt_generated(self.draft_name); self.refresh_drafts(keep=self.draft_name); self.notify('새 생성본으로 교체했습니다. 이전 수정본은 보관했습니다.')
        except Exception as e: self.fail('교체', e)

    def show_history(self):
        if not self.draft_name: return
        rows = self.drafts().history(self.draft_name)
        self.popup(f'변경 기록 — {self.draft_name}', '\n'.join(f'{r["시각"]}  {r["동작"]}  {r["근거"]}' for r in rows) or '기록 없음')

    # ---------- ⑤ 성과 회고·검색 ----------
    def build_search(self):
        bar = ttk.Frame(self.t_search); bar.pack(fill='x', pady=(0, 6))
        ttk.Label(bar, text='메뉴·불편·ID 검색').pack(side='left')
        self.query = ttk.Entry(bar, width=40, font=FONT); self.query.pack(side='left', padx=4); self.query.bind('<Return>', lambda e: self.search())
        self.only_review = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text='회고만', variable=self.only_review).pack(side='left')
        for title, fn in [('검색', self.search), ('성과 회고 초안 보기', self.open_retro), ('회고 입력', lambda: self.open_kind('회고')), ('영상 성과 입력', lambda: self.open_kind('영상성과'))]:
            ttk.Button(bar, text=title, command=fn).pack(side='left', padx=2)
        ttk.Label(self.t_search, text='다음 메뉴를 기획할 때 메뉴 이름이나 불편(예: 질김)으로 이전 회고를 찾아보세요. 같은 플랫폼·같은 게시 후 시간끼리만 비교합니다.', font=SMALL).pack(anchor='w')
        self.results = tk.Text(self.t_search, wrap='word', font=FONT); self.results.pack(fill='both', expand=True)

    def open_kind(self, kind): self.kind.set(kind); self.reload(); self.tabs.select(self.t_input)

    def search(self):
        q = self.query.get().strip()
        if not q: return
        try:
            hits = [(k, r) for k, r in self.store().search(q) if not self.only_review.get() or k == '회고']
            hits.sort(key=lambda kr: kr[0] != '회고'); self.results.delete('1.0', 'end')
            for kind, r in hits:
                head = f'[{kind} / {r["id"]}]' + (f'  ▶ 다음 변경: {r["다음변경"]}' if kind == '회고' and r.get('다음변경') else '')
                self.results.insert('end', head + '\n' + '\n'.join(f'  {k}: {v}' for k, v in r.items() if v and k not in ('구분',)) + '\n\n')
            self.notify(f'"{q}" {len(hits)}건 · 원문이 들어 있으니 외부 공유 전 개인정보를 확인하세요.')
        except Exception as e: self.fail('검색 오류', e)

    def open_retro(self):
        self.refresh_drafts(keep='05_성과회고.md'); self.tabs.select(self.t_draft)
        if self.draft_name != '05_성과회고.md': self.notify('[초안 만들기]를 먼저 눌러 주세요.')

    # ---------- 백업·도움말 ----------
    def build_help(self):
        bar = ttk.Frame(self.t_help); bar.pack(fill='x', pady=(0, 6))
        for title, fn in [('지금 백업', self.backup), ('백업에서 복원', self.restore), ('백업 폴더 열기', lambda: self.open_path(self.out_root / '백업')),
                          ('결과 폴더 열기', lambda: self.open_path(self.store().out)), ('입력 자료 폴더 열기', lambda: self.open_path(self.store().folder)),
                          ('사용 설명서(README)', lambda: self.open_path(self.folder / 'README.md'))]:
            ttk.Button(bar, text=title, command=fn).pack(side='left', padx=2)
        self.helptext = tk.Text(self.t_help, wrap='word', font=FONT); self.helptext.pack(fill='both', expand=True)
        self.helptext.insert('1.0', f'''처음 쓰는 순서
1. 오른쪽 위를 [예시 연습]으로 두고 [④ 콘텐츠 초안] → [초안 만들기]를 눌러 결과를 구경합니다.
2. 실제로 시작할 때 오른쪽 위를 [실제 운영]으로 바꿉니다. 예시와 실제 자료는 따로 저장됩니다.
3. 위쪽 여섯 단계 버튼이 지금 단계와 부족한 자료를 알려 줍니다. 노란 버튼이 지금 할 일입니다.

실제 자료 넣는 곳
- [① 자료 입력] → 자료 종류를 고르고 [새 기록] → 칸 채우기 → [저장]. 칸마다 설명과 예시가 있습니다.
- 여러 건은 Excel로 templates 폴더의 "_실제입력.csv"를 복사해 채운 뒤 [CSV 가져오기].
- 조리 테스트는 셰프가 확인한 뒤 검토상태를 "셰프확인"으로 바꿔야 콘텐츠 초안에 쓰입니다.
- 최종 메뉴는 메뉴후보의 [최종판단] 칸에 셰프가 "선택"을 직접 넣습니다. 앱이 정하지 않습니다.

결과 위치
- {self.out_root}\\예시 또는 \\실제
  초안: 초안 폴더 / 이전 버전·자동 생성본·변경기록: 초안\\_기록 / 실행 기록: 실행기록 / 내보낸 CSV: 내보내기

백업과 복원
- [지금 백업]: 현재 모드의 입력 자료와 초안을 zip 하나로 저장합니다 ({self.out_root}\\백업).
- [백업에서 복원]: zip을 고르면 먼저 내용을 검사하고, 지금 자료를 자동 백업한 뒤 입력 자료를 되돌립니다. 초안 파일은 zip 안에 남아 있어 필요한 것만 꺼내 쓰면 됩니다.
- 입력을 저장할 때마다 이전 CSV가 앱 폴더의 backups에 자동 보관됩니다.
- 앱 폴더 전체를 USB나 드라이브에 복사해 두는 것도 좋은 백업입니다. 다만 data\\actual과 backups에는 원문이 있으니 공유하지 마세요.

오류가 날 때
- 오류 창에 원인과 해결 방법이 함께 나옵니다. 대부분 "Excel에서 파일이 열려 있음", "날짜 형식", "예시·실제 섞임"입니다.
- 오류 내용은 {self.out_root}\\오류기록.txt에도 남습니다.

이 버전이 하지 않는 것
- 유튜브·인스타 게시, 댓글 답글, DM, 알림톡 발송, 상품 정보 변경, 외부 AI 호출. 로그인·API 연결도 없습니다.''')
        self.helptext.configure(state='disabled')

    def backup(self):
        try: p = self.store().backup_zip(); self.notify(f'백업했습니다: {p}'); return p
        except Exception as e: self.fail('백업', e)

    def restore(self, path=None, confirm=True):
        path = path or filedialog.askopenfilename(title='복원할 백업 zip 고르기', initialdir=self.out_root / '백업', filetypes=[('zip', '*.zip')])
        if not path: return
        if confirm and not self.ask('복원 확인', f'{self.mode.get()} 입력 자료를 이 백업으로 되돌릴까요?\n지금 자료는 먼저 자동 백업합니다.'): return
        try: before = self.store().restore_zip(path); self.refresh_all(); self.notify(f'복원했습니다. 복원 전 자료 백업: {before}'); return before
        except Exception as e: self.fail('복원하지 못했습니다', e)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--run', choices=['example', 'actual']); parser.add_argument('--out')
    args = parser.parse_args(); initialize(ROOT)
    if args.run:
        res = run_all(Store(ROOT, args.run, args.out))
        print('초안 폴더:', res['folder']); [print(f'  {n}: {a}') for n, a in res['actions'].items()]
        if res['skipped']: print('셰프 미검토라 초안을 만들지 않은 조리테스트:', ', '.join(res['skipped']))
    else:
        window = tk.Tk(); App(window, out_root=args.out); window.mainloop()
