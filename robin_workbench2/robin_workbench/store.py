# -*- coding: utf-8 -*-
"""자료 저장소. 예시/실제를 폴더째 나누고, 저장할 때마다 이전 파일을 백업한다."""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import re
import shutil
import zipfile
from pathlib import Path

from .schema import TABLES, Table

MODES = ("예시", "실제")
BACKUP_KEEP = 50
FORMAT_VERSION = 2


class WorkbenchError(Exception):
    """로빈님이 고칠 수 있는 오류. 메시지에 원인과 해결 방법을 함께 쓴다."""


def now() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def default_home() -> Path:
    """자료 보관 위치: 문서\\로빈_요리공구작업실2 (앱 폴더를 새 버전으로 바꿔도 자료는 남는다)."""
    env = os.environ.get("ROBIN_WB_HOME")
    if env:
        return Path(env)
    return Path(os.environ.get("USERPROFILE") or Path.home()) / "Documents" / "로빈_요리공구작업실2"


def default_output() -> Path:
    """결과물 저장 위치: 다운로드\\로빈_요리공구작업실2_결과"""
    base = os.environ.get("ROBIN_WB_OUT")
    if base:
        return Path(base)
    return Path(os.environ.get("USERPROFILE") or Path.home()) / "Downloads" / "로빈_요리공구작업실2_결과"


# ---------------------------------------------------------------- 값 검사
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")


def clean_value(table: Table, key: str, value) -> str:
    """입력값을 검사하고 저장 형태(문자열)로 바꾼다. 빈 값은 빈 값 그대로 둔다(0으로 바꾸지 않음)."""
    f = table.field(key)
    v = "" if value is None else str(value).strip()
    if f.kind != "long":
        v = " ".join(v.split())
    if v == "":
        return ""
    if f.kind == "int":
        n = v.replace(",", "")
        if not re.fullmatch(r"\d+", n):
            raise WorkbenchError(f"'{key}'에는 0 이상의 정수만 넣습니다. (지금: '{v}')\n→ 쉼표·단위 없이 숫자만, 모르면 비워 두세요.")
        return str(int(n))
    if f.kind == "float":
        n = v.replace(",", "").rstrip("%")
        try:
            x = float(n)
        except ValueError:
            raise WorkbenchError(f"'{key}'에는 숫자만 넣습니다. (지금: '{v}')\n→ 모르면 비워 두세요.")
        if x < 0:
            raise WorkbenchError(f"'{key}'는 음수가 될 수 없습니다. (지금: '{v}')")
        return ("%g" % x)
    if f.kind == "score":
        if v not in {"1", "2", "3", "4", "5"}:
            raise WorkbenchError(f"'{key}'는 1~5 중 하나로 적습니다. 평가를 안 했으면 비워 두세요. (지금: '{v}')")
        return v
    if f.kind == "date":
        if not _DATE.match(v):
            raise WorkbenchError(f"'{key}' 날짜 형식이 맞지 않습니다. 예: 2026-09-20 (지금: '{v}')")
        try:
            dt.date.fromisoformat(v)
        except ValueError:
            raise WorkbenchError(f"'{key}'에 없는 날짜입니다: '{v}'")
        return v
    if f.kind == "datetime":
        if not _DATETIME.match(v):
            raise WorkbenchError(f"'{key}' 형식이 맞지 않습니다. 예: 2026-09-22 09:00 (지금: '{v}')")
        try:
            dt.datetime.strptime(v, "%Y-%m-%d %H:%M")
        except ValueError:
            raise WorkbenchError(f"'{key}'에 없는 날짜·시각입니다: '{v}'")
        return v
    if f.kind == "choice" and f.choices and v not in f.choices:
        raise WorkbenchError(f"'{key}'는 다음 중 하나로 적습니다: {', '.join(f.choices)} (지금: '{v}')")
    return v


def _norm(s: str) -> str:
    return re.sub(r"[\s\W_]+", "", (s or "").lower())


