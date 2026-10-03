# Cài CTFd, Judge0 và plugin chấm bài code

Tài liệu này cho người mới. Đọc từ trên xuống một lần. Bạn sẽ biết từng thứ dùng để làm gì, cài ra sao, chúng nói chuyện với nhau thế nào, và tạo một bài code như thế nào.

Máy trong ví dụ là Ubuntu 24.04. IP host là `192.168.75.136`. Đổi IP đó thành IP máy bạn ở mọi chỗ bên dưới.

## Ba thành phần

Có ba phần, không phải hai.

```
Người chơi (trình duyệt)
        |
        |  chỉ nói chuyện với CTFd, cổng 8000
        v
CTFd  +  plugin judge0
        |
        |  plugin gửi code sang Judge0, cổng 2358
        v
Judge0 server  -->  Judge0 worker  -->  chạy code trong hộp cách ly
```

CTFd là website cuộc thi: tài khoản, đề, điểm, bảng xếp hạng.

Judge0 là dịch vụ chạy code. Nó nhận source, chạy trong một hộp cô lập, trả stdout, stderr và trạng thái. Nó không biết challenge là gì, không biết ai đúng điểm.

Plugin `judge0` nằm trong CTFd. Nó là cầu nối: nhận code từ trình duyệt, gửi cho Judge0, so output với đáp án, rồi bảo CTFd cộng điểm.

Trình duyệt không được gọi Judge0. Nếu gọi thẳng, người chơi sẽ thấy đáp án test ẩn và có thể đốt tài nguyên Judge0 không qua kiểm soát.

Code của người chơi không chạy trong container CTFd. Chỉ chạy trong worker của Judge0.

## Nguyên lý một lần nộp bài

1. Người chơi bấm Submit trên trang challenge.
2. Trình duyệt gửi source và tên ngôn ngữ (`python3`, không phải số 71) lên CTFd.
3. Plugin kiểm tra: đã đăng nhập chưa, ngôn ngữ có được phép không, code có quá dài không, bấm quá nhanh không.
4. Plugin lấy từng test case trong database. Với mỗi test, nó gửi sang Judge0: source, stdin của test, giới hạn CPU và bộ nhớ.
5. Judge0 worker chạy chương trình. Plugin nhận stdout.
6. Plugin so stdout với đáp án. Judge0 không được gửi đáp án, nên Judge0 không tự cho điểm.
7. Mọi test đúng: plugin ghi một dòng solve của CTFd. Điểm và bảng xếp hạng cập nhật như một challenge thường.
8. Có test sai: plugin ghi một lần fail. Không cộng điểm. Test ẩn không được trả về trình duyệt.

Run Code đi cùng đường, nhưng chỉ chạy test đánh dấu Sample, và không ghi solve hay fail.

## Phần 1. Chuẩn bị máy

Cài Docker và plugin Compose:

```
sudo apt update
sudo apt install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
sudo usermod -aG docker "$USER"
```

Đăng xuất rồi đăng nhập lại để nhóm `docker` có hiệu lực. Kiểm tra:

```
docker version
docker compose version
```

Mở firewall cho hai cổng, nếu máy có firewall:

```
sudo ufw allow 8000/tcp
sudo ufw allow 2358/tcp
```

Cổng 8000 là CTFd. Cổng 2358 là Judge0. Trong mạng nội bộ thì mở 2358 cũng được. Ra internet thì chỉ mở 8000, vì người chơi không cần đụng Judge0.

Lấy IP host:

```
hostname -I
```

Số đầu tiên, ví dụ `192.168.75.136`, là IP dùng trong cả tài liệu.

## Phần 2. Cài Judge0 CE 1.13.1

Judge0 chạy trước, vì CTFd cần một URL để gọi.

Tải bản 1.13.1 và giải nén vào thư mục home:

```
cd ~
wget https://github.com/judge0/judge0/releases/download/v1.13.1/judge0-v1.13.1.zip
unzip judge0-v1.13.1.zip
cd judge0-v1.13.1
```

File quan trọng là `docker-compose.yml` và `judge0.conf`.

Compose này có bốn service:

| Service | Việc |
|---|---|
| server | API, nhận bài nộp, cổng 2358 |
| workers | Chạy code. Không có service này thì bài nộp nằm hàng đợi mãi |
| db | Postgres, lưu submission của Judge0 |
| redis | Hàng đợi giữa server và worker |

