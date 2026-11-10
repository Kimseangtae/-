"""
content-hub: 공식 API 로 자동 발행하고 성과를 가져오는 모듈.

자동 발행되는 곳 (공식 API)
  threads   : 글. Threads API (graph.threads.net). 토큰은 `hub.py set-threads-token` 으로 저장.
  instagram : 이미지 1장 또는 캐러셀(2~10장). Instagram Graph API. 토큰은 gongu-lab 의 `ig_collect.py --set-token` 것을 같이 쓴다.
              이미지는 인터넷에서 열리는 JPEG 주소(image_url)여야 한다. 권한 instagram_content_publish 필요.
  facebook  : 인스타와 연결된 페이스북 페이지에 글(+링크 또는 사진 1장). 같은 토큰. 권한 pages_manage_posts 필요.

자동 발행하지 않는 곳 (수동 알림만)
  유튜브(쇼츠·롱폼·커뮤니티·고정댓글), 릴스 영상, 틱톡. 이유는 README '한계' 참고.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "gongu-lab"))

THREADS_API = "https://graph.threads.net/v1.0/"
THREADS_TOKEN_FILE = HERE / ".threads_token.json"
THREADS_MAX = 500
IG_VERSION = os.environ.get("IG_GRAPH_VERSION", "v25.0")
UA = "content-hub/1.0"


class PublishError(RuntimeError):
    pass


def _request(method: str, url: str, params: dict) -> dict:
    data = urllib.parse.urlencode(params).encode() if method == "POST" else None
    if method == "GET":
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise PublishError(f"{e.code}: {e.read().decode('utf-8', errors='replace')[:300]}") from e
    except urllib.error.URLError as e:
        raise PublishError(f"연결 실패: {e}") from e


# ---------------------------------------------------------------- Threads

def threads_creds() -> dict:
    saved = json.loads(THREADS_TOKEN_FILE.read_text(encoding="utf-8")) if THREADS_TOKEN_FILE.exists() else {}
    return {"token": saved.get("token") or os.environ.get("THREADS_ACCESS_TOKEN", ""),
            "user_id": saved.get("user_id") or os.environ.get("THREADS_USER_ID", "")}


def threads_save(token: str, user_id: str, username: str = "", expires_in: int | None = None) -> None:
    THREADS_TOKEN_FILE.write_text(json.dumps({
        "token": token, "user_id": user_id, "username": username, "saved_at": int(time.time()),
        "expires_at": int(time.time()) + expires_in if expires_in else None}, ensure_ascii=False, indent=2), encoding="utf-8")


def threads_long_lived(short_token: str, app_secret: str) -> tuple[str, int | None]:
    """짧은 토큰 → 60일 토큰. 시크릿은 이 호출에만 쓰고 저장하지 않는다."""
    r = _request("GET", "https://graph.threads.net/access_token",
                 {"grant_type": "th_exchange_token", "client_secret": app_secret, "access_token": short_token})
    return r["access_token"], r.get("expires_in")


def threads_refresh_if_old(days: int = 30) -> str:
    """저장한 지 days 일이 지난 60일 토큰을 새로 고친다(만료 전, 발급 24시간 뒤부터 가능)."""
    if not THREADS_TOKEN_FILE.exists():
        return "토큰 파일 없음"
    saved = json.loads(THREADS_TOKEN_FILE.read_text(encoding="utf-8"))
    if time.time() - saved.get("saved_at", 0) < days * 86400:
        return "갱신 불필요"
    r = _request("GET", "https://graph.threads.net/refresh_access_token",
                 {"grant_type": "th_refresh_token", "access_token": saved["token"]})
    threads_save(r["access_token"], saved["user_id"], saved.get("username", ""), r.get("expires_in"))
    return "스레드 토큰을 새로 고쳤습니다"


def threads_me(token: str) -> dict:
    return _request("GET", THREADS_API + "me", {"fields": "id,username", "access_token": token})


def threads_publish(text: str) -> dict:
    c = threads_creds()
    if not (c["token"] and c["user_id"]):
        raise PublishError("스레드 토큰이 없습니다. `hub.py set-threads-token` 으로 저장하세요.")
    if len(text) > THREADS_MAX:
        raise PublishError(f"스레드 글은 {THREADS_MAX}자까지입니다 (지금 {len(text)}자).")
    box = _request("POST", f"{THREADS_API}{c['user_id']}/threads",
                   {"media_type": "TEXT", "text": text, "access_token": c["token"]})
    time.sleep(2)  # 컨테이너 준비 시간
    pub = _request("POST", f"{THREADS_API}{c['user_id']}/threads_publish",
                   {"creation_id": box["id"], "access_token": c["token"]})
    link = ""
    try:
        link = _request("GET", THREADS_API + pub["id"], {"fields": "permalink", "access_token": c["token"]}).get("permalink", "")
    except PublishError:
        pass
    return {"media_id": pub["id"], "url": link}


def threads_insights(media_id: str) -> dict:
    c = threads_creds()
    data = _request("GET", f"{THREADS_API}{media_id}/insights",
                    {"metric": "views,likes,replies,reposts,quotes", "access_token": c["token"]})
    return {m["name"]: (m.get("values") or [{}])[0].get("value", m.get("total_value", {}).get("value")) for m in data.get("data", [])}


# ---------------------------------------------------------------- Instagram

def ig_creds() -> dict:
    from ig_collect import load_creds  # gongu-lab 의 저장된 토큰 사용
    return load_creds()


def ig_creds_quiet() -> dict:
    """토큰 확인용. 계정 ID 를 찾으러 네트워크에 나가지 않는다(저장된 값·환경변수만)."""
    try:
        from ig_collect import load_creds
        return load_creds(resolve=False)
    except Exception:
        return {}


def _ig(path: str) -> str:
    return f"https://graph.facebook.com/{IG_VERSION}/{path}"


def ig_wait(container_id: str, token: str, tries: int = 10) -> None:
    for _ in range(tries):
        st = _request("GET", _ig(container_id), {"fields": "status_code", "access_token": token}).get("status_code")
        if st in ("FINISHED", None):
            return
        if st == "ERROR":
            raise PublishError("인스타가 이미지를 처리하지 못했습니다 (이미지 주소·형식 확인: JPEG, 인터넷에서 열리는 주소).")
        time.sleep(3)
    raise PublishError("인스타 처리 대기 시간이 지났습니다.")


def ig_publish(image_urls: list[str], caption: str) -> dict:
    c = ig_creds()
    if not (c.get("token") and c.get("ig_user_id")):
        raise PublishError("인스타 토큰이 없습니다. `python gongu-lab/ig_collect.py --set-token` 으로 저장하세요.")
    if not image_urls:
        raise PublishError("인스타 발행에는 인터넷에서 열리는 이미지 주소가 필요합니다.")
    if len(image_urls) > 10:
        raise PublishError("캐러셀은 10장까지입니다.")
    tok, uid = c["token"], c["ig_user_id"]
    if len(image_urls) == 1:
        box = _request("POST", _ig(f"{uid}/media"), {"image_url": image_urls[0], "caption": caption, "access_token": tok})
    else:
        children = []
        for u in image_urls:
            item = _request("POST", _ig(f"{uid}/media"), {"image_url": u, "is_carousel_item": "true", "access_token": tok})
            ig_wait(item["id"], tok)
            children.append(item["id"])
        box = _request("POST", _ig(f"{uid}/media"),
                       {"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption, "access_token": tok})
    ig_wait(box["id"], tok)
    pub = _request("POST", _ig(f"{uid}/media_publish"), {"creation_id": box["id"], "access_token": tok})
    link = ""
    try:
        link = _request("GET", _ig(pub["id"]), {"fields": "permalink", "access_token": tok}).get("permalink", "")
    except PublishError:
        pass
    return {"media_id": pub["id"], "url": link}


def ig_insights(media_id: str) -> dict:
    tok = ig_creds()["token"]
    for metrics in ("reach,likes,comments,saved,shares", "reach,likes,comments,saved", "reach,saved"):
        try:
            data = _request("GET", _ig(f"{media_id}/insights"), {"metric": metrics, "access_token": tok})
            return {m["name"]: (m.get("values") or [{}])[0].get("value", m.get("total_value", {}).get("value")) for m in data.get("data", [])}
        except PublishError:
            continue
    raise PublishError("인스타 성과를 가져오지 못했습니다 (토큰에 instagram_manage_insights 권한 필요).")


# ---------------------------------------------------------------- Facebook 페이지

def fb_page() -> dict:
    """인스타와 연결된 페이지의 id·이름·페이지 토큰. 토큰은 메모리에서만 쓴다."""
    c = ig_creds()
    if not c.get("token"):
        raise PublishError("토큰이 없습니다. `python gongu-lab/ig_collect.py --set-token` 으로 저장하세요.")
    pages = _request("GET", _ig("me/accounts"), {"fields": "id,name,access_token,instagram_business_account",
                                                 "access_token": c["token"]}).get("data", [])
    for p in pages:
        if (p.get("instagram_business_account") or {}).get("id") == c.get("ig_user_id"):
            return p
    if len(pages) == 1:
        return pages[0]
    raise PublishError("인스타와 연결된 페이스북 페이지를 찾지 못했습니다.")


def fb_publish(message: str, link: str = "", image_url: str = "") -> dict:
    p = fb_page()
    if image_url:
        r = _request("POST", _ig(f"{p['id']}/photos"), {"url": image_url, "caption": message, "access_token": p["access_token"]})
        pid = r.get("post_id") or r["id"]
    else:
        params = {"message": message, "access_token": p["access_token"]}
        if link:
            params["link"] = link
        pid = _request("POST", _ig(f"{p['id']}/feed"), params)["id"]
    return {"media_id": pid, "url": f"https://www.facebook.com/{pid}"}


def fb_insights(post_id: str) -> dict:
    p = fb_page()
    d = _request("GET", _ig(post_id), {"fields": "shares,reactions.summary(true),comments.summary(true)",
                                        "access_token": p["access_token"]})
    return {"reactions": (d.get("reactions") or {}).get("summary", {}).get("total_count"),
            "comments": (d.get("comments") or {}).get("summary", {}).get("total_count"),
            "shares": (d.get("shares") or {}).get("count", 0)}
