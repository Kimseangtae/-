"""로빈 작업실 핵심 기능. 외부 연결 없음 — 규칙 기반 분류와 서식 기반 초안만 만든다."""
from pathlib import Path
import csv, io, json, re, hashlib, shutil, zipfile, math
from datetime import datetime
from collections import defaultdict
import theme_menu as tm
from schema import (FIELDS, ENUMS, REQUIRED, TOPICS, OTHER, IDEAS, CRITERIA, ID_PREFIX,
                    INTEGERS, NUMBERS, DATES, VERSION)

MODES = {'example': '예시', 'actual': '실제'}
MODE_TITLE = {'example': '예시 연습', 'actual': '실제 운영'}
DEFAULT_OUT = Path.home() / 'Downloads' / '로빈_작업실_결과'
NEEDS = '확인 필요'


class UserError(ValueError):
    """원인과 해결 방법을 함께 보여 주는 입력 오류."""
    def __init__(self, cause, fix=''):
        super().__init__(cause + (f'\n\n해결 방법: {fix}' if fix else ''))


def stamp(): return datetime.now().strftime('%Y%m%d_%H%M%S_%f')
def sha(text): return hashlib.sha256(text.encode('utf-8')).hexdigest()


def redact(value):
    s = str(value or '')
    s = re.sub(r'(?<!\d)(?:\+82[- .]?)?0?1[016789][- .]?\d{3,4}[- .]?\d{4}(?!\d)', '[연락처 가림]', s)
    s = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[이메일 가림]', s)
    s = re.sub(r'\b\d{6}[- ]?[1-8]\d{6}\b', '[식별번호 가림]', s)
    s = re.sub(r'@[\w가-힣.]+', '[닉네임 가림]', s)
    s = re.sub(r'(이름|성함|주소|계좌)\s*[:：]\s*[^\n,;]+', r'\1: [가림]', s)
    return s


# ---------- CSV 읽기·쓰기 ----------

def write_csv(path, kind, rows):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    try:
        with tmp.open('w', encoding='utf-8-sig', newline='') as f:
            w = csv.DictWriter(f, fieldnames=list(FIELDS[kind])); w.writeheader()
            w.writerows({k: r.get(k, '') for k in FIELDS[kind]} for r in rows)
        tmp.replace(path)
    except PermissionError:
        raise UserError(f'{path.name} 파일에 저장할 수 없습니다.', 'Excel 등 다른 프로그램에서 이 파일을 열어 두었다면 닫고 다시 저장하세요.')


def load_csv(path, kind):
    """양식 열이 일부 빠진 이전 버전 CSV도 받아들인다. 모르는 열은 거부한다."""
    path = Path(path)
    try: raw = path.read_bytes()
    except FileNotFoundError: raise UserError(f'파일을 찾을 수 없습니다: {path}', '파일 위치를 다시 선택하세요.')
    except PermissionError: raise UserError(f'파일을 열 수 없습니다: {path.name}', '다른 프로그램에서 열려 있으면 닫고 다시 시도하세요.')
    for enc in ('utf-8-sig', 'cp949'):
        try: text = raw.decode(enc); break
        except UnicodeDecodeError: continue
    else:
        raise UserError('CSV 글자 인코딩을 읽을 수 없습니다.', 'Excel에서 [다른 이름으로 저장] → "CSV UTF-8(쉼표로 분리)"로 저장하세요.')
    reader = csv.DictReader(io.StringIO(text, newline=''))
    names = [n.strip() for n in (reader.fieldnames or [])]
    if not names: raise UserError(f'{path.name}: 빈 파일입니다.', 'templates 폴더의 양식을 복사해 첫 줄(열 이름)을 유지하세요.')
    unknown = [n for n in names if n not in FIELDS[kind]]
    if unknown or 'id' not in names or len(set(names)) != len(names):
        raise UserError(f'{kind} 양식과 열 이름이 다릅니다. 모르는 열: {", ".join(unknown) or "없음"}',
                        f'[{kind}]을(를) 고른 것이 맞는지 확인하고, templates\\{kind}_실제입력.csv 양식을 사용하세요.')
    rows = []
    for i, r in enumerate(reader, 2):
        if None in r or any(v is None for v in r.values()):
            raise UserError(f'{kind} {i}행: 열 개수가 맞지 않습니다.', '쉼표가 들어간 글은 따옴표로 감싸거나 Excel에서 저장하세요.')
        clean = {k: '' for k in FIELDS[kind]}
        for k, v in zip(names, r.values()): clean[k] = v.strip() if k != '원문' else v
        if any(clean.values()): rows.append(clean)
    return rows, names != list(FIELDS[kind])


def _num(value, key, where, integer):
    s = value.replace(',', '').replace('%', '').strip()
    try: n = float(s)
    except ValueError: raise UserError(f'{where}: {key}는 숫자 또는 공란이어야 합니다 (입력값: {value}).', '모르면 0이 아니라 공란으로 두세요.')
    if not math.isfinite(n) or n < 0: raise UserError(f'{where}: {key} 값 범위 오류 ({value}).', '0 이상 숫자를 넣으세요.')
    if key == '클릭률' and n > 100: raise UserError(f'{where}: 클릭률은 0~100 사이입니다.', '%단위 숫자만 넣으세요. 예: 4.2')
    if integer and n != int(n): raise UserError(f'{where}: {key}는 정수여야 합니다.', '소수점 없이 입력하세요.')
    return str(int(n)) if integer else s


def validate(kind, rows, mode):
    label = MODES[mode]; ids = set()
    for i, r in enumerate(rows, 2):
        where = f'{kind} {i}행({r.get("id") or "id 없음"})'
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,60}', r.get('id', '')):
            raise UserError(f'{where}: id는 영문·숫자·밑줄·하이픈 1~60자입니다.', '[새 기록] 버튼을 누르면 자동 id가 채워집니다.')
        if r['id'] in ids: raise UserError(f'{kind}: 중복 id {r["id"]}', '다른 id로 바꾸거나 기존 기록을 수정하세요.')
        ids.add(r['id'])
        if not r.get('구분'): r['구분'] = label
        if r['구분'] != label or (mode == 'actual' and r.get('원문', '').lstrip().startswith('[예시]')):
            raise UserError(f'{where}: 예시 자료와 실제 자료는 섞을 수 없습니다.', '예시 행을 지우거나 오른쪽 위 모드를 확인하세요.')
        for group in REQUIRED[kind]:
            if not any(r.get(k, '').strip() for k in group):
                raise UserError(f'{where}: {" 또는 ".join(group)} 칸이 비어 있습니다.', '필수 칸을 채운 뒤 저장하세요.')
        for key in DATES:
            if r.get(key):
                try: datetime.strptime(r[key], '%Y-%m-%d')
                except ValueError: raise UserError(f'{where}: {key}는 YYYY-MM-DD 형식입니다 (입력값: {r[key]}).', '예: 2026-09-30')
        if r.get('확인시각'):
            for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d'):
                try: datetime.strptime(r['확인시각'], fmt); break
                except ValueError: pass
            else: raise UserError(f'{where}: 확인시각은 YYYY-MM-DD HH:MM 형식입니다.', '예: 2026-09-30 21:00')
        for (k2, key), allowed in ENUMS.items():
            if k2 == kind and r.get(key) and r[key] not in allowed:
                raise UserError(f'{where}: {key}에 "{r[key]}"는 쓸 수 없습니다.', ' / '.join(allowed) + ' 중 하나를 입력하세요.')
        for key in INTEGERS + NUMBERS:
            if r.get(key): r[key] = _num(r[key], key, where, key in INTEGERS)
        if r.get('셰프점수') or r.get('셰프이유'):
            scores = [x.strip() for x in r.get('셰프점수', '').split(',')]
            reasons = [x.strip() for x in r.get('셰프이유', '').split('|')]
            if len(scores) != 6 or any(x not in ('1', '2', '3', '4', '5', '보류') for x in scores) or len(reasons) != 6 or not all(reasons):
                raise UserError(f'{where}: 셰프 점수 6개(1~5 또는 보류)와 | 로 나눈 이유 6개가 필요합니다.', '예: 4,4,3,5,보류,5 / 이유1|이유2|이유3|이유4|이유5|이유6')
    return rows


