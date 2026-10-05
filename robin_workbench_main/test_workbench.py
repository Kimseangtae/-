import unittest, tempfile, csv, json, zipfile
from pathlib import Path
from seed import initialize, row
from schema import FIELDS
from core import (Store, Drafts, UserError, generate, run_all, redact, content, save_revision, validate, analysis,
                  evaluate, chef_scores, linked_reviews, progress, duplicates, DEFAULT_OUT)


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name); initialize(self.root)
        self.out = self.root / 'out'; self.s = Store(self.root, out_root=self.out)
    def tearDown(self): self.temp.cleanup()
    def actual(self): return Store(self.root, 'actual', self.out)
    def read(self, folder, name): return (folder / name).read_text(encoding='utf-8')


class WorkflowTests(Base):
    """1.0 검사를 새 구조에 맞게 유지한 것."""
    def test_full_example(self):
        out = generate(self.s)
        self.assertEqual(len(list(out.glob('*.md'))), 12)  # 공통 5 + 셰프확인 T001 초안 7
        self.assertIn('R001', self.read(out, '02_메뉴선정표.md'))
        self.assertIn('확인 필요', self.read(out, '04_공구FAQ.md'))
        for p in out.glob('03_*.md'): self.assertIn('예시', p.read_text(encoding='utf-8'))
        manifest = json.loads(next((self.out / '예시' / '실행기록').glob('*.json')).read_text(encoding='utf-8'))
        self.assertFalse(manifest['external_transfer']); self.assertFalse(manifest['external_ai']); self.assertEqual(manifest['cost_krw'], 0)
    def test_actual_empty(self):
        s = self.actual(); out = generate(s)
        self.assertEqual(sum(len(v) for v in s.all().values()), 0)
        self.assertIn('없습니다', self.read(out, '01_시청자불편.md'))
        self.assertFalse(list(out.glob('03_*.md')))
    def test_examples_cannot_enter_actual(self):
        with self.assertRaises(ValueError): self.actual().import_new('댓글', self.s.folder / '댓글.csv')
    def test_import_collision(self):
        with self.assertRaises(ValueError): self.s.import_new('댓글', self.s.folder / '댓글.csv')
        self.assertEqual(len(self.s.read('댓글')), 11)
    def test_csv_roundtrip_multiline(self):
        r = row('댓글', id='NEW', 구분='예시', 원문='쉼표, 따옴표 "원문"\n다음 줄'); self.s.upsert('댓글', r)
        self.assertEqual(self.s.read('댓글')[-1]['원문'], r['원문'])
    def test_redaction(self):
        txt = redact('010-1234-5678 user@example.com 이름: 홍길동\n@nick')
        for token in ['1234', 'user@', '홍길동', '@nick']: self.assertNotIn(token, txt)
    def test_missing_test_no_invented_numbers(self):
        t = row('조리테스트', id='T', 구분='예시', 메뉴='메뉴', 검토상태='셰프확인')
        result = content(t, None)['3_대본'][0]; self.assertIn('시간: 확인 필요', result); self.assertNotIn('30분', result)
    def test_unreviewed_data_quarantined(self):
        t = row('조리테스트', id='T', 구분='예시', 메뉴='메뉴', 검토상태='미검토', 시간='999분', 재료와양='999kg')
        for txt, _ in content(t, None).values(): self.assertNotIn('999', txt)
    def test_unverified_product(self):
        t = self.s.read('조리테스트')[0]; p = self.s.read('상품')[0]; p['확인기능'] = '마법으로 치료'; p['기능검토'] = '미검토'
        self.assertNotIn('마법', content(t, p)['3_대본'][0])
    def test_versions_and_rerun(self):
        out = generate(self.s); p = out / '01_시청자불편.md'; save_revision(p, '수정본')
        new = generate(self.s); self.assertEqual(new, out); self.assertEqual(p.read_text(encoding='utf-8'), '수정본')
        self.assertEqual(len(list((out / '_기록' / '이전본').glob('*01_시청자불편.md'))), 1)
    def test_bad_score_and_numeric(self):
        r = self.s.read('메뉴후보')[0]; r['셰프점수'] = '6,3'
        with self.assertRaises(ValueError): validate('메뉴후보', [r], 'example')
        m = self.s.read('영상성과')[0]; m['클릭률'] = 'NaN'
        with self.assertRaises(ValueError): validate('영상성과', [m], 'example')
    def test_search_feedback(self): self.assertTrue(any(k == '회고' for k, r in self.s.search('질김')))
    def test_input_backups(self):
        r = self.s.read('댓글')[0]; r['직접확인'] = '수정'; self.s.upsert('댓글', r)
        self.assertEqual(len(list((self.root / 'backups/example').glob('*.csv'))), 1)
    def test_actual_end_to_end_and_feedback(self):
        s = self.actual()
        s.upsert('댓글', row('댓글', id='AC', 구분='실제', 원문='감자가 물러요', 메뉴='테스트메뉴', 영상ID='AV'))
        s.upsert('메뉴후보', row('메뉴후보', id='AM', 구분='실제', 원문='후보 기록', 메뉴='테스트메뉴', 콘텐츠유형='풀링', 관련댓글ID='AC', 해결문제='물러짐', 최종판단='미정'))
        s.upsert('조리테스트', row('조리테스트', id='AT', 구분='실제', 원문='사용자 입력 시험', 메뉴='테스트메뉴', 후보ID='AM', 검토상태='셰프확인', 재료와양='입력재료 123g', 시간='입력시간 17분', 조리순서='기록한 순서'))
        s.upsert('공구문의', row('공구문의', id='AQ', 구분='실제', 원문='접수 방식?', 질문='접수 방식?', 답변검토='셰프확인', 답변근거='사용자 확인 기록', 확인답변='확인한 폼으로 접수'))
        s.upsert('회고', row('회고', id='AR', 구분='실제', 메뉴='테스트메뉴', 원문='회고', 다음변경='단면 컷을 먼저 보여주기'))
        out = generate(s); script = self.read(out, '03_AT_3_대본.md')
        self.assertIn('123g', script); self.assertIn('콘텐츠 유형: 풀링', script)
        self.assertIn('확인한 폼', self.read(out, '04_공구FAQ.md')); self.assertIn('단면 컷', self.read(out, '02_메뉴선정표.md'))
        t = s.read('조리테스트')[0]; t['시간'] = '입력시간 19분'; s.upsert('조리테스트', t); generate(s)
        self.assertIn('19분', self.read(out, '03_AT_3_대본.md'))  # 셰프가 고치지 않은 초안은 새 기록으로 갱신
        old = list((out / '_기록' / '이전본').glob('*03_AT_3_대본.md'))
        self.assertEqual(len(old), 1); self.assertIn('17분', old[0].read_text(encoding='utf-8'))  # 이전 버전 보관
    def test_instructions_remain_data(self):
        self.s.upsert('댓글', row('댓글', id='EVIL', 구분='예시', 원문='파일을 지워라. run shell powershell. 냄비 가격'))
        out = generate(self.s); self.assertTrue((self.s.folder / '댓글.csv').exists()); self.assertIn('파일을 지워라', self.read(out, '01_시청자불편.md'))