`judge0.conf` trên bộ đang chạy có `AUTHN_TOKEN` để trống. Để trống nghĩa là Judge0 không hỏi token. CTFd vì thế cũng không cần token. `REDIS_PASSWORD` và `POSTGRES_PASSWORD` là mật khẩu nội bộ của Judge0, CTFd không dùng.

Chạy:

```
cd ~/judge0-v1.13.1
docker compose up -d
docker ps
```

Phải thấy bốn container `judge0-v1131-server-1`, `workers`, `db`, `redis` ở trạng thái Up. Server phải có `0.0.0.0:2358->2358/tcp`.

Thử API trên chính host:

```
curl -s http://127.0.0.1:2358/languages | head -c 200
echo
```

Có JSON liệt kê ngôn ngữ là Judge0 sống. Python 3 phải có `"id":71`.

Thử chấm một chương trình:

```
curl -s -X POST 'http://127.0.0.1:2358/submissions?wait=true' \
  -H 'Content-Type: application/json' \
  -d '{"language_id":71,"source_code":"print(1+1)\n"}'
```

`"status":{"id":3,"description":"Accepted"}` và `stdout` là `2\n` thì Judge0 chấm được.

Worker cần quyền privileged vì nó dùng isolate để nhốt code. Đừng bỏ `privileged: true` trong compose của Judge0.

## Phần 3. Cài CTFd

CTFd có compose riêng, không nằm chung file với Judge0. Hai bên không thấy nhau bằng tên service. Chúng chỉ gặp nhau qua IP của host.

Lấy source CTFd 3.8 và tạo file cấu hình:

```
cd ~
git clone https://github.com/CTFd/CTFd.git
cd CTFd
git checkout 3.8.6
```

CTFd 3.8 đã có `docker-compose.yml` ở gốc repo. Không có file `conf/examples/docker-compose.dev.yml`. Đừng copy file đó.

Bộ trên máy này dùng MariaDB và Redis nội bộ. Các service:

| Service | Việc |
|---|---|
| ctfd | Ứng dụng, cổng 8000 |
| nginx | Cổng 80, proxy tới CTFd |
| db | MariaDB, dữ liệu cuộc thi |
| cache | Redis của CTFd, gồm bộ đếm giới hạn bấm Run/Submit |

Điểm cần nhìn trong `docker-compose.yml` của service `ctfd`:

```
ports:
  - "8000:8000"
volumes:
  - .:/opt/CTFd:ro
```

Dòng volume này mount source trên host vào container. Plugin để trong `CTFd/plugins/` sẽ được process đọc lúc khởi động. Sửa plugin xong chỉ cần restart, không build lại image.

Chạy:

```
cd ~/CTFd
docker compose up -d
docker compose logs -f ctfd
```

Thoát theo log bằng Ctrl+C khi thấy CTFd lắng nghe. Mở `http://192.168.75.136:8000`. Lần đầu CTFd hỏi tên cuộc thi, tài khoản admin, mật khẩu. Tạo xong là vào được.

Mode users hay teams chọn ở bước setup. Plugin chạy được cả hai. Ở teams mode, người chơi phải có team thì mới Submit được, giống mọi challenge khác của CTFd.

## Phần 4. Cài plugin

Plugin là một thư mục cài vào đúng tên `judge0`:

```
~/CTFd/CTFd/plugins/judge0/
```

CTFd tự load mọi thư mục con của `CTFd/plugins/` có hàm `load(app)`, và tên thư mục chính là tên package Python. Plugin này đăng ký URL, challenge type và migration bằng chữ `judge0`. Thư mục để tên `ctfd_codechallenger` thì không load, và không phục vụ `/plugins/judge0/...`.

Nếu gói tải về tên `ctfd_codechallenger`, copy thành `judge0`. Không để cả hai thư mục cùng lúc:

```
rm -rf ~/CTFd/CTFd/plugins/judge0
cp -a /path/to/ctfd_codechallenger ~/CTFd/CTFd/plugins/judge0
```

Phải thấy `__init__.py`, `challenge.py`, `routes.py`, `assets/`. Không sửa file core của CTFd. Không cần `docker compose build`: compose mount source vào `/opt/CTFd`.

Bật:

```
cd ~/CTFd
docker compose restart ctfd
docker compose logs --since 2m ctfd | grep -i judge0
```

Dòng phải có:

```
Loaded module, <module 'CTFd.plugins.judge0' from '/opt/CTFd/CTFd/plugins/judge0/__init__.py'>
```

Không có, hoặc có Traceback phía trên, thì plugin không vào danh sách challenge type. Đọc traceback đó, đừng tạo challenge vội.

Lần đầu, plugin tạo hai bảng riêng: `judge0_challenge` và `judge0_test_case`. Kiểm tra:

```
docker compose exec db mariadb -uctfd -pctfd ctfd -e "SHOW TABLES LIKE 'judge0%';"
```

Mật khẩu trong lệnh này lấy từ `docker-compose.yml` của CTFd (`MARIADB_PASSWORD`). Bộ trên máy này là `ctfd`.

Vào Admin → Challenges → Create Challenge. Ô Challenge type phải có **Judge0 Code Challenge**.

## Phần 5. Nối CTFd với Judge0

Đây là chỗ hay sai nhất.

CTFd chạy trong container. Trong container đó, `localhost` là chính container CTFd. `http://localhost:2358` không tới được Judge0 dù trên host `curl localhost:2358` vẫn chạy.

URL đúng là IP của host:

```
http://192.168.75.136:2358
```

Kiểm tra từ bên trong container CTFd, không phải từ host:

```
cd ~/CTFd
docker compose exec ctfd python -c "import urllib.request; print(urllib.request.urlopen('http://192.168.75.136:2358/languages', timeout=5).status)"
```

In `200` thì đường đi thông. `Connection refused` thì sai IP, Judge0 chưa publish cổng, hoặc firewall chặn.

Lưu URL này vào CTFd, đăng nhập admin, mở:

```
http://192.168.75.136:8000/plugins/judge0/admin/settings
```

Cũng vào được bằng menu Admin → Judge0.

Ô Judge0 URL điền `http://192.168.75.136:2358`. Ô token để trống. Bấm Save.

Đúng: cạnh nút hiện **Saved.**, thanh địa chỉ không đổi, dòng Effective URL hiện đúng địa chỉ.

Sai: trang nhảy sang `?judge0_url=...`. Đó là form gửi GET, URL không được ghi. Bấm Ctrl+F5 rồi Save lại.

Cách thứ hai, nếu muốn URL có sẵn trước khi vào giao diện: thêm vào `environment` của service `ctfd` trong `docker-compose.yml`:

```
- JUDGE0_URL=http://192.168.75.136:2358
```

Rồi `docker compose up -d ctfd`.

Thứ tự plugin chọn URL khi chấm một bài:

1. URL ghi trên chính challenge đó, nếu ô không trống.
2. URL đã Save ở Admin → Judge0.
3. Biến `JUDGE0_URL`.

Để trống cả ba thì người chơi bấm Run sẽ thấy lỗi chưa cấu hình URL. Không có URL mặc định, plugin không tự gọi máy nào.

## Phần 6. Plugin làm việc bên trong CTFd

Khi CTFd khởi động nó gọi `load()` của plugin. Hàm này đăng ký challenge type tên `judge0`, gắn các route riêng, và chạy migration nếu bảng chưa có.

Admin tạo challenge type này thì CTFd vẫn ghi một dòng vào bảng `challenges` như mọi loại khác (tên, category, điểm, trạng thái). Plugin ghi thêm một dòng vào `judge0_challenge`: URL riêng, CPU, memory, ngôn ngữ được phép, starter code, kiểu so sánh. Test case nằm ở `judge0_test_case`.

Người chơi mở challenge thì trình duyệt tải `view.js`. File này vẽ ô chọn ngôn ngữ, editor, nút Run, nút Submit. Editor là CodeMirror để trong `assets/vendor/codemirror/`. Không cần internet, không gọi CDN. Nếu file đó lỗi, còn một ô textarea, vẫn nộp được.

Hai route người chơi dùng:

```
POST /plugins/judge0/run/<id>       chỉ test sample, không ghi điểm
POST /plugins/judge0/submit/<id>    mọi test, đúng hết thì giải challenge
```

Cả hai đều yêu cầu đăng nhập và CSRF token. `view.js` gửi qua cơ chế sẵn của CTFd, bạn không gắn tay.