def content_key(text):
    return re.sub(r'[\W_]+', '', re.sub(r'^\s*\[예시\]', '', text or '')).casefold()


def duplicates(rows, field='원문'):
    seen = defaultdict(list)
    for r in rows:
        k = content_key(r.get(field) or r.get('질문', ''))
        if k: seen[k].append(r['id'])
    return [ids for ids in seen.values() if len(ids) > 1]


class Store:
    def __init__(self, root, mode='example', out_root=None):
        if mode not in MODES: raise ValueError('자료 모드 오류')
        self.root = Path(root); self.mode = mode; self.folder = self.root / 'data' / mode
        self.out_root = Path(out_root) if out_root else DEFAULT_OUT
        self.out = self.out_root / MODES[mode]
        self.folder.mkdir(parents=True, exist_ok=True)
        self.migrated = []
        for kind in FIELDS:
            p = self.folder / f'{kind}.csv'
            if not p.exists(): write_csv(p, kind, []); continue
            rows, old = load_csv(p, kind)
            if old:  # 이전 버전 양식 → 사본을 남기고 새 칸을 빈 값으로 추가
                self._backup(p, kind, '양식갱신전'); write_csv(p, kind, rows); self.migrated.append(kind)

    def _backup(self, p, kind, tag=''):
        b = self.root / 'backups' / self.mode / f'{stamp()}_{kind}{"_" + tag if tag else ""}.csv'
        b.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(p, b); return b

    def read_file(self, path, kind): return validate(kind, load_csv(path, kind)[0], self.mode)
    def read(self, kind): return self.read_file(self.folder / f'{kind}.csv', kind)
    def all(self): return {k: self.read(k) for k in FIELDS}

    def save(self, kind, rows):
        validate(kind, rows, self.mode)
        p = self.folder / f'{kind}.csv'; self._backup(p, kind); write_csv(p, kind, rows)

    def upsert(self, kind, row):
        row = dict(row); rows = self.read(kind)
        idx = next((i for i, r in enumerate(rows) if r['id'] == row['id']), None)
        if idx is None: rows.append(row)
        else: rows[idx] = row
        self.save(kind, rows)

    def import_new(self, kind, path):
        new = self.read_file(path, kind); old = self.read(kind)
        overlap = {r['id'] for r in old} & {r['id'] for r in new}
        if overlap: raise UserError('기존 ID와 겹칩니다: ' + ', '.join(sorted(overlap)), '가져올 파일의 id를 바꾸거나, 기존 기록은 화면에서 수정하세요.')
        self.save(kind, old + new)
        return len(new)

    def export(self, kind):
        dest = self.out / '내보내기' / f'{kind}_{stamp()[:15]}.csv'
        write_csv(dest, kind, self.read(kind)); return dest

    def next_id(self, kind):
        nums = [int(m.group(1)) for r in self.read(kind) if (m := re.fullmatch(ID_PREFIX[kind] + r'(\d+)', r['id']))]
        return f'{ID_PREFIX[kind]}{max(nums, default=0) + 1:03}'

    def search(self, query):
        words = query.casefold().split()
        return [(k, r) for k, rs in self.all().items() for r in rs
                if all(w in ' '.join(r.values()).casefold() for w in words)]

    # ---------- 백업·복원 ----------
    def backup_zip(self):
        dest = self.out_root / '백업' / f'{stamp()[:15]}_{MODES[self.mode]}_백업.zip'
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as z:
            for kind in FIELDS: z.write(self.folder / f'{kind}.csv', f'data/{self.mode}/{kind}.csv')
            drafts = self.out / '초안'
            if drafts.exists():
                for p in drafts.rglob('*'):
                    if p.is_file(): z.write(p, '초안/' + p.relative_to(drafts).as_posix())
            z.writestr('백업정보.txt', f'로빈 작업실 {VERSION} / {MODE_TITLE[self.mode]} / {datetime.now():%Y-%m-%d %H:%M}\n복원: 앱의 [백업·도움말] → [백업에서 복원]')
        return dest

    def restore_zip(self, zpath):
        """먼저 모든 파일을 검사하고, 현재 자료를 백업한 뒤 입력 자료만 되돌린다."""
        try:
            with zipfile.ZipFile(zpath) as z:
                names = set(z.namelist()); parsed = {}
                for kind in FIELDS:
                    name = f'data/{self.mode}/{kind}.csv'
                    if name not in names:
                        raise UserError(f'백업 파일에 {MODE_TITLE[self.mode]} 자료({kind})가 없습니다.', '오른쪽 위 모드가 백업한 모드와 같은지 확인하세요.')
                    tmp = self.root / 'backups' / f'_restore_{kind}.csv'; tmp.parent.mkdir(parents=True, exist_ok=True)
                    tmp.write_bytes(z.read(name))
                    try: parsed[kind] = self.read_file(tmp, kind)
                    finally: tmp.unlink(missing_ok=True)
        except zipfile.BadZipFile:
            raise UserError('백업 zip 파일이 손상됐거나 zip이 아닙니다.', '[백업 폴더 열기]에서 다른 백업 파일을 고르세요.')
        before = self.backup_zip()
        for kind, rows in parsed.items(): write_csv(self.folder / f'{kind}.csv', kind, rows)
        return before


# ---------- 규칙 기반 분류 ----------

def classify_detail(r):
    """[(분류, 주제, 걸린 표현)]. 분류수정이 있으면 셰프 지정을 따른다."""
    if r.get('분류수정'): return [(r['분류수정'].strip(), '셰프 지정', '')]
    text = ' '.join(r.get(k, '') for k in ('원문', '질문', '해결문제'))
    squeezed = text.replace(' ', '')
    hits = []
    for cat, topics in TOPICS.items():
        for topic, words in topics.items():
            w = next((w for w in words if w in text or w.replace(' ', '') in squeezed), None)
            if w: hits.append((cat, topic, w))
    return hits or [(OTHER, '규칙에 걸리지 않음', '')]


