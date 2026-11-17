# daily-tech-digest

Mỗi sáng, một scheduled task của Claude Code chạy trên cloud gom tin AI/IT, chọn khoảng 10–15 tin, tóm tắt bằng tiếng Việt rồi gửi qua Telegram.

- `scripts/fetch.py`: lấy tin từ Hacker News, Lobsters, Reddit, GitHub Trending, HF Daily Papers và các RSS feed, ghi ra `out/candidates.json`.
- `ROUTINE.md`: hướng dẫn cho agent: chọn tin, viết bản tin, gửi đi.
- `scripts/send_telegram.py`: gửi `out/digest.html`, tự chia khi dài quá 4000 ký tự.
- `config/sources.json`: danh sách nguồn. `config/interests.md`: sở thích, chỉnh để bản tin hợp gu hơn.

## Chạy tay

```sh
python3 scripts/fetch.py
export TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...
python3 scripts/send_telegram.py out/digest.html
python3 scripts/send_telegram.py --chat-id   # tìm chat id sau khi nhắn cho bot
```

## Cấu hình môi trường cloud

- Biến môi trường: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.
- Network access **Limited**, Allowed domains:

```
api.telegram.org
hn.algolia.com
lobste.rs
www.reddit.com
huggingface.co
openai.com
deepmind.google
blog.google
simonwillison.net
www.latent.space
www.theverge.com
techcrunch.com
blog.pragmaticengineer.com
```

Thêm nguồn mới vào `config/sources.json` thì nhớ thêm domain vào danh sách trên. Muốn đỡ phải nhớ thì chọn **Full**, nhưng Full kém an toàn hơn.