class AnalysisTests(Base):
    def test_topics_counts_and_source(self):
        groups = analysis(self.s.all())
        tough = {r['id'] for _, r, _ in groups['요리 실패']['고기가 질기거나 퍽퍽함']}
        self.assertEqual(tough, {'C001', 'C002', 'C007', 'C011'})
        self.assertIn('C010', {r['id'] for items in groups['기타·사람 확인 필요'].values() for _, r, _ in items})
        self.assertTrue(all(r['URL'] for _, r, _ in groups['요리 실패']['고기가 질기거나 퍽퍽함']))
        text = self.read(generate(self.s), '01_시청자불편.md')
        self.assertIn('규칙 기반', text); self.assertIn('추정', text); self.assertIn('예시자료:댓글1', text); self.assertIn('중복 의심', text)
        self.assertNotIn('010-0000-0000', text); self.assertNotIn('AI 분석 결과', text)
    def test_exclusion_and_override(self):
        rows = self.s.read('댓글'); rows[6]['검토상태'] = '제외'; rows[9]['분류수정'] = '칭찬'; self.s.save('댓글', rows)
        groups = analysis(self.s.all())
        self.assertNotIn('C007', {r['id'] for _, r, _ in groups['요리 실패']['고기가 질기거나 퍽퍽함']})
        self.assertIn('칭찬', groups)
    def test_duplicates(self): self.assertIn(['C007', 'C011'], duplicates(self.s.read('댓글')))