def classify(r):
    return list(dict.fromkeys(c for c, _, _ in classify_detail(r)))


def analysis(data):
    """분류 → 주제 → 원문 기록 목록. 제외 처리한 댓글과 판매 결과 행은 뺀다."""
    groups = defaultdict(lambda: defaultdict(list))
    sources = [('댓글', r) for r in data['댓글'] if r.get('검토상태') != '제외']
    sources += [('공구문의', r) for r in data['공구문의'] if r.get('기록유형') != '결과' and (r.get('질문') or r.get('원문'))]
    for kind, r in sources:
        for cat, topic, word in classify_detail(r):
            groups[cat][topic].append((kind, r, word))
    order = list(TOPICS) + [OTHER]
    return dict(sorted(groups.items(), key=lambda kv: order.index(kv[0]) if kv[0] in order else len(order)))


def representative(items):
    """대표 댓글: 셰프 확인 > 10자 이상 중 가장 짧은 것."""
    def text(it): return it[1].get('질문') or it[1].get('원문', '')
    confirmed = [it for it in items if it[1].get('검토상태') == '확인']
    pool = confirmed or [it for it in items if len(text(it)) >= 10] or items
    return min(pool, key=lambda it: len(text(it)))


# ---------- 메뉴 평가 ----------

def evaluate(c, data):
    """규칙 기반 자동 평가. 근거가 없으면 점수 대신 '보류'."""
    refs = [x.strip() for x in c.get('관련댓글ID', '').split(',') if x.strip()]
    valid = {r['id']: r for r in data['댓글'] if r.get('검토상태') != '제외'}
    hit = [x for x in refs if x in valid]
    tests = [t for t in data['조리테스트'] if t['후보ID'] == c['id'] and t['검토상태'] == '셰프확인']
    product = next((p for p in data['상품'] if p['id'] == c.get('상품ID')), None)
    out = [(min(5, 2 + len(hit)), f'연결된 시청자 댓글 {len(hit)}건: {", ".join(hit)}') if hit
           else ('보류', '연결된 댓글 없음 — 실제 수요 근거 부족')]
    shot = next((t for t in tests if t['촬영장면']), None)
    fix = next((t for t in tests if t['실패와수정']), None)
    for field, test, label in [('화면변화', shot, '촬영장면'), ('조리원리', fix, '실패와수정')]:
        if test: out.append((4, f'셰프확인 조리테스트 {test["id"]}에 {label} 기록 있음 / 계획: {c.get(field) or "미기재"}'))
        elif c.get(field): out.append((3, f'검증 전 계획: {c[field]}'))
        else: out.append(('보류', '자료 없음'))
    out.append((3, f'검증 전 계획: {c["재료접근성"]}') if c.get('재료접근성') else ('보류', '자료 없음'))
    if not c.get('상품검증계획'): out.append(('보류', '상품 검증 계획 없음'))
    elif product and product['기능검토'] == '확인' and product['공식출처']: out.append((3, f'공식 자료 확인된 상품 {product["id"]} / 계획: {c["상품검증계획"]}'))
    else: out.append((2, f'계획만 있음. 상품 공식 자료 {NEEDS} / 계획: {c["상품검증계획"]}'))
    out.append((3, f'검증 전 계획: {c["독립가치"]}') if c.get('독립가치') else ('보류', '자료 없음'))
    return out


def chef_scores(c):
    if not c.get('셰프점수'): return []
    return list(zip([x.strip() for x in c['셰프점수'].split(',')], [x.strip() for x in c['셰프이유'].split('|')]))


def score_summary(scores):
    nums = [s for s, _ in scores if s not in ('보류',) and str(s).isdigit()]
    held = len(scores) - len(nums)
    if not scores: return '미평가'
    return f'{sum(int(s) for s in nums)}/{len(nums) * 5}' + (f' (보류 {held})' if held else '')


def linked_reviews(data, candidate):
    cats = set(classify({'원문': candidate.get('해결문제', '')})) - {OTHER}
    found = []
    for r in data['회고']:
        same_menu = r['메뉴'] and r['메뉴'] == candidate.get('메뉴')
        a, b = r.get('해결문제', ''), candidate.get('해결문제', '')
        same_problem = a and b and (a in b or b in a)
        same_cat = bool(a) and bool(cats & (set(classify({'원문': a})) - {OTHER}))
        if same_menu or same_problem or same_cat: found.append(r)
    return found


# ---------- 콘텐츠 초안 ----------

def split_items(text):
    return [p.strip(' -·') for p in re.split(r'\s*(?:/|\n|→|;)\s*', text or '') if p.strip(' -·')]


