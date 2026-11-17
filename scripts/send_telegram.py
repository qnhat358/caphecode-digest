#!/usr/bin/env python3
"""Gửi bản tin (HTML kiểu Telegram) tới chat.

    send_telegram.py out/digest.html   gửi file, tự chia nhỏ nếu dài quá 4000 ký tự
    send_telegram.py --chat-id         in chat id của những ai vừa nhắn cho bot

Cần biến môi trường TELEGRAM_BOT_TOKEN, và TELEGRAM_CHAT_ID khi gửi.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

LIMIT = 4000  # Telegram cho tối đa 4096 ký tự mỗi tin


def api(method, **params):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/{method}",
                                 data=urllib.parse.urlencode(params).encode())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}") | {"ok": False, "status": e.code}


def chunks(text):
    """Chia theo đoạn (dòng trống) để không cắt ngang thẻ HTML; đoạn nào quá dài thì chia theo dòng."""
    parts, current = [], ""
    for block in re.split(r"\n\s*\n", text.strip()):
        pieces = [block] if len(block) <= LIMIT else block.splitlines()
        for piece in pieces:
            if current and len(current) + len(piece) + 2 > LIMIT:
                parts.append(current)
                current = ""
            current = f"{current}\n\n{piece}" if current else piece[:LIMIT]
    return parts + [current] if current else parts


def send(chat_id, text):
    res = api("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML", disable_web_page_preview="true")
    if not res.get("ok") and "parse entities" in res.get("description", ""):
        # HTML hỏng thì vẫn gửi bản chữ thường, còn hơn mất cả bản tin
        plain = re.sub(r"<[^>]+>", "", text).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
        res = api("sendMessage", chat_id=chat_id, text=plain, disable_web_page_preview="true")
    return res


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    if sys.argv[1] == "--chat-id":
        res = api("getUpdates")
        chats = {u["message"]["chat"]["id"]: u["message"]["chat"] for u in res.get("result", []) if "message" in u}
        if not chats:
            sys.exit(f"Chưa thấy tin nhắn nào. Nhắn một câu cho bot rồi chạy lại. ({res.get('description', '')})")
        for cid, chat in chats.items():
            print(cid, chat.get("username") or chat.get("title") or chat.get("first_name"))
        return

    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    parts = chunks(open(sys.argv[1], encoding="utf-8").read())
    for i, part in enumerate(parts, 1):
        res = send(chat_id, part)
        if not res.get("ok"):
            sys.exit(f"Gửi phần {i}/{len(parts)} thất bại: {res}")
    print(f"Đã gửi {len(parts)} tin.")


if __name__ == "__main__":
    main()
