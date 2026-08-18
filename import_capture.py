#!/usr/bin/env python3
"""import_capture.py — วาง "Copy all as cURL" จาก DevTools ทั้งกอง แล้วสคริปต์ดึง
request ที่มี token ให้เอง (ไม่ต้องหา request เดียวเอง) → เซฟ capture → add + verify.

ใช้ (บนเครื่องเจ้าของ):
  เปิด chatgpt.com > DevTools > Network > ส่งข้อความสั้น ๆ 1 ที > คลิกขวาที่ request
  ไหนก็ได้ > Copy > "Copy all as cURL" แล้ว:
      pbpaste | python3 ~/Desktop/chatgpt-api/import_capture.py
  หรือวางมือ:
      python3 ~/Desktop/chatgpt-api/import_capture.py    (แล้ววาง จบด้วย Ctrl-D)

เลือก request ตามลำดับความดี: f/conversation (ส่งข้อความจริง มี proof token) >
conversation/init > อันไหนก็ได้ที่มี Bearer + body JSON. capture เก็บเข้ารหัสใน
secrets/ (gitignore) โดย add flow ของ bridge เอง — สคริปต์นี้ไม่พิมพ์ token ออกจอ
"""
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

BRIDGE = Path(__file__).resolve().parent
ACCOUNT = os.environ.get("CAPTURE_ACCOUNT", "main")


def read_dump() -> str:
    # 1) path ไฟล์เป็น argv (รองรับ .har หรือ .txt) 2) stdin 3) pbpaste 4) .har ล่าสุดใน Downloads
    if len(sys.argv) > 1 and Path(sys.argv[1]).exists():
        return Path(sys.argv[1]).read_text(encoding="utf-8", errors="replace")
    data = ""
    if not sys.stdin.isatty():
        data = sys.stdin.read()
    if len(data.strip()) < 50:
        try:
            data = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
        except OSError:
            pass
    if len(data.strip()) < 50:
        hars = sorted(glob.glob(str(Path.home() / "Downloads" / "*.har")),
                      key=lambda p: Path(p).stat().st_mtime, reverse=True)
        if hars:
            print(f"(ใช้ HAR ล่าสุด: {Path(hars[0]).name})")
            return Path(hars[0]).read_text(encoding="utf-8", errors="replace")
    return data


def _q(v: str) -> str:
    return "'" + v.replace("'", "'\\''") + "'"       # ครอบ single-quote ให้ shlex อ่านได้


def har_to_blocks(text: str) -> list[str]:
    """แปลง HAR (Save all as HAR with content) เป็น curl block ต่อ 1 request."""
    try:
        entries = json.loads(text).get("log", {}).get("entries", [])
    except (json.JSONDecodeError, AttributeError):
        return []
    blocks = []
    for e in entries:
        req = e.get("request", {})
        url = req.get("url", "")
        if not url:
            continue
        parts = [f"curl {_q(url)}"]
        has_cookie = False
        for h in req.get("headers", []):
            name = (h.get("name") or "").strip()
            if not name or name.startswith(":"):   # ข้าม pseudo-header ของ HTTP/2
                continue
            if name.lower() == "cookie":
                has_cookie = True
            parts.append(f"-H {_q(name + ': ' + (h.get('value') or ''))}")
        if not has_cookie:                          # บาง HAR เก็บ cookie แยก array
            ck = "; ".join(f"{c.get('name')}={c.get('value')}" for c in req.get("cookies", []) if c.get("name"))
            if ck:
                parts.append(f"-b {_q(ck)}")
        body = (req.get("postData") or {}).get("text")
        if body:
            parts.append(f"--data-raw {_q(body)}")
        blocks.append(" \\\n  ".join(parts))
    return blocks


def split_curls(text: str) -> list[str]:
    # แต่ละคำสั่งขึ้นต้น "curl '" — ตัดตามขอบนั้น (รองรับทั้งกองจาก Copy all as cURL)
    parts = re.split(r"(?=curl '\S)", text)
    return [p.strip().rstrip(";").strip() for p in parts if p.strip().startswith("curl ")]


def first_url(block: str) -> str:
    m = re.search(r"curl '([^']+)'", block)
    return m.group(1) if m else ""


def score(block: str, url: str) -> int:
    low = block.lower()
    if not re.search(r"-h '?authorization:\s*bearer", low):
        return -1                              # ไม่มี token = ใช้ไม่ได้
    has_body = ("--data-raw" in block) or ("--data" in block) or ("-d '" in block)
    s = 0
    if "/backend-api/f/conversation" in url and "/prepare" not in url:
        s = 100                                # request ส่งข้อความจริง (ดีสุด: มี proof token)
    elif url.endswith("/backend-api/conversation/init"):
        s = 80
    elif "/backend-api/" in url:
        s = 40
    if has_body:
        s += 10                                # ต้องมี body JSON ให้ผ่านเกต required
    return s


def main() -> int:
    dump = read_dump()
    if len(dump.strip()) < 50:
        print("!! ไม่พบข้อมูล — วาง 'Copy all as cURL' ผ่าน pbpaste หรือ stdin", file=sys.stderr)
        return 2
    blocks = split_curls(dump)
    if not blocks and dump.lstrip().startswith("{"):
        blocks = har_to_blocks(dump)               # ไฟล์ HAR (Save all as HAR with content)
    if not blocks:
        print("!! อ่านไม่ออก — ต้องเป็น 'Copy all as cURL' หรือไฟล์ .har "
              "(Save all as HAR with content)", file=sys.stderr)
        return 2
    ranked = sorted(((score(b, first_url(b)), first_url(b), b) for b in blocks),
                    key=lambda x: x[0], reverse=True)
    best_score, best_url, best = ranked[0]
    if best_score < 0:
        print(f"!! ไม่มี request ไหนมี Bearer token เลย ({len(blocks)} curl) — "
              "ต้องก็อปตอนล็อกอินอยู่ และเลือกหน้า chat จริง", file=sys.stderr)
        return 3
    print(f"เลือก request: {best_url}  (จาก {len(blocks)} curl, score={best_score})")
    if best_score < 80:
        print("   [เตือน] ไม่พบ f/conversation หรือ conversation/init — ใช้ตัวสำรอง "
              "ถ้า verify ไม่ผ่าน ให้ส่งข้อความใน chatgpt แล้วก็อปใหม่", file=sys.stderr)

    key = ""
    for line in (BRIDGE / ".env").read_text().splitlines():
        if line.startswith("CHATGPT_API_KEY="):
            key = line.split("=", 1)[1].strip()
    if not key:
        print("!! อ่าน CHATGPT_API_KEY จาก .env ไม่ได้", file=sys.stderr)
        return 4

    tmp = Path(tempfile.mkstemp(prefix="cap_", suffix=".txt", dir=BRIDGE / "secrets")[1])
    try:
        tmp.write_text(best + "\n", encoding="utf-8")
        cmd = [str(BRIDGE / ".venv" / "bin" / "python"), "-m", "chatgpt_api",
               "admin", "account", "add", "--account", ACCOUNT,
               "--capture-file", str(tmp),
               "--base-url", "http://127.0.0.1:8001/v1", "--api-key", key]
        print(f"$ admin account add --account {ACCOUNT} (verify สด)...")
        rc = subprocess.run(cmd, cwd=BRIDGE).returncode
        return rc
    finally:
        try:
            tmp.write_bytes(b"\0" * tmp.stat().st_size)   # ลบร่องรอย token ในไฟล์ชั่วคราว
        except OSError:
            pass
        tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