def content(t, product, candidate=None, comments=(), reviews=()):
    """셰프확인 조리 기록만 원본으로 쓴다. 기록에 없는 양·시간·불 세기·효능은 만들지 않는다."""
    candidate = candidate or {}
    verified = t.get('검토상태') == '셰프확인'
    val = lambda key: (t.get(key) or NEEDS) if verified else f'{NEEDS} — 셰프 미검토 기록'
    menu = t.get('메뉴') or candidate.get('메뉴') or NEEDS
    typ = candidate.get('콘텐츠유형', '')
    problem = candidate.get('해결문제') or (comments[0].get('해결문제') if comments else '') or NEEDS
    failure = t.get('실패와수정', '') if verified else ''
    shots = split_items(t.get('촬영장면')) if verified else []
    steps = split_items(t.get('조리순서')) if verified else []
    src = f'조리테스트 {t["id"]} ({t.get("검토상태") or "미검토"})' + (f' / 후보 {candidate["id"]}' if candidate.get('id') else '') \
        + (f' / 댓글 {", ".join(c["id"] for c in comments)}' if comments else ' / 연결 댓글 없음') + (f' / 상품 {product["id"]}' if product else '')
    case = comments[0] if comments else None
    case_line = f'실제로 이런 댓글이 있었어요. "{case["원문"].replace("[예시] ", "")[:70]}" ({case["id"]})' if case else f'사례: {NEEDS} — 연결된 시청자 댓글 없음'
    fail_first = split_items(failure)[0] if failure else ''

    # 1. 제목·썸네일 (먼저 정한다)
    titles = [f'{menu} 할 때 "{problem}" 고민, 이 단계부터 보세요',
              f'{problem}? {menu}, 순서 하나만 다시 보세요']
    if failure: titles.append(f'셰프가 {menu} 실패하고 다시 해 본 기록')
    p_ok = product and product.get('기능검토') == '확인' and product.get('공식출처')
    if typ == '키' and product: titles.append(f'{menu}, {product["상품명"]} 쓰기 전에 직접 확인한 것' + ('' if p_ok else ' (공식 자료 확인 전 사용 보류)'))
    thumbs = ['여기서 갈려요', '이것부터 보세요', '다시 해봤어요'] + ([f'{problem}?'] if len(problem) <= 8 and problem != NEEDS else [])
    title_md = '## 제목 후보\n' + '\n'.join(f'{i}. {x}' for i, x in enumerate(titles, 1)) \
        + '\n\n## 썸네일 문구 후보 (10자 안팎, 정답은 숨김)\n' + '\n'.join(f'- {x} ({len(x.replace(" ", ""))}자)' for x in thumbs) \
        + f'\n\n## 기본 선택안 (셰프가 바꾸면 대본 도입부도 함께 수정)\n제목: {titles[0]}\n썸네일: {thumbs[0]}\n' \
        + '- 해결 방법(정답)은 썸네일에 쓰지 않습니다.\n- 실제 전후 장면이 촬영되지 않았다면 결과 차이를 암시하는 문구는 보류합니다.'

    # 2. 대본 (도입부: 공감 → 문제 → 사례 → 볼 이유)
    intro = [f'[공감] 여러분, {menu} 해 보셨죠? 정성껏 했는데 생각과 다르게 나오면 속상하시죠.',
             f'[문제] 많이 물어보신 고민은 이거예요. "{problem}"',
             f'[사례] {case_line}' + (f'\n저도 테스트할 때 그랬어요. {fail_first}' if fail_first else ''),
             f'[볼 이유] 오늘은 제목에서 말씀드린 그 고민, 어느 단계에서 갈리는지 제가 직접 해 본 기록으로 보여 드릴게요.'
             + ('' if failure else f' (실패·수정 기록: {NEEDS})')]
    step_md = '\n'.join(f'{i}. {s}' for i, s in enumerate(steps, 1)) or val('조리순서')
    record = (f'재료와 양: {val("재료와양")}\n조리 순서:\n{step_md}\n불 세기: {val("불세기")}\n시간: {val("시간")}\n'
              f'실패와 수정: {val("실패와수정")}\n맛 평가(셰프): {val("맛평가")}\n안전 확인: {val("안전확인")}\n'
              '※ 재료량·시간·불 세기는 기록된 값만 적었습니다. 빈 칸은 촬영 전에 채워 주세요.')

    unverified = product.get('미확인주장') if product else ''
    exp_ok = product and product.get('경험확인') == '셰프확인' and product.get('직접확인')
    if not product: product_md = '상품 없음 — 메뉴 중심으로 진행합니다.'
    else:
        facts = f'공식 자료로 확인한 기능: {product["확인기능"]} (출처: {product["공식출처"]}, 확인일: {product.get("확인날짜") or NEEDS})' if p_ok else f'공식 자료로 확인한 기능: {NEEDS}'
        exp = f'셰프 직접 사용 경험: {product["직접확인"]}' if exp_ok else f'셰프 직접 사용 경험: {NEEDS}'
        cond = product['가격공구조건'] if product.get('조건검토') == '확인' and product.get('가격공구조건') else NEEDS
        not_needed = ('## 이 상품이 필요 없을 수 있는 분\n- 지금 쓰는 냄비로도 원하는 결과가 나오는 분\n- 이 메뉴를 자주 하지 않는 분\n'
                      '- 무게·크기·보관 공간이 부담되는 분 (실제 무게·크기는 공식 자료로 확인)\n'
                      f'## 구매 전 비교할 조건\n- 정확한 모델·용량: {product.get("모델") or NEEDS}\n- 사용할 수 있는 열원(가스·인덕션 등): 공식 자료로 {NEEDS}\n'
                      f'- 무게·세척·보관: 공식 자료로 {NEEDS}\n- 가격·공구 조건: {cond}\n- 지금 가진 냄비와 같은 메뉴로 비교한 결과: 셰프 테스트 기록으로만 말하기')
        if typ == '키':
            product_md = f'## 상품 확인 (키 콘텐츠)\n{facts}\n{exp}\n\n{not_needed}'
        else:
            product_md = ('## 상품 언급 (풀링 콘텐츠 — 메뉴가 중심)\n실제 사용 장면에서 한 번만 자연스럽게 언급합니다.\n'
                          + (f'{facts}\n' if p_ok else '공식 자료 확인 전이므로 기능 설명은 보류합니다.\n') + f'\n{not_needed}')
        if unverified: product_md += f'\n\n## 말하지 않을 것 (확인되지 않은 주장)\n- {unverified}'
    review_md = '\n'.join(f'- 지난 회고 {r["id"]}: {r["다음변경"]}' for r in reviews if r.get('다음변경'))
    script = ('## 도입부\n' + '\n\n'.join(intro) + '\n\n## 본문 — 조리 기록 그대로\n여러분, 사용한 재료와 양부터 보겠습니다.\n'
              + record + '\n\n' + product_md
              + '\n\n## 마무리\n여러분은 어느 단계가 제일 어려우셨어요? 댓글로 알려 주세요. 다음 영상에서 이어서 다룰게요.'
              + ('\n\n## 이번 기획에 반영한 지난 회고\n' + review_md if review_md else ''))

    # 3. 롱폼 구성 + 촬영 순서
    structure = ['1. 훅 — 제목에서 약속한 장면(완성·실패 비교 컷)으로 시작', '2. 인사·공감 — 도입부 대본', '3. 재료 — 기록한 계량 그대로',
                 '4. 손질 — 시청자 질문 받는 소통 구간', '5. 조리 — 단계마다 불 세기·시간 자막(기록값만)', '6. 실패와 수정 — 무엇을 바꿨는지',
                 '7. 시식·맛 평가 — 셰프 평가만'] + (['8. 상품 확인 — 확인된 기능·직접 경험·필요 없는 분'] if typ == '키' and product else []) + ['마무리 — 질문 요청·다음 예고']
    shoot_rows = [('재료 전체 컷', '재료와양'), ('손질 과정', '조리순서'), ('조리 단계별 화면', '조리순서'), ('실패 결과와 수정 결과', '실패와수정'),
                  ('완성·단면', '촬영장면'), ('시식', '맛평가')]
    table = '| 순서 | 장면 | 근거 칸 | 상태 |\n|---|---|---|---|\n' + '\n'.join(
        f'| {i} | {name} | {key} | {"기록 있음" if verified and t.get(key) else NEEDS} |' for i, (name, key) in enumerate(shoot_rows, 1))
    table += '\n' + '\n'.join(f'| 추가 | {s} | 촬영장면 | 셰프 기록 |' for s in shots)
    longform = '## 롱폼 구성 (편집 순서)\n' + '\n'.join(structure) + '\n\n## 촬영 순서표 (촬영 순서 — 편집 순서와 다름)\n' + table \
        + '\n\n훅에 쓸 비교 컷은 조리 중에 미리 찍어 두고 편집에서 앞으로 옮깁니다.'

    # 4. 쇼츠·릴스 — 서로 다른 문제·장면
    ideas = [('시청자 고민', f'여러분, "{problem}" 이런 고민 있으셨죠?', problem, case_line, ['완성', '단면', '비교']),
             ('실패와 수정', f'여러분, 저도 {menu} 한 번에 안 됐어요.', fail_first or NEEDS, val('실패와수정'), ['실패', '수정']),
             ('놓치기 쉬운 단계', f'여러분, {menu} 시작 전에 이 순서부터 보세요.', steps[0] if steps else NEEDS, step_md, ['재료', '손질', '준비', '순서'])]
    free = list(shots); shorts = []
    for i, (angle, hook, focus, say, prefs) in enumerate(ideas):
        scene = next((s for s in free if any(p in s for p in prefs)), free[0] if free else None)
        if scene: free.remove(scene)
        else: scene = f'{NEEDS} — 다른 쇼츠와 같은 장면을 쓰지 않도록 촬영장면을 추가하세요'
        shorts.append(f'## 안 {i + 1} — {angle}\n훅: {hook}\n다룰 문제: {focus}\n장면: {scene}\n'
                      f'말할 내용(기록 그대로): {say}\n마무리: 여러분은 어떠셨어요? 댓글로 알려 주세요.')
    shorts_md = '\n\n'.join(shorts) + '\n\n조리 시간·재료량은 조리 기록 외에 추가하지 않습니다.'

    desc = (f'{menu}, "{problem}" 고민을 셰프가 직접 조리해 보며 기록했습니다.\n\n[재료와 양]\n{val("재료와양")}\n\n[만드는 순서]\n{step_md}\n\n'
            f'[불 세기·시간]\n{val("불세기")} / {val("시간")}\n\n[챕터] 편집 후 입력\n'
            + (f'\n[상품 안내]\n공식 자료로 확인된 내용만 적습니다: {product["확인기능"] if p_ok else NEEDS}\n가격·공구 조건: {NEEDS if not (product.get("조건검토") == "확인") else product["가격공구조건"]}\n' if product else '')
            + '\n여러분도 해 보시고 어느 단계가 어려웠는지 댓글로 알려 주세요.\n확인 전 수치·효능·판매 조건은 게시하지 않습니다.')
    community = (f'여러분, {menu} 만들 때 어떤 점이 제일 어려우세요?\n이번에는 "{problem}" 고민을 직접 조리하며 확인하고 있어요.\n'
                 + (f'테스트하면서 이런 일이 있었어요. {fail_first}\n' if fail_first else '')
                 + f'\n[투표 안] {problem} 겪어 보셨어요? ① 자주 ② 가끔 ③ 없어요\n\n궁금한 과정이 있으면 댓글로 알려 주세요. 연락처는 공개 댓글에 남기지 마세요.')
    tag = re.sub(r'\s+', '', menu)
    insta = (f'## 캡션\n{menu}, 이렇게 된 적 있으시죠?\n"{problem}"\n\n셰프가 직접 해 보고\n어디서 갈리는지 기록했어요.\n\n'
             f'자세한 과정은 영상에서 보세요.\n여러분은 어떠셨어요? 댓글로 알려 주세요.\n\n#{tag}\n\n'
             f'## 스토리 문구 (3장)\n1장: {problem}? (질문 스티커: "여러분은 어떠세요?")\n2장: {shots[0] if shots else "장면 " + NEEDS} — 여기서 갈려요\n'
             '3장: 영상에서 끝까지 보기 (링크는 게시 후 입력)')
    return {'1_제목썸네일': (title_md, src), '2_롱폼구성_촬영순서': (longform, src), '3_대본': (script, src),
            '4_쇼츠릴스': (shorts_md, src), '5_유튜브설명': (desc, src), '6_커뮤니티': (community, src), '7_인스타': (insta, src)}