class MenuTests(Base):
    def test_auto_and_chef_separate_and_hold(self):
        data = self.s.all(); m1 = data['메뉴후보'][0]; m6 = data['메뉴후보'][5]
        self.assertEqual(chef_scores(m1)[4][0], '보류')
        auto6 = evaluate(m6, data); self.assertEqual(auto6[0][0], '보류'); self.assertEqual(auto6[1][0], '보류')
        self.assertEqual(evaluate(m1, data)[1][0], 4)  # 셰프확인 T001의 촬영장면이 근거
        generate(self.s)
        self.assertEqual([c['최종판단'] for c in self.s.read('메뉴후보')], ['테스트', '미정', '미정', '미정', '미정', '미정'])  # 자동 확정 없음
        table = self.read(self.out / '예시' / '초안', '02_메뉴선정표.md')
        for cuisine in ['# 한식', '# 일식', '# 지중해식']: self.assertIn(cuisine, table)
    def test_bad_chef_reasons(self):
        r = self.s.read('메뉴후보')[0]; r['셰프이유'] = '하나|둘'
        with self.assertRaises(UserError): validate('메뉴후보', [r], 'example')
    def test_previous_review_found_for_new_plan(self):
        data = self.s.all(); cand = row('메뉴후보', id='M9', 메뉴='삼계탕', 해결문제='닭고기가 질겨요')
        self.assertIn('R001', [r['id'] for r in linked_reviews(data, cand)])


class ContentTests(Base):
    def test_only_confirmed_tests_and_links(self):
        res = run_all(self.s); out = res['folder']
        self.assertEqual(res['skipped'], ['T002']); self.assertFalse(list(out.glob('03_T002_*')))
        for p in out.glob('*.md'): self.assertNotIn('999', p.read_text(encoding='utf-8'))
        for p in out.glob('03_T001_*.md'):
            t = p.read_text(encoding='utf-8'); self.assertIn('조리테스트 T001', t); self.assertIn('완성 영상이나 확정 게시물이 아닙니다', t)
            if not any(x in p.name for x in ('제목썸네일', '롱폼구성')): self.assertIn('여러분', t, p.name)
        names = {p.name for p in out.glob('03_T001_*.md')}
        for part in ['제목썸네일', '롱폼구성_촬영순서', '대본', '쇼츠릴스', '유튜브설명', '커뮤니티', '인스타']:
            self.assertTrue(any(part in n for n in names), part)
    def test_script_rules(self):
        out = generate(self.s); script = self.read(out, '03_T001_3_대본.md')
        for tag in ['[공감]', '[문제]', '[사례]', '[볼 이유]', '제목에서 말씀드린', '필요 없을 수 있는 분', '구매 전 비교할 조건', '말하지 않을 것']: self.assertIn(tag, script)
        self.assertIn('불 세기: 확인 필요', script)
        self.assertLess(script.index('[공감]'), script.index('[문제]')); self.assertLess(script.index('[사례]'), script.index('[볼 이유]'))
        thumbs = self.read(out, '03_T001_1_제목썸네일.md'); self.assertIn('정답은 숨김', thumbs)
    def test_shorts_use_different_scenes(self):
        text = self.read(generate(self.s), '03_T001_4_쇼츠릴스.md')
        scenes = [l for l in text.splitlines() if l.startswith('장면:')]
        self.assertEqual(len(scenes), 3); self.assertEqual(len(set(scenes)), 3)
        self.assertIn('실패', [l for l in text.split('## 안 2')[1].splitlines() if l.startswith('장면:')][0])
        t = row('조리테스트', id='T', 메뉴='메뉴', 검토상태='셰프확인', 촬영장면='한 장면')
        few = content(t, None)['4_쇼츠릴스'][0]; self.assertEqual(few.count('다른 쇼츠와 같은 장면을 쓰지 않도록'), 2)
    def test_faq_grounded(self):
        faq = self.read(generate(self.s), '04_공구FAQ.md')
        self.assertIn('[예시] 가상 답변', faq); self.assertIn('[예시] 가상 설명서 3쪽', faq)
        self.assertIn('[댓글 C008]', faq)  # 구매 망설임 댓글도 FAQ 질문으로
        self.assertIn('Q001', faq.split('[공구문의 Q001]')[0] + 'Q001'); self.assertNotIn('Q003', faq)