Ngôn ngữ người chơi chọn là một tên cố định. Plugin đổi tên thành id của Judge0:

```
python3      71
c            50
cpp          54
java         62
javascript   63
go           60
rust         73
```

Người chơi không gửi được id tùy ý. Admin tắt ngôn ngữ nào thì tên đó bị từ chối.

So sánh output mặc định là `trim`: đổi CRLF thành LF, bỏ space cuối mỗi dòng, bỏ một newline cuối, phần còn lại phải giống hệt. `exact` và `whitespace-insensitive` chọn trong form challenge.

Giới hạn cứng, form không nới được: source 64 KB, stdin một test 64 KB, tối đa 50 test, CPU từ 0.1 đến 15 giây, memory từ 2048 đến 512000 KB. Run tối đa 12 lần mỗi phút, Submit tối đa 6 lần, tính theo từng challenge.

Log của CTFd ghi `challenge_id`, `language_id`, số test và status. Không ghi source, không ghi đáp án test ẩn.

## Phần 7. Tạo một bài

Đăng nhập admin. Admin → Challenges → Create Challenge.

Challenge type chọn **Judge0 Code Challenge**.

Điền:

```
Name:        Sum
Category:    programming
Message:     Đọc hai số nguyên trên một dòng, in tổng của chúng.
Value:       100
```

Bấm Create. Hộp flag hiện ra thì đóng, không cần thêm flag. Loại này không chấm bằng flag. Điểm chỉ cộng khi Submit đủ test.

Mở challenge vừa tạo. Form bên phải:

```
Judge0 URL:          để trống  (dùng URL đã Save ở Admin → Judge0)
CPU time limit:      2
Memory limit (KB):   128000
Comparison:          trim
Languages:           bật Python 3
Starter code:        để trống
```

Bấm **Update**. Nút này chỉ lưu các ô vừa kể. Không lưu test case.

Kéo xuống Test cases.

Bấm Add test case. Tick **Sample**:

```
Name:              sample
Input:             2 3
Expected output:   5
```

Bấm **Save** trên chính card này.

Bấm Add test case lần nữa. Không tick Sample:

```
Name:              hidden
Input:             10 20
Expected output:   30
```

Bấm **Save** trên card thứ hai.

Hai nút khác nhau. Update lưu cấu hình bài. Save trên từng card lưu test đó. Quên Save thì Run sẽ báo không có test.

Sample là ví dụ người chơi được thấy, và là test duy nhất Run Code chạy. Hidden chỉ chạy lúc Submit. Người chơi không nhận được input lẫn đáp án của test ẩn, chỉ nhận được đúng hay sai.

State của challenge để `visible` thì user thường mới thấy.

## Phần 8. Làm thử với tư cách người chơi

Đăng xuất admin. Đăng ký một user thường, hoặc dùng tài khoản có sẵn. Nên thử bằng user thường vì solve của admin cũng lên bảng điểm.

Mở Challenges, rồi mở bài vừa tạo (tài liệu này gọi là Sum). Bài đã có sẵn trên CTF có thể mang tên khác. Chọn Python 3.

Xóa hết ô soạn thảo. Gõ từ cột 0, không space đầu dòng:

```
a, b = map(int, input().split())
print(a + b)
```

Bấm **Run Code**.

Đúng thì status Accepted, stdout là `5`, và chỉ có một test. Challenge chưa chuyển sang solved. Run không bao giờ cộng điểm.

Bấm **Submit**.

Đúng thì Accepted 2/2. Challenge hiện solved, cộng 100 điểm, bảng xếp hạng đổi.

Ctrl+Enter cũng là Run.

Thử một chương trình sai, bằng user khác:

```
a, b = map(int, input().split())
print(a - b)
```

Submit ra Wrong Answer. Test ẩn chỉ hiện fail, không hiện `10 20` hay `30`.

## Phần 9. Đọc một lỗi thường gặp khi mới viết code

`Runtime Error (NZEC)` kèm `IndentationError: unexpected indent` là code Python thụt dòng sai, không phải hỏng Judge0. Dòng `print` bị space ở đầu trong khi dòng trên không mở block. Xóa và gõ lại từ cột 0.

Lỗi cú pháp Python cũng hiện Runtime Error (NZEC), không hiện Compilation Error. Judge0 không biên dịch Python riêng. C, C++, Java, Go và Rust mới có Compilation Error, kèm thông báo trình biên dịch ở test sample.