# ---------- 초안 보관: 셰프 수정본을 덮어쓰지 않는다 ----------

class Drafts:
    def __init__(self, out):
        self.dir = Path(out) / '초안'; self.meta = self.dir / '_기록'
        for d in (self.dir, self.meta / '이전본', self.meta / '생성본'): d.mkdir(parents=True, exist_ok=True)
        self.state_path = self.meta / '상태.json'
        self.state = json.loads(self.state_path.read_text(encoding='utf-8')) if self.state_path.exists() else {}

    def _save_state(self): self.state_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=1), encoding='utf-8')

    def log(self, name, action, basis=''):
        p = self.meta / '변경기록.csv'; new = not p.exists()
        with p.open('a', encoding='utf-8-sig', newline='') as f:
            w = csv.writer(f)
            if new: w.writerow(['시각', '파일', '동작', '근거'])
            w.writerow([datetime.now().strftime('%Y-%m-%d %H:%M:%S'), name, action, basis])

    def path(self, name):
        p = (self.dir / name).resolve()
        if p.parent != self.dir.resolve() or p.suffix != '.md': raise UserError('초안 폴더의 .md 파일만 다룰 수 있습니다.', '목록에서 초안을 고르세요.')
        return p

    def status(self, name):
        p = self.path(name); st = self.state.get(name, {})
        if not p.exists(): return '없음'
        edited = sha(p.read_text(encoding='utf-8')) != st.get('written')
        pending = st.get('pending') and st.get('pending') != st.get('written')
        return ('수정됨' if edited else '자동') + (' · 새 생성본 대기' if pending and edited else '')

    def write_generated(self, name, text, basis):
        p = self.path(name); h = sha(text); st = self.state.setdefault(name, {})
        if not p.exists():
            p.write_text(text, encoding='utf-8'); st.update(written=h, pending=None); action = '생성'
        else:
            cur = sha(p.read_text(encoding='utf-8'))
            if cur == st.get('written'):
                if h == cur: return '변경 없음'
                shutil.copy2(p, self.meta / '이전본' / f'{stamp()}_{name}')
                p.write_text(text, encoding='utf-8'); st.update(written=h, pending=None); action = '재생성 반영'
            else:
                if st.get('pending') == h: return '수정본 유지'
                st['pending'] = h; action = '수정본 유지 — 새 생성본은 _기록/생성본에 보관'
        (self.meta / '생성본' / f'{stamp()}_{name}').write_text(text, encoding='utf-8')
        self._save_state(); self.log(name, action, basis)
        return action

    def latest_generated(self, name):
        files = sorted((self.meta / '생성본').glob(f'*_{name}'))
        return files[-1] if files else None

    def save_user(self, name, text):
        p = self.path(name)
        if p.exists(): shutil.copy2(p, self.meta / '이전본' / f'{stamp()}_{name}')
        p.write_text(text, encoding='utf-8'); self.log(name, '셰프 수정 저장 (이전본 보관)')

    def adopt_generated(self, name):
        g = self.latest_generated(name)
        if not g: raise UserError('새 생성본이 없습니다.', '[초안 만들기]를 먼저 실행하세요.')
        p = self.path(name); text = g.read_text(encoding='utf-8')
        if p.exists(): shutil.copy2(p, self.meta / '이전본' / f'{stamp()}_{name}')
        p.write_text(text, encoding='utf-8'); self.state.setdefault(name, {}).update(written=sha(text), pending=None)
        self._save_state(); self.log(name, '새 생성본으로 교체 (수정본은 이전본에 보관)')

    def history(self, name):
        p = self.meta / '변경기록.csv'
        if not p.exists(): return []
        with p.open(encoding='utf-8-sig', newline='') as f:
            return [r for r in csv.DictReader(f) if r['파일'] == name]

    def names(self): return sorted(p.name for p in self.dir.glob('*.md'))