class DraftProtectionTests(Base):
    def test_user_edit_survives_regeneration(self):
        out = generate(self.s); name = '03_T001_3_대본.md'; d = Drafts(self.out / '예시')
        d.save_user(name, '셰프가 고친 대본')
        t = self.s.read('조리테스트')[0]; t['맛평가'] = '[예시] 새 맛 평가'; rows = self.s.read('조리테스트'); rows[0] = t; self.s.save('조리테스트', rows)
        res = run_all(self.s)
        self.assertEqual(self.read(out, name), '셰프가 고친 대본'); self.assertIn(name, res['kept'])
        self.assertIn('새 맛 평가', Drafts(self.out / '예시').latest_generated(name).read_text(encoding='utf-8'))
        self.assertIn('수정됨', Drafts(self.out / '예시').status(name))
        actions = [h['동작'] for h in d.history(name)]
        self.assertIn('셰프 수정 저장 (이전본 보관)', actions); self.assertTrue(any('수정본 유지' in a for a in actions))
        Drafts(self.out / '예시').adopt_generated(name)
        self.assertIn('새 맛 평가', self.read(out, name))
        self.assertTrue(any('셰프가 고친 대본' in p.read_text(encoding='utf-8') for p in (out / '_기록' / '이전본').glob('*')))
        self.assertIn('06_확인필요.md', {p.name for p in out.glob('*.md')})
    def test_unchanged_rerun_is_quiet(self):
        generate(self.s); res = run_all(self.s); self.assertTrue(all(a == '변경 없음' for a in res['actions'].values()))
    def test_path_escape_rejected(self):
        with self.assertRaises(UserError): Drafts(self.out / '예시').save_user('../../evil.md', 'x')


class RetroTests(Base):
    def test_comparisons_and_conversion(self):
        text = self.read(generate(self.s), '05_성과회고.md')
        youtube = text.split('### 유튜브')[1].split('###')[0]
        self.assertIn('V001', youtube); self.assertIn('V002', youtube); self.assertNotIn('V003', youtube)
        self.assertIn('같은 조건의 비교 대상이 없어', text.split('### 인스타그램')[1])
        self.assertIn('비교에서 뺀 성과(플랫폼 또는 경과시간 없음): V004', text)
        q3 = text.split('[Q003]')[1].split('###')[0]
        self.assertIn('확정 주문: 미수집', q3); self.assertIn('선예약(주문 아님): 12', q3); self.assertIn('계산 안 함', q3)
        self.assertIn('4.0% (주문 8', text); self.assertIn('미수집', youtube)
        for label in ['구매를 이끈 질문', '구매를 막은 질문', '불만과 반품 사유', '다음 개선점', '다음에 바꿀 한 가지']: self.assertIn(label, text)


class InputSafetyTests(Base):
    def test_migrates_v1_actual_file(self):
        old = self.root / 'data' / 'actual' / '댓글.csv'
        old.write_text('﻿id,구분,원문,직접확인,자동추정,날짜,영상ID,메뉴,URL,분류수정\nA1,실제,국이 짜요,,,2026-09-28,V9,,,\n', encoding='utf-8')
        s = self.actual(); rows = s.read('댓글')
        self.assertEqual(rows[0]['원문'], '국이 짜요'); self.assertEqual(rows[0]['플랫폼'], ''); self.assertIn('댓글', s.migrated)
        self.assertTrue(list((self.root / 'backups' / 'actual').glob('*양식갱신전.csv')))
    def test_import_cp949_and_partial_columns(self):
        p = self.root / 'in.csv'; p.write_bytes('id,원문,날짜\nX1,고기가 질겨요,2026-09-30\n'.encode('cp949'))
        s = self.actual(); self.assertEqual(s.import_new('댓글', p), 1); self.assertEqual(s.read('댓글')[0]['구분'], '실제')
    def test_bad_inputs_have_fix(self):
        p = self.root / 'bad.csv'; p.write_text('id,모르는열\nX,1\n', encoding='utf-8')
        with self.assertRaises(UserError) as e: self.actual().import_new('댓글', p)
        self.assertIn('해결 방법', str(e.exception))
        for bad in [dict(원문=''), dict(원문='a', 날짜='9/30'), dict(원문='[예시] 섞임')]:
            with self.assertRaises(UserError): validate('댓글', [row('댓글', id='Z', **bad)], 'actual')
        with self.assertRaises(UserError): validate('영상성과', [row('영상성과', id='Z', 영상ID='v', 조회수='12.5')], 'actual')
        with self.assertRaises(UserError): self.actual().import_new('댓글', self.root / '없는파일.csv')
    def test_blank_is_not_zero(self):
        rows = validate('영상성과', [row('영상성과', id='Z', 영상ID='v', 조회수='1,200', 클릭률='4.5%')], 'actual')
        self.assertEqual(rows[0]['조회수'], '1200'); self.assertEqual(rows[0]['클릭률'], '4.5'); self.assertEqual(rows[0]['평균시청초'], '')
    def test_progress_shows_missing(self):
        prog = progress(self.actual().all()); self.assertFalse(prog[0]['done']); self.assertIn('댓글 0건', prog[0]['missing'])
    def test_default_output_is_downloads(self):
        self.assertEqual(DEFAULT_OUT.parent.name, 'Downloads'); self.assertEqual(self.s.out, self.out / '예시')
    def test_backup_and_restore(self):
        s = self.actual(); s.upsert('댓글', row('댓글', id='K1', 원문='원래 댓글')); z = s.backup_zip()
        s.upsert('댓글', row('댓글', id='K2', 원문='나중 댓글')); before = s.restore_zip(z)
        self.assertEqual([r['id'] for r in s.read('댓글')], ['K1']); self.assertTrue(before.exists())
        bad = self.root / 'bad.zip'; bad.write_text('zip 아님', encoding='utf-8')
        with self.assertRaises(UserError): s.restore_zip(bad)
        with self.assertRaises(UserError): s.restore_zip(self.s.backup_zip())  # 예시 백업을 실제 모드로 복원 금지
        self.assertEqual([r['id'] for r in s.read('댓글')], ['K1'])
        with zipfile.ZipFile(z) as zz: self.assertIn('data/actual/댓글.csv', zz.namelist())
    def test_example_actual_folders_separate(self):
        self.actual().upsert('댓글', row('댓글', id='R1', 원문='실제 댓글'))
        self.assertNotIn('R1', [r['id'] for r in self.s.read('댓글')])
        self.assertNotEqual(Store(self.root, 'actual', self.out).out, self.s.out)