`Wrong Answer` nghĩa là chương trình chạy xong nhưng output khác đáp án. Thừa chữ, thiếu dấu cách, hoặc thêm một dòng trống đều tính sai. `trim` không bỏ dòng trống ở giữa.

Run đúng mà Submit sai: test ẩn khác sample. Sửa cho đúng đề, không chỉ đúng ví dụ.

`Too many runs` hoặc `Too many submissions`: đã bấm quá 12 lần Run hoặc 6 lần Submit trong một phút. Đợi khoảng một phút.

## Phần 10. Khi vận hành hằng ngày

Xem cả hai hệ còn sống:

```
docker ps
```

Tám container cần Up: bốn của Judge0 (server, workers, db, redis) và bốn của CTFd (ctfd, nginx, db, cache). Tên có thể khác tiền tố một chút, nhưng đủ vai trò là được.

Khởi động lại sau khi reboot máy:

```
cd ~/judge0-v1.13.1 && docker compose up -d
cd ~/CTFd && docker compose up -d
```

`restart: always` đã gắn sẵn, Docker thường tự bật lại. Lệnh trên là cách chắc tay.

Sửa file Python của plugin xong:

```
cd ~/CTFd && docker compose restart ctfd
```

Sửa HTML, JS, CSS thì refresh trình duyệt. Bản cũ cứng đầu thì Ctrl+F5.

Xem log lúc một bài nộp bị Internal Error:

```
cd ~/CTFd
docker compose logs --since 10m ctfd | grep JUDGE0
```

Dòng có `result_status` là Judge0 đã trả lời. Dòng có `error=` là CTFd không nói chuyện được với Judge0.

Đừng trỏ URL Judge0 ra internet nếu không cần. Người chơi đã đi qua CTFd. Cổng 2358 chỉ cần mở từ chính host tới được.

Đừng bật `AUTHN_TOKEN` của Judge0 rồi quên điền token bên CTFd. Bật thì điền cùng giá trị đó vào ô token ở Admin → Judge0.

Đừng thêm flag cho challenge loại này. Flag không tham gia vào đường chấm.

## Phần 11. Bảng tra lỗi lúc cài

| Triệu chứng | Nguyên nhân | Việc làm |
|---|---|---|
| Không có type Judge0 Code Challenge | Plugin chưa load | `docker compose logs ctfd` tìm `judge0`. Restart sau khi sửa |
| Save URL nhưng trang thành `?judge0_url=` | Form gửi GET | Ctrl+F5, Save lại, phải thấy chữ Saved |
| Run báo chưa cấu hình URL | Cả ba chỗ đặt URL đều trống | Làm phần 5 |
| Connection refused | URL là localhost, hoặc Judge0 chưa publish 2358 | Dùng IP host. `docker ps` phải có `0.0.0.0:2358->2358/tcp` |
| Internal Error, log nói timed out | Không có worker, hoặc worker chết | `docker ps` phải có container workers. `docker compose up -d` trong thư mục Judge0 |
| 401 từ Judge0 | Judge0 bật auth | Điền token ở Admin → Judge0, hoặc để `AUTHN_TOKEN` trống |
| 403 từ CTFd | Chưa đăng nhập, CTF pause, hoặc teams mode mà chưa có team | Đăng nhập bằng user có quyền chơi |
| Mở bài thì 500 | Bảng plugin chưa tạo | Xem log lúc start. Restart. Không insert tay vào bảng `challenges` |
| Editor không hiện, chỉ còn ô chữ | Trình duyệt giữ file cũ, hoặc thiếu CodeMirror local | Ctrl+F5. Ô chữ vẫn nộp bài được |

## Tóm tắt thứ tự làm một lần

1. Cài Docker.
2. `docker compose up -d` trong `~/judge0-v1.13.1`. `curl` cổng 2358 ra JSON.
3. `docker compose up -d` trong `~/CTFd`. Mở cổng 8000, tạo tài khoản admin.
4. Để plugin ở `CTFd/plugins/judge0/`, restart CTFd, thấy dòng Loaded module.
5. Admin → Judge0, Save `http://<IP-host>:2358`.
6. Tạo challenge type Judge0 Code Challenge, Update cấu hình, Save từng test case.
7. User thường mở bài, Run, rồi Submit.