def save_revision(path, text):
    """초안 파일 직접 저장(이전본 보관)."""
    path = Path(path); Drafts(path.parent.parent).save_user(path.name, text)


# ---------- 진행 단계 점검 ----------

STEPS = ['자료 입력', '불편 분석', '메뉴 후보', '조리 기록', '콘텐츠 초안', '성과 회고']


def progress(data):
    comments = [r for r in data['댓글'] if r.get('검토상태') != '제외']
    cands = data['메뉴후보']; tests = data['조리테스트']; ok_tests = [t for t in tests if t['검토상태'] == '셰프확인']
    steps = []
    miss = [f'{k} 0건' for k in ('댓글', '상품') if not data[k]]
    steps.append(('자료 입력', f'댓글 {len(comments)} · 문의 {len(data["공구문의"])} · 상품 {len(data["상품"])}', miss))
    unrev = [r['id'] for r in comments if r.get('검토상태') in ('', '미검토')]
    other = [r['id'] for r in comments if classify(r) == [OTHER]]
    steps.append(('불편 분석', f'분류 {len(comments)}건', ([f'미검토 댓글 {len(unrev)}건'] if unrev else []) + ([f'사람 확인 필요 {len(other)}건'] if other else []) + ([] if comments else ['댓글 없음'])))
    no_chef = [c['id'] for c in cands if not c.get('셰프점수')]
    chosen = [c['id'] for c in cands if c.get('최종판단') == '선택']
    steps.append(('메뉴 후보', f'후보 {len(cands)} · 선택 {len(chosen)}', ([] if cands else ['메뉴후보 없음']) + ([f'셰프 점수 없음 {len(no_chef)}개'] if no_chef else []) + ([] if chosen or not cands else ['셰프 최종 선택 없음'])))
    gaps = [f'{t["id"]} {f}' for t in ok_tests for f in ('재료와양', '조리순서', '불세기', '시간', '맛평가', '안전확인') if not t[f]]
    steps.append(('조리 기록', f'기록 {len(tests)} · 셰프확인 {len(ok_tests)}', ([] if ok_tests else ['셰프확인된 조리테스트 없음']) + gaps[:4] + (['…'] if len(gaps) > 4 else [])))
    unverified_p = [p['id'] for p in data['상품'] if p['기능검토'] != '확인' or not p['공식출처']]
    steps.append(('콘텐츠 초안', f'초안 원본 {len(ok_tests)}건', ([] if ok_tests else ['셰프확인 조리 기록이 있어야 생성']) + ([f'상품 공식자료 미확인 {", ".join(unverified_p)}'] if unverified_p else [])))
    no_time = [m['id'] for m in data['영상성과'] if not m['경과시간'] or not m['플랫폼']]
    steps.append(('성과 회고', f'성과 {len(data["영상성과"])} · 회고 {len(data["회고"])}', ([] if data['영상성과'] else ['영상 성과 없음']) + ([] if data['회고'] else ['회고 없음']) + ([f'플랫폼/경과시간 없음 {", ".join(no_time)}'] if no_time else [])))
    return [{'name': n, 'summary': s, 'missing': m, 'done': not m} for n, s, m in steps]


# ---------- 전체 흐름 실행 ----------

def _header(store, title, basis):
    label = ('⚠ 예시 연습 자료 — 가상 자료이며 실제 조리·성과·제품 근거가 아닙니다' if store.mode == 'example'
             else '실제 입력 기반 검토용 초안 — 셰프 확인 전 게시 금지')
    return (f'# {title}\n{label}\n만든 방식: 규칙·서식 기반 (외부 AI 미사용 · 외부 전송 없음) · 완성 영상이나 확정 게시물이 아닙니다\n'
            f'근거: {basis}\n\n')