# ---------------------------------------------------------------- 저장소
class Store:
    def __init__(self, home: Path | None = None, mode: str = "예시"):
        if mode not in MODES:
            raise WorkbenchError(f"모드는 {MODES} 중 하나입니다.")
        self.home = Path(home) if home else default_home()
        self.mode = mode
        self.data: dict = {}
        self.load()

    # --- 파일 위치
    @property
    def folder(self) -> Path:
        return self.home / "data" / self.mode

    @property
    def path(self) -> Path:
        return self.folder / "workbench.json"

    @property
    def backup_dir(self) -> Path:
        return self.folder / "backups"

    def output_dir(self) -> Path:
        d = default_output() / self.mode
        d.mkdir(parents=True, exist_ok=True)
        return d

    # --- 읽기/쓰기
    def _empty(self) -> dict:
        return {"format": FORMAT_VERSION, "mode": self.mode, "created": now(),
                "tables": {k: [] for k in TABLES}, "drafts": {}, "history": [], "counters": {}}

    def load(self) -> None:
        if not self.path.exists():
            self.data = self._empty()
            if self.mode == "예시":
                from .example_data import fill_example
                fill_example(self)
                self.save("예시 자료 처음 만들기")
            return
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            raise WorkbenchError(
                f"자료 파일을 읽지 못했습니다: {self.path}\n원인: {e}\n"
                f"→ 시작 화면의 '백업에서 복원'으로 {self.backup_dir} 의 최근 백업을 불러오세요.")
        if self.data.get("mode") != self.mode:
            raise WorkbenchError(f"{self.path} 는 '{self.data.get('mode')}' 자료인데 '{self.mode}' 폴더에 있습니다. "
                                 "→ 파일을 원래 폴더로 옮기세요.")
        for k in TABLES:
            self.data["tables"].setdefault(k, [])
        for k in ("drafts", "history", "counters"):
            self.data.setdefault(k, {} if k != "history" else [])

    def save(self, reason: str = "") -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            shutil.copy2(self.path, self.backup_dir / f"workbench_{stamp}.json")
            olds = sorted(self.backup_dir.glob("workbench_*.json"))
            for f in olds[:-BACKUP_KEEP]:
                f.unlink(missing_ok=True)
        self.data["saved"] = now()
        self.data["save_reason"] = reason
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError as e:
            raise WorkbenchError(f"저장하지 못했습니다: {e}\n→ 다른 프로그램이 파일을 쓰고 있지 않은지, 디스크 공간을 확인하세요.")

    # --- 기록 다루기
    def rows(self, table: str) -> list[dict]:
        return self.data["tables"][table]

    def get(self, table: str, rid: str) -> dict | None:
        t = TABLES[table]
        return next((r for r in self.rows(table) if r.get(t.id_field) == rid), None)

    def next_id(self, table: str) -> str:
        t = TABLES[table]
        prefix = ("EX-" if self.mode == "예시" else "") + t.id_prefix + "-"
        existing = {r.get(t.id_field, "") for r in self.rows(table)}
        n = self.data["counters"].get(table, 0)
        while True:
            n += 1
            rid = f"{prefix}{n:04d}"
            if rid not in existing:
                self.data["counters"][table] = n
                return rid

    def _dedupe_key(self, t: Table, rec: dict) -> tuple | None:
        if not t.dedupe:
            return None
        vals = tuple(_norm(rec.get(k, "")) for k in t.dedupe)
        return vals if any(vals) else None

    def find_duplicate(self, table: str, rec: dict, ignore_id: str = "") -> dict | None:
        t = TABLES[table]
        key = self._dedupe_key(t, rec)
        if key is None:
            return None
        for r in self.rows(table):
            if r.get(t.id_field) != ignore_id and self._dedupe_key(t, r) == key:
                return r
        return None

    def validate(self, table: str, values: dict) -> dict:
        t = TABLES[table]
        rec = {}
        for f in t.fields:
            rec[f.key] = clean_value(t, f.key, values.get(f.key, ""))
        missing = [f.key for f in t.fields if f.required and not rec[f.key]]
        if missing:
            raise WorkbenchError(f"필수 칸이 비어 있습니다: {', '.join(missing)}\n→ 이 칸을 채운 뒤 다시 저장하세요.")
        rid = rec[t.id_field]
        if rid and self.mode == "실제" and rid.upper().startswith("EX-"):
            raise WorkbenchError(f"'{rid}'는 예시 자료 ID입니다. 실제 모드에는 넣을 수 없습니다.\n→ ID 칸을 비우면 새 ID가 붙습니다.")
        return rec

    def upsert(self, table: str, values: dict, reason: str = "화면 입력", save: bool = True) -> dict:
        """새로 넣거나 고친다. 같은 ID면 고치기, 내용이 같은 다른 기록이 있으면 중복으로 멈춘다."""
        t = TABLES[table]
        rec = self.validate(table, values)
        rid = rec[t.id_field]
        old = self.get(table, rid) if rid else None
        dup = self.find_duplicate(table, rec, ignore_id=rid)
        if dup is not None:
            raise WorkbenchError(f"같은 내용이 이미 있습니다: {dup.get(t.id_field)}\n"
                                 f"(중복 기준: {', '.join(t.dedupe)})\n→ 기존 기록을 고치거나, 정말 다른 기록이면 내용을 구분해 주세요.")
        stamp = now()
        if old is None:
            if not rid:
                rec[t.id_field] = self.next_id(table)
            rec["_created"] = stamp
            rec["_updated"] = stamp
            rec["_auto"] = {}
            rec["_extra"] = values.get("_extra", {}) or {}
            self.rows(table).append(rec)
            self.log(table, rec[t.id_field], "추가", "", "", reason)
            result = rec
        else:
            for k, v in rec.items():
                if old.get(k, "") != v:
                    self.log(table, rid, k, old.get(k, ""), v, reason)
                    old[k] = v
            old["_updated"] = stamp
            result = old
        if save:
            self.save(f"{t.title} {reason}")
        return result

    def delete(self, table: str, rid: str) -> None:
        t = TABLES[table]
        rec = self.get(table, rid)
        if rec is None:
            raise WorkbenchError(f"{rid} 기록이 없습니다.")
        self.rows(table).remove(rec)
        self.log(table, rid, "삭제", json.dumps({k: v for k, v in rec.items() if not k.startswith('_')},
                                              ensure_ascii=False), "", "화면 삭제")
        self.save(f"{t.title} 삭제 {rid}")

    def log(self, table: str, rid: str, key: str, before: str, after: str, reason: str) -> None:
        self.data["history"].append({"시각": now(), "표": table, "ID": rid, "칸": key,
                                     "이전": before, "이후": after, "사유": reason})

    # --- CSV
    def export_csv(self, table: str, path: Path | None = None) -> Path:
        t = TABLES[table]
        out = Path(path) if path else self.output_dir() / f"{t.title.split(' ', 1)[-1]}_{self.mode}.csv"
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(t.keys + ["데이터구분"])
        for r in self.rows(table):
            w.writerow([r.get(k, "") for k in t.keys] + [self.mode])
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(buf.getvalue(), encoding="utf-8-sig")
        except OSError as e:
            raise WorkbenchError(f"CSV를 저장하지 못했습니다: {e}\n→ 엑셀에서 같은 파일이 열려 있으면 닫고 다시 하세요.")
        return out

    def export_template(self, table: str, path: Path | None = None) -> Path:
        """빈 양식 + 예시 한 줄 + 작성 안내 한 줄."""
        t = TABLES[table]
        out = Path(path) if path else self.output_dir() / f"양식_{t.title.split(' ', 1)[-1]}.csv"
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(t.keys + ["데이터구분"])
        w.writerow([("[안내] " + f.help) if f.help else "" for f in t.fields] + ["[안내] 이 두 줄은 지우고 쓰세요"])
        w.writerow([f.example for f in t.fields] + ["예시"])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(buf.getvalue(), encoding="utf-8-sig")
        return out

    @staticmethod
    def _read_csv_text(path: Path) -> str:
        if not Path(path).exists():
            raise WorkbenchError(f"파일이 없습니다: {path}")
        try:
            raw = Path(path).read_bytes()
        except OSError as e:
            raise WorkbenchError(f"파일을 열 수 없습니다: {e}\n→ 엑셀에서 열려 있으면 닫고 다시 하세요.")
        for enc in ("utf-8-sig", "cp949"):
            try:
                return raw.decode(enc)
            except UnicodeDecodeError:
                pass
        raise WorkbenchError("글자 인코딩을 읽을 수 없습니다.\n→ 엑셀에서 'CSV UTF-8'로 다시 저장하세요.")

    def import_csv(self, table: str, path: Path) -> dict:
        """전부 검사한 뒤 문제없을 때만 넣는다(일부만 들어가는 일 없음). 중복 줄은 건너뛰고 알려 준다.
        양식에 없는 열은 버리지 않고 '_extra'에 보관한다(기존 1.0 자료 보존)."""
        t = TABLES[table]
        text = self._read_csv_text(path)
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise WorkbenchError("첫 줄(열 제목)이 없습니다.")
        headers = [h.strip() for h in reader.fieldnames]
        mapping = {}
        for h in headers:
            k = h if h in t.keys else t.aliases.get(h)
            if k:
                mapping[h] = k
        if not any(v in t.keys for v in mapping.values()):
            raise WorkbenchError(f"이 파일의 열 제목이 '{t.title}' 양식과 하나도 맞지 않습니다.\n"
                                 f"→ '양식 내보내기'로 받은 파일 제목을 쓰세요. 필요한 제목: {', '.join(t.keys)}")
        prepared, errors, skipped = [], [], []
        seen = set()
        for n, row in enumerate(reader, start=2):
            row = {(k or "").strip(): (v or "").strip() for k, v in row.items() if k is not None}
            if not any(row.values()) or any(str(v).startswith("[안내]") for v in row.values()):
                continue
            kind = row.get("데이터구분", "")
            if kind and kind not in MODES:
                errors.append(f"{n}번째 줄: 데이터구분 '{kind}'는 예시/실제 중 하나여야 합니다.")
                continue
            if kind and kind != self.mode:
                errors.append(f"{n}번째 줄: '{kind}' 자료입니다. 지금은 '{self.mode}' 모드라 섞을 수 없습니다.")
                continue
            vals = {mapping[h]: v for h, v in row.items() if h in mapping}
            extra = {h: v for h, v in row.items() if h not in mapping and h != "데이터구분" and v}
            try:
                rec = self.validate(table, vals)
            except WorkbenchError as e:
                errors.append(f"{n}번째 줄: {e}".split("\n")[0])
                continue
            key = self._dedupe_key(t, rec)
            rid = rec[t.id_field]
            if (rid and self.get(table, rid)) or (key and (key in seen or self.find_duplicate(table, rec))):
                skipped.append(n)
                continue
            if key:
                seen.add(key)
            rec["_extra"] = extra
            prepared.append(rec)
        if errors:
            raise WorkbenchError("가져오지 않았습니다. 아래 줄을 고친 뒤 다시 가져오세요.\n" + "\n".join(errors[:20])
                                 + ("\n…" if len(errors) > 20 else ""))
        for rec in prepared:
            self.upsert(table, rec, reason=f"CSV 가져오기 {Path(path).name}", save=False)
        self.save(f"{t.title} CSV 가져오기")
        return {"added": len(prepared), "skipped_duplicate_lines": skipped}

    # --- 백업·복원
    def backup_zip(self, dest_dir: Path | None = None) -> Path:
        self.save("수동 백업 전 저장")
        d = Path(dest_dir) if dest_dir else default_output() / "백업"
        d.mkdir(parents=True, exist_ok=True)
        out = d / f"작업실백업_{self.mode}_{dt.datetime.now():%Y%m%d_%H%M%S}.zip"
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(self.path, "workbench.json")
        return out

    def restore(self, src: Path) -> Path:
        """zip 또는 json 백업으로 되돌린다. 되돌리기 전 지금 상태를 먼저 백업한다."""
        src = Path(src)
        try:
            if src.suffix.lower() == ".zip":
                with zipfile.ZipFile(src) as z:
                    raw = z.read("workbench.json").decode("utf-8")
            else:
                raw = src.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, KeyError, zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError) as e:
            raise WorkbenchError(f"백업 파일을 읽지 못했습니다: {e}\n→ 작업실백업_*.zip 또는 backups 폴더의 workbench_*.json 을 고르세요.")
        if data.get("mode") != self.mode:
            raise WorkbenchError(f"이 백업은 '{data.get('mode')}' 자료입니다. 지금 모드('{self.mode}')와 달라 복원하지 않았습니다.\n"
                                 "→ 시작 화면에서 모드를 바꾼 뒤 복원하세요.")
        safety = self.backup_zip()
        self.data = data
        self.save(f"복원: {src.name}")
        return safety