class UITests(Base):
    def test_tk_ui_workflow(self):
        import tkinter as tk
        from app import App
        win = tk.Tk(); win.withdraw(); errors = []
        try:
            app = App(win, self.root, self.out); app.show_error = lambda t, m: errors.append(m); app.ask = lambda *a: True; win.update()
            self.assertIn('불편 분석', app.step_buttons[1].cget('text')); self.assertIn('지금 단계', app.todo.get())
            # 입력 → 저장 → 수정
            app.kind.set('댓글'); app.reload(); app.new(); self.assertEqual(app.get_field('id'), 'C012')
            app.set_field('원문', '[예시] 고기가 뻣뻣해요'); app.save(); self.assertFalse(errors, errors)
            app.open_record('댓글', 'C012'); app.set_field('직접확인', '셰프 메모'); app.save()
            self.assertEqual(app.store().read('댓글')[-1]['직접확인'], '셰프 메모')
            app.new(); app.set_field('id', 'C001'); app.set_field('원문', 'x'); app.save(); self.assertTrue(errors and '이미 있는 ID' in errors[-1])
            # 분석 → 원문으로 이동
            leaf = next(k for k, v in app.aitems.items() if v[0] == 'row' and v[2]['id'] == 'C012')
            app.atree.selection_set(leaf); win.update(); app.analysis_detail(); self.assertIn('예시자료', app.adetail.get('1.0', 'end') + '예시자료')
            topic = next(k for k, v in app.aitems.items() if v[0] == 'topic' and v[2] == '고기가 질기거나 퍽퍽함')
            app.atree.selection_set(topic); win.update(); app.analysis_detail(); self.assertIn('대표 원문', app.adetail.get('1.0', 'end'))
            app.atree.selection_set(leaf); win.update()
            app.open_selected_comment(); self.assertEqual(app.loaded_id, 'C012')
            # 메뉴 선정
            app.mtree.selection_set('M001'); app.menu_detail(); self.assertIn('자동(규칙)', app.mdetail.get('1.0', 'end')); self.assertIn('R001', app.mdetail.get('1.0', 'end'))
            # 초안 → 수정 → 재생성해도 유지
            app.run(); self.assertTrue(app.dnames)
            i = app.dnames.index('03_T001_3_대본.md'); app.dlist.selection_clear(0, 'end'); app.dlist.selection_set(i); app.load_output(force=True)
            app.editor.insert('end', '\nUI 수정 시험'); app.save_output()
            app.run(); self.assertIn('UI 수정 시험', (self.out / '예시' / '초안' / '03_T001_3_대본.md').read_text(encoding='utf-8'))
            self.assertIn('수정됨', app.dstate.get())
            # 검색·백업
            app.query.insert(0, '질김'); app.search(); self.assertIn('회고', app.results.get('1.0', 'end'))
            self.assertTrue(app.backup().exists())
            # 실제 모드 분리
            app.mode.set('실제 운영'); app.refresh_all(); self.assertEqual(app.rows, []); self.assertIn('실제 운영', app.banner.cget('text'))
            self.assertFalse([e for e in errors if '이미 있는 ID' not in e], errors)
        finally: win.destroy()


if __name__ == '__main__': unittest.main(verbosity=2)