def run_all(store):
    data = store.all(); drafts = Drafts(store.out); actions = {}

    def emit(name, title, body, basis):
        text = _header(store, title, basis) + redact(body)
        actions[name + '.md'] = drafts.write_generated(name + '.md', text, basis)

    # 01 시청자 불편 (규칙 기반)
    groups = analysis(data); dup = duplicates([r for r in data['댓글'] if r.get('검토상태') != '제외'])
    dup_ids = {i for g in dup for i in g}
    body = ['분류 방식: **규칙 기반**(표현 목록과 일치 여부). AI 분석이 아닙니다. 한 원문이 여러 분류에 들어갈 수 있어 합계는 원문 수와 다릅니다.',
            '영상 아이디어는 모두 **추정**입니다. 댓글에 직접 나온 요청은 "시청자가 직접 말함"으로 따로 표시합니다.\n']
    for cat, topics in groups.items():
        ids = {it[1]['id'] for items in topics.values() for it in items}
        body.append(f'## {cat} — {len(ids)}건')
        for topic, items in sorted(topics.items(), key=lambda kv: -len(kv[1])):
            kind, rep, word = representative(items)
            body.append(f'### {topic} — {len(items)}건' + (f' (걸린 표현 예: "{word}")' if word else ''))
            body.append(f'대표: [{rep["id"]}] {rep.get("질문") or rep["원문"]}')
            for k, r, _ in items:
                mark = ' · 중복 의심' if r['id'] in dup_ids else ''
                src = ' / '.join(x for x in [r.get('플랫폼'), r.get('영상ID'), r.get('댓글ID'), r.get('URL')] if x) or '출처 미기재'
                body.append(f'- [{k} {r["id"]}] {(r.get("질문") or r["원문"])[:80]}\n  출처: {src}{mark}')
            stated = [f'{r["id"]}: {r["해결문제"]}' for _, r, _ in items if r.get('해결문제')]
            if stated: body.append('시청자가 직접 말한 해결 희망: ' + ' / '.join(stated))
        body.append(f'**영상 아이디어 (추정)**: {IDEAS.get(cat, IDEAS[OTHER])}\n')
    if dup: body.append('## 중복 의심\n' + '\n'.join('- ' + ', '.join(g) for g in dup) + '\n같은 사람이 여러 번 쓴 것인지 확인한 뒤 필요하면 검토상태를 "제외"로 바꾸세요.')
    emit('01_시청자불편', '시청자 불편 분석', '\n'.join(body) if groups else '댓글·문의 입력이 없습니다. [자료 입력] → 댓글에서 추가하세요.', f'댓글 {len(data["댓글"])}건, 공구문의 {len(data["공구문의"])}건')

    # 02 메뉴 선정표
    b = ['자동 평가는 **규칙 기반 추정**입니다(연결 댓글 수·계획 기재·셰프확인 기록 유무). 맛·안전·성능은 평가하지 않습니다.',
         '근거가 없으면 점수 대신 **보류**로 둡니다. 셰프 점수는 따로 보관하며, 최종 메뉴는 셰프가 [최종판단] 칸에 직접 입력합니다.\n']
    for cuisine in ['한식', '일식', '지중해식', '기타', '']:
        cs = [c for c in data['메뉴후보'] if (c['요리권'] or '') == cuisine or (cuisine == '기타' and c['요리권'] not in ('한식', '일식', '지중해식', ''))]
        if not cs: continue
        b.append(f'# {cuisine or "요리권 미기재"}')
        for c in cs:
            auto = evaluate(c, data); chef = chef_scores(c)
            b.append(f'## {c["메뉴"]} [{c["id"]}] — {c["콘텐츠유형"] or "키/풀링 미정"} / 해결 문제: {c["해결문제"] or NEEDS}')
            b.append('| 기준 | 자동(규칙) | 자동 이유 | 셰프 점수 | 셰프 이유 |\n|---|---|---|---|---|')
            for i, name in enumerate(CRITERIA):
                cs_, cr = chef[i] if chef else ('미평가', '')
                b.append(f'| {name} | {auto[i][0]} | {auto[i][1]} | {cs_} | {cr} |')
            b.append(f'자동 합계: {score_summary(auto)} · 셰프 합계: {score_summary(chef)} · **최종 판단(셰프 입력): {c["최종판단"] or "미정"}**')
            for r in linked_reviews(data, c): b.append(f'- 참고할 이전 회고 [{r["id"]}] {r["메뉴"]}: 다음 변경 = {r["다음변경"] or "미기재"} (근거 {r["근거"] or "미기재"})')
            b.append('')
    emit('02_메뉴선정표', '메뉴 선정표', '\n'.join(b) if data['메뉴후보'] else '메뉴후보가 없습니다.', f'메뉴후보 {len(data["메뉴후보"])}건')

    # 03 콘텐츠 초안 — 셰프확인 조리 기록만
    products = {p['id']: p for p in data['상품']}; comments = {r['id']: r for r in data['댓글'] if r.get('검토상태') != '제외'}
    skipped = []
    for t in data['조리테스트']:
        if t['검토상태'] != '셰프확인': skipped.append(t['id']); continue
        c = next((c for c in data['메뉴후보'] if c['id'] == t['후보ID']), {})
        linked = [comments[x.strip()] for x in c.get('관련댓글ID', '').split(',') if x.strip() in comments]
        typ = c.get('콘텐츠유형') or '미지정'
        direction = {'키': '키 콘텐츠: 시청자 문제 → 실제 조리로 상품 확인 → 확인된 경험과 한계. 장점 나열 금지.',
                     '풀링': '풀링 콘텐츠: 메뉴의 실패 해결이 중심. 상품은 실제 사용 장면에서만 언급.'}.get(typ, '키/풀링을 메뉴후보에서 정해 주세요.')
        for name, (txt, src) in content(t, products.get(t['상품ID']), c, linked, linked_reviews(data, c) if c else []).items():
            emit(f'03_{t["id"]}_{name}', f'{t["메뉴"]} — {name.split("_", 1)[1]}', f'콘텐츠 유형: {typ}\n편집 방향: {direction}\n\n{txt}', src)

    # 04 공구 FAQ — 시청자 질문 근거
    faq = ['시청자 질문(공구문의 + 구매 망설임 댓글)만 모았습니다. 답변은 **셰프확인 + 답변근거**가 있을 때만 적고, 나머지는 "확인 필요"입니다.\n']
    qs = [('공구문의', q) for q in data['공구문의'] if q.get('기록유형') != '결과' and (q.get('질문') or q.get('원문'))]
    qs += [('댓글', r) for r in comments.values() if '제품 구매 망설임' in classify(r)]
    by_topic = defaultdict(list)
    for kind, q in qs:
        topics = [tp for cat, tp, _ in classify_detail(q) if cat == '제품 구매 망설임'] or ['그 밖의 질문']
        by_topic[topics[0]].append((kind, q))
    for topic, items in sorted(by_topic.items(), key=lambda kv: -len(kv[1])):
        faq.append(f'## {topic} — 질문 {len(items)}건')
        for kind, q in items:
            ok = kind == '공구문의' and q['답변검토'] == '셰프확인' and q['답변근거'] and q['확인답변']
            faq.append(f'### [{kind} {q["id"]}] {q.get("질문") or q["원문"]}\n답변: {q["확인답변"] if ok else NEEDS + " — 검토된 답변 근거 없음"}\n'
                       f'근거: {q.get("답변근거") if ok else "없음"}\n출처: {q.get("URL") or q.get("영상ID") or "미기재"}')
            p = products.get(q.get('상품ID', ''))
            if not ok and p and topic.startswith('가격') and p['조건검토'] == '확인':
                faq.append(f'참고 자료: 상품 {p["id"]} 가격공구조건(확인됨) — 답변 확정은 셰프가 합니다.')
    emit('04_공구FAQ', '공동구매 FAQ', '\n'.join(faq) if qs else '실제 질문 입력 후 생성합니다. 자주 받은 질문으로 꾸미지 않습니다.', f'공구문의 {len(data["공구문의"])}건')

    # 05 성과 회고
    emit('05_성과회고', '성과 회고', retrospective(data), f'영상성과 {len(data["영상성과"])}건, 회고 {len(data["회고"])}건, 공구결과')

    # 06 확인 필요
    checks = []
    for st in progress(data): checks += [f'[{st["name"]}] {m}' for m in st['missing']]
    for tid in skipped: checks.append(f'조리테스트 {tid}: 셰프 미검토 — 콘텐츠 초안을 만들지 않았습니다.')
    ids = {k: {r['id'] for r in rs} for k, rs in data.items()}
    for t in data['조리테스트']:
        if t['상품ID'] and t['상품ID'] not in ids['상품']: checks.append(f'{t["id"]}: 상품ID {t["상품ID"]} 연결 없음')
        if t['후보ID'] and t['후보ID'] not in ids['메뉴후보']: checks.append(f'{t["id"]}: 후보ID {t["후보ID"]} 연결 없음')
    for c in data['메뉴후보']:
        for ref in [v.strip() for v in c['관련댓글ID'].split(',') if v.strip()]:
            if ref not in ids['댓글']: checks.append(f'{c["id"]}: 댓글 {ref} 연결 없음')
    for p in products.values():
        if p['미확인주장']: checks.append(f'{p["id"]}: 확인되지 않은 주장은 홍보에 쓰지 않음 — {p["미확인주장"]}')
    for g in dup: checks.append('중복 의심 댓글: ' + ', '.join(g))
    kept = [n for n, a in actions.items() if a.startswith('수정본 유지')]
    for n in kept: checks.append(f'{n}: 셰프 수정본을 유지했습니다. 새 생성본은 [새 생성본 보기]로 비교하세요.')
    emit('06_확인필요', '확인 필요 목록', '\n'.join('- ' + c for c in checks) or '자동 점검에서 빠진 자료가 없습니다. 내용의 사실·안전은 셰프가 확인해 주세요.', '입력 전체')

    manifest = {'version': VERSION, 'mode': store.mode, 'created': datetime.now().isoformat(timespec='seconds'),
                'external_ai': False, 'external_transfer': False, 'cost_krw': 0, 'counts': {k: len(v) for k, v in data.items()},
                'inputs': {k: hashlib.sha256((store.folder / f'{k}.csv').read_bytes()).hexdigest() for k in FIELDS},
                'tests_used': [t['id'] for t in data['조리테스트'] if t['검토상태'] == '셰프확인'], 'tests_skipped': skipped,
                'actions': actions, 'output_status': '검토용 초안 — 게시 안 함'}
    runs = store.out / '실행기록'; runs.mkdir(parents=True, exist_ok=True)
    (runs / f'{stamp()}.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'folder': drafts.dir, 'actions': actions, 'kept': kept, 'skipped': skipped, 'manifest': manifest}


def generate(store): return run_all(store)['folder']


def _f(v): return float(v) if v not in ('', None) else None


def retrospective(data):
    out = ['## 1. 영상 성과 — 같은 플랫폼·같은 게시 후 경과시간끼리만 비교', '빈 값은 0이 아니라 **미수집**입니다.\n']
    groups = defaultdict(list); excluded = []
    for m in data['영상성과']:
        if m['플랫폼'] and m['경과시간']: groups[(m['플랫폼'], _f(m['경과시간']))].append(m)
        else: excluded.append(m['id'])
    cols = ['조회수', '클릭률', '평균시청초', '저장수', '공유수']
    for (plat, hrs), ms in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        out.append(f'### {plat} · 게시 후 {hrs:g}시간 — {len(ms)}개')
        out.append('| 성과ID | 영상ID | 메뉴 | 제목 | ' + ' | '.join(cols) + ' | 확인시각 |\n|' + '---|' * (len(cols) + 5))
        for m in ms: out.append(f'| {m["id"]} | {m["영상ID"]} | {m["메뉴"]} | {m["제목"]} | ' + ' | '.join(m[c] or '미수집' for c in cols) + f' | {m["확인시각"] or "미기재"} |')
        if len(ms) < 2: out.append('같은 조건의 비교 대상이 없어 높다/낮다를 판단하지 않습니다.')
        else:
            for c in cols:
                have = [m for m in ms if m[c]]
                if len(have) >= 2:
                    top = max(have, key=lambda m: float(m[c]))
                    out.append(f'- {c}: 이 묶음에서 가장 높은 영상 {top["영상ID"]} ({top[c]}) — 값이 있는 {len(have)}개 중 비교')
        out.append('')
    if excluded: out.append(f'비교에서 뺀 성과(플랫폼 또는 경과시간 없음): {", ".join(excluded)}\n')
    out.append('## 2. 영상 회고')
    for r in [r for r in data['회고'] if r['유형'] != '공구']:
        out.append(f'### [{r["id"]}] {r["메뉴"]} (영상 {r["영상ID"] or "미기재"})')
        out += [f'- 해결하려던 문제: {r["해결문제"] or "미기재"}', f'- 실제 성과: {r["실제성과"] or "미수집"}',
                f'- 시청자 반응: {r["시청자반응"] or "미기재"}', f'- 다음에 바꿀 한 가지: {r["다음변경"] or "미기재 — 한 가지만 적어 주세요"}',
                f'- 근거: {r["근거"] or "미기재"}']
        for m in data['영상성과']:
            if r['영상ID'] and m['영상ID'] == r['영상ID']:
                out.append(f'  연결 성과 [{m["id"]}] {m["플랫폼"] or "플랫폼 미기재"} {m["경과시간"] or "?"}시간: ' + ', '.join(f'{c} {m[c] or "미수집"}' for c in cols))
    out.append('\n## 3. 공동구매 결과 — 선예약은 주문·매출에 넣지 않습니다')
    res = [q for q in data['공구문의'] if q['판매수'] or q['선예약수'] or q['매출'] or q['기록유형'] == '결과']
    if not res: out.append('판매 집계 입력 없음.')
    for q in res:
        conv = (f'{int(q["판매수"]) / int(q["전환분모"]) * 100:.1f}% (주문 {q["판매수"]} ÷ {q["분모기준"] or "분모 기준 미기재"} {q["전환분모"]})'
                if q['판매수'] and q['전환분모'] and int(q['전환분모']) > 0 else '계산 안 함 — 분자(확정 주문) 또는 분모가 없음')
        out.append(f'### [{q["id"]}] {q["날짜"] or "날짜 미기재"} / 상품 {q["상품ID"] or "미기재"}\n- 확정 주문: {q["판매수"] or "미수집"}\n'
                   f'- 선예약(주문 아님): {q["선예약수"] or "미수집"}\n- 확정 매출: {q["매출"] or "미수집"}\n- 전환율: {conv}\n'
                   f'- 집계 기준: {q["판매근거"] or "미기재"}\n- 반품·불만: {q["반품불만"] or "미기재"}')
    out.append('\n## 4. 공동구매 회고')
    for r in [r for r in data['회고'] if r['유형'] == '공구']:
        out += [f'### [{r["id"]}] {r["메뉴"]} / 상품 {r["상품ID"] or "미기재"}', f'- 구매를 이끈 질문: {r["구매유도질문"] or "미기재"}',
                f'- 구매를 막은 질문: {r["구매장벽질문"] or "미기재"}', f'- 불만과 반품 사유: {r["불만"] or "미기재"}',
                f'- 다음 개선점: {r["다음변경"] or "미기재"}', f'- 근거: {r["근거"] or "미기재"}']
    out.append('\n구매 문의가 있었다고 해서 구매 원인이 확인된 것으로 보지 않습니다. 근거 없는 항목은 "추정"으로 적어 주세요.')
    return '\n'.join(out)


# ---------- 테마 밥상 추천 (재미·기획용, 규칙 기반) ----------

def theme_report(store, birth=None, mbti=None, day=None, audience='밥상 식구님들'):
    rows = store.read('메뉴후보')
    if not rows: raise UserError('메뉴 후보가 없습니다.', '[① 자료 입력]에서 메뉴후보를 먼저 입력하세요.')
    menus = [tm.Menu(r['id'], r['메뉴'], MODES[store.mode], r['요리권'], tm._split(r['색']), tm._split(r['맛']), tm._split(r['스타일태그']),
                     '예' if r['최종판단'] == '선택' else '') for r in rows]
    try: mb = tm.parse_mbti(mbti) if mbti else None
    except ValueError as e: raise UserError(str(e), '네 글자로 입력하세요. 예: ISFJ. 모르면 비워 두세요.')
    return tm.build_report(menus, birth, mb, day or datetime.now().date(), audience)
