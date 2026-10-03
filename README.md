# Code Challenge for CTFd

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CTFd](https://img.shields.io/badge/CTFd-3.8.x-blue.svg)](https://github.com/CTFd/CTFd)
[![Judge0](https://img.shields.io/badge/Judge0-CE%201.13.1+-green.svg)](https://github.com/judge0/judge0)

> **English**: Custom challenge type for CTFd. Players write code in the browser. CTFd sends code to Judge0, compares output with test cases, and records a solve when every test passes.
>
> **Tiếng Việt**: Plugin thêm challenge type **Code Challenge** cho CTFd. Người chơi viết code trên trình duyệt. CTFd gửi code sang Judge0, so output với test case, và ghi solve khi mọi test đạt.

---

## Quick Links / Liên kết nhanh

| File | Mô tả | Link |
|------|-------|------|
| **HUONG-DAN.md** | Hướng dẫn chi tiết tiếng Việt (cài đặt, cấu hình, tạo bài, sửa lỗi) | [Đọc](HUONG-DAN.md) |
| **CAI-DAT.md** | Tài liệu cài đặt tiếng Việt (chuẩn bị máy, cài Judge0, CTFd, plugin) | [Đọc](CAI-DAT.md) |
| **LICENSE** | MIT License | [Đọc](LICENSE) |

---

## Table of Contents / Mục lục

- [Features / Tính năng](#features--tính-năng)
- [Requirements / Yêu cầu](#requirements--yêu-cầu)
- [Installation / Cài đặt](#installation--cài-đặt)
  - [1. Install Judge0 / Cài Judge0](#1-install-judge0--cài-judge0)
  - [2. Install CTFd / Cài CTFd](#2-install-ctfd--cài-ctfd)
  - [3. Install Plugin / Cài plugin](#3-install-plugin--cài-plugin)
  - [4. Configure Judge0 URL / Cấu hình URL Judge0](#4-configure-ctfd-code-url--cấu-hình-url-judge0)
- [Quick Start / Hướng dẫn nhanh](#quick-start--hướng-dẫn-nhanh)
- [Configuration / Cấu hình chi tiết](#configuration--cấu-hình-chi-tiết)
- [API Reference / Tài liệu API](#api-reference--tài-liệu-api)
- [Troubleshooting / Sửa lỗi](#troubleshooting--sửa-lỗi)
- [Security Notes / Ghi chú bảo mật](#security-notes--ghi-chú-bảo-mật)
- [Documentation / Tài liệu](#documentation--tài-liệu)
- [License / Giấy phép](#license--giấy-phép)
- [Credits / Công trạng](#credits--công-trạng)

---

## Features / Tính năng

- **Browser code editor** — CodeMirror 5.65.18, no CDN, works offline
- **7 languages** — Python 3, C, C++, Java, JavaScript, Go, Rust
- **Sample + hidden test cases** — Sample shown to player, hidden only on Submit
- **Run Code / Submit** — Run tests sample only (no score), Submit tests all (records solve)
- **Rate limiting** — 12 runs/min, 6 submits/min per challenge
- **Server-side grading** — Browser never talks to Judge0
- **No flag required** — Solve recorded via plugin's own grading

---

## Requirements / Yêu cầu

| Component | Version |
|-----------|---------|
| CTFd | 3.8.x (verified: 3.8.6-9-g006b7274) |
| Judge0 CE | 1.13.1+ |
| Docker | 20.10+ |
| Docker Compose | 2.0+ |
| OS | Ubuntu 24.04 (recommended) |

---

## Installation / Cài đặt

### 1. Install Judge0 / Cài Judge0

> **Chi tiết**: Xem [CAI-DAT.md Phần 2](CAI-DAT.md#phần-2-cài-judge0-ce-1131) — Hướng dẫn cài Judge0 chi tiết tiếng Việt

```bash
cd ~
wget https://github.com/judge0/judge0/releases/download/v1.13.1/judge0-v1.13.1.zip
unzip judge0-v1.13.1.zip
cd judge0-v1.13.1
docker compose up -d
```

Verify Judge0 is running / Kiểm tra Judge0 đang chạy:

```bash
curl -s http://127.0.0.1:2358/languages | head -c 200
```

Expected: JSON with language list, Python 3 has `"id":71`.

### 2. Install CTFd / Cài CTFd

> **Chi tiết**: Xem [CAI-DAT.md Phần 3](CAI-DAT.md#phần-3-cài-ctfd) — Hướng dẫn cài CTFd chi tiết tiếng Việt

```bash
cd ~
git clone https://github.com/CTFd/CTFd.git
cd CTFd
git checkout 3.8.6
docker compose up -d
```

CTFd 3.8 already has `docker-compose.yml` at the repo root. There is no `conf/examples/docker-compose.dev.yml`. The `ctfd` service bind-mounts the repo (`.:/opt/CTFd:ro`), so plugin edits are picked up by `docker compose restart ctfd`. Do not rebuild the image for this plugin.

Open `http://<host-ip>:8000` and complete setup (admin account, CTF name, mode).

### 3. Install Plugin / Cài plugin

> **Chi tiết**: Xem [HUONG-DAN.md Mục 1](HUONG-DAN.md#1-cài-plugin) và [CAI-DAT.md Phần 4](CAI-DAT.md#phần-4-cài-plugin) — Hướng dẫn cài plugin chi tiết tiếng Việt

The download may be named `ctfd_codechallenger`. CTFd imports whatever the directory is called, and this plugin's URLs, migration key, and challenge type are `ctfd_code`. The installed directory must be named `ctfd_code`. A copy left as `ctfd_codechallenger` does not load and does not serve `/plugins/ctfd_code/...`.

```bash
rm -rf ~/CTFd/CTFd/plugins/ctfd_code
cp -a /path/to/ctfd_codechallenger ~/CTFd/CTFd/plugins/ctfd_code
```

Do not leave both directories in `CTFd/plugins/`. Restart CTFd (no image rebuild; the repo is bind-mounted) and verify:

```bash
cd ~/CTFd
docker compose restart ctfd
docker compose logs --since 2m ctfd | grep -i ctfd_code
```

Expected log line:

```
Loaded module, <module 'CTFd.plugins.ctfd_code' from '/opt/CTFd/CTFd/plugins/ctfd_code/__init__.py'>
```

Verify tables created / Kiểm tra bảng đã tạo:

```bash
docker compose exec db mariadb -uctfd -pctfd ctfd -e "SHOW TABLES LIKE 'ctfd_code%';"
```

Expected: `ctfd_code_challenge` and `ctfd_code_test_case`.

### 4. Configure Judge0 URL / Cấu hình URL Judge0

> **Chi tiết**: Xem [HUONG-DAN.md Mục 2](HUONG-DAN.md#2-đặt-url-judge0) và [CAI-DAT.md Phần 5](CAI-DAT.md#phần-5-nối-ctfd-với-judge0) — Hướng dẫn cấu hình URL chi tiết tiếng Việt

**URL priority** (first non-empty wins):

1. Per-challenge URL (in challenge form)
2. Global URL (Admin → Judge0)
3. Environment variable `JUDGE0_URL`

**Via Admin UI**:

1. Open `http://<host-ip>:8000/plugins/ctfd_code/admin/settings`
2. Enter `http://<host-ip>:2358`
3. Leave token empty (Judge0 local, no auth)
4. Click **Save**

**Via environment variable** — add to `docker-compose.yml` under `ctfd.environment`:

```yaml
- JUDGE0_URL=http://192.168.75.136:2358
```

Then `docker compose up -d ctfd`.

**Verify connectivity from inside container**:

```bash
docker compose exec ctfd python -c "import urllib.request; print(urllib.request.urlopen('http://192.168.75.136:2358/languages', timeout=5).status)"
```

Expected: `200`.

### Docker networking / Mạng Docker

| Judge0 location | URL for CTFd |
|-----------------|--------------|
| Published on host, port 2358 | `http://<host-ip>:2358` |
| Another compose, same network | `http://<service-name>:2358` |
| Same compose file | `http://server:2358` |

**Do not use** `localhost` or `127.0.0.1` inside container — that's the CTFd container itself.

---

## Quick Start / Hướng dẫn nhanh

### Create a challenge / Tạo một bài

> **Chi tiết**: Xem [HUONG-DAN.md Mục 3](HUONG-DAN.md#3-tạo-một-bài) và [CAI-DAT.md Phần 7](CAI-DAT.md#phần-7-tạo-một-bài) — Hướng dẫn tạo bài chi tiết tiếng Việt

1. **Admin Panel → Challenges → Create Challenge**
2. Challenge type: **Code Challenge**
3. Fill: Name, Category, Message, Value
4. Click **Create** (no flag needed)
5. Open the challenge, set on right-hand form:
   - Judge0 URL: leave blank (use global)
   - CPU time limit: `2`
   - Memory limit (KB): `128000`
   - Comparison: `trim`
   - Languages: enable Python 3
   - Starter code: optional
6. Click **Update**
7. Scroll to **Test cases**, click **Add test case**:

   **Test 1 (Sample)**:
   - Name: `sample`
   - Input: `2 3`
   - Expected output: `5`
   - Tick **Sample**
   - Click **Save** on this card

   **Test 2 (Hidden)**:
   - Name: `hidden`
   - Input: `10 20`
   - Expected output: `30`
   - Do NOT tick Sample
   - Click **Save** on this card

### Play as user / Chơi thử

> **Chi tiết**: Xem [HUONG-DAN.md Mục 3 → Chơi thử](HUONG-DAN.md#chơi-thử) và [CAI-DAT.md Phần 8](CAI-DAT.md#phần-8-làm-thử-với-tư-cách-người-chơi) — Hướng dẫn chơi thử chi tiết tiếng Việt

1. Log out admin, login as regular user
2. Open the challenge you just created (this doc calls it **Sum**). A challenge already on the CTF may have a different name.
3. Select **Python 3**
4. Enter code (no leading spaces):

   ```python
   a, b = map(int, input().split())
   print(a + b)
   ```

5. **Run Code** — tests sample only, shows Accepted, no score recorded
6. **Submit** — tests all, shows 2/2, challenge solved, +100 points

**Ctrl+Enter** also runs the code.

---

## Configuration / Cấu hình chi tiết

### Language IDs / ID ngôn ngữ

> **Chi tiết**: Xem [HUONG-DAN.md Mục 5](HUONG-DAN.md#5-ngôn-ngữ) — Hướng dẫn ngôn ngữ chi tiết tiếng Việt

| Language | Slug | ID |
|----------|------|----|
| Python 3 | `python3` | 71 |
| C | `c` | 50 |
| C++ | `cpp` | 54 |
| Java | `java` | 62 |
| JavaScript | `javascript` | 63 |
| Go | `go` | 60 |
| Rust | `rust` | 73 |

These are Judge0 CE 1.13.1 defaults. After upgrading Judge0, re-check `/languages`.

### Comparison modes / Chế độ so sánh

| Mode | Rule |
|------|------|
| `trim` (default) | CRLF → LF, strip trailing whitespace per line, ignore one final newline, exact match |
| `exact` | CRLF → LF, then exact match |
| `whitespace-insensitive` | Collapse every whitespace run to single space, then exact match |

Judge0's "Accepted" only means exit code 0. Wrong Answer is decided by CTFd plugin.

### Limits / Giới hạn

| Item | Limit |
|------|-------|
| Source code | 64 KB |
| One test stdin | 64 KB |
| Starter code | 16 KB per language |
| Test cases | 50 per challenge |
| CPU time | 0.1 – 15 seconds |
| Memory | 2048 – 512000 KB |
| Run | 12 per account per challenge per minute |
| Submit | 6 per account per challenge per minute |

---

## API Reference / Tài liệu API

All POST bodies are JSON. CTFd's `CSRF-Token` header is required.

### POST /plugins/ctfd_code/run/<challenge_id>

```json
{
  "language": "python3",
  "source_code": "print(1)"
}
```

Response:

```json
{
  "success": true,
  "solved": false,
  "status": "Accepted",
  "passed": 1,
  "total": 1,
  "stdout": "5\n",
  "stderr": "",
  "time": "0.019",
  "memory": 8064,
  "cases": []
}
```

### POST /plugins/ctfd_code/submit/<challenge_id>

```json
{
  "language": "python3",
  "source_code": "print(1)"
}
```

Response:

```json
{
  "success": false,
  "solved": false,
  "status": "Wrong Answer",
  "message": "Wrong Answer (2/5 tests)",
  "passed": 2,
  "total": 5,
  "cases": [
    { "name": "Sample 1", "sample": true, "passed": true, "status": "Accepted", "stdout": "5\n", "stdin": "2 3\n", "expected_output": "5\n" },
    { "name": "Hidden 2", "sample": false, "passed": false, "status": "Wrong Answer" }
  ]
}
```

Hidden cases have no `stdin`, `expected_output`, `stdout`, or `stderr`.

---

## Troubleshooting / Sửa lỗi

> **Chi tiết**: Xem [HUONG-DAN.md Mục 6](HUONG-DAN.md#6-sửa-lỗi) và [CAI-DAT.md Phần 11](CAI-DAT.md#phần-11-bảng-tra-lỗi-lúc-cài) — Hướng dẫn sửa lỗi chi tiết tiếng Việt

| Symptom | Cause | Fix |
|---------|-------|-----|
| No "Code Challenge" type | Plugin not loaded | `docker compose logs ctfd \| grep -i ctfd_code`. Restart after fix |
| Save URL but page becomes `?ctfd_code_url=` | Form sent GET | Ctrl+F5, Save again, must see **Saved.** |
| Run/Submit 400 "Judge0 URL is not configured" | All three URL sources empty | Configure URL (see Installation → step 4) |
| Connection refused | URL is `localhost` or `127.0.0.1` | Use host IP. `docker ps` must show `0.0.0.0:2358->2358/tcp` |
| Timeout, Internal Error | Judge0 worker not running | `docker ps` must show `workers` container Up |
| First Run is Time Limit Exceeded, stdout is already correct, retry is Accepted in well under the CPU limit | Worker was cold (first job after idle) | Run again. Not a wrong answer |
| 401/403 from Judge0 | Judge0 auth enabled, no token | Set token in Admin → Judge0 or `JUDGE0_API_TOKEN` |
| 403 from CTFd | Not logged in, CTF paused, or no team | Login with valid user |
| CORS error in console | Other page calling Judge0 directly | Ignore if Run/Submit on CTFd works |
| Runtime Error (NZEC) with Python | IndentationError or SyntaxError | Check code, retype from column 0 |
| Wrong Answer but output looks correct | Extra spaces, missing newline | `trim` only strips trailing whitespace per line |
| Accepted on Run but Wrong Answer on Submit | Hidden test differs from sample | Fix for full problem, not just sample |
| "Too many runs" / "Too many submissions" | Rate limit hit | Wait ~1 minute |
| Editor not showing, only textarea | Browser cache or missing CodeMirror | Ctrl+F5. Textarea still works |
| Plugin code changes not visible | Python cached | `docker compose restart ctfd` |
| Tables missing or 500 on challenge | Migration not run | Check startup log, restart. Don't insert into `challenges` manually |

---

## Security Notes / Ghi chú bảo mật

- **No `eval`, `exec`, `subprocess`, or `shell=True`** on submitted code
- **Language from fixed slug map** — client never forwards user-supplied language ID
- **Source not logged** — only `challenge_id`, `language_id`, test count, status
- **Judge0 URL and token not in player config payload**
- **Hidden tests not leaked** — `read()` adds `test_cases` only for admins

---

## Documentation / Tài liệu

- **[HUONG-DAN.md](HUONG-DAN.md)** — Hướng dẫn chi tiết tiếng Việt (cài đặt, cấu hình, tạo bài, sửa lỗi)
- **[CAI-DAT.md](CAI-DAT.md)** — Tài liệu cài đặt tiếng Việt (chuẩn bị máy, cài Judge0, CTFd, plugin)

---

## License / Giấy phép

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

Dự án này được cấp phép theo MIT License — xem [LICENSE](LICENSE) để biết chi tiết.

---

## Credits / Công trạng

- **Author**: Kiraly
- **CTFd**: [CTFd/CTFd](https://github.com/CTFd/CTFd)
- **Judge0**: [judge0/judge0](https://github.com/judge0/judge0)
- **CodeMirror**: [codemirror/codemirror5](https://github.com/codemirror/codemirror5)
