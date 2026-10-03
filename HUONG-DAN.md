# Hướng dẫn plugin Judge0 cho CTFd

Plugin thêm challenge type **Judge0 Code Challenge**. Người chơi viết code trên trình duyệt. CTFd gửi code sang Judge0, so output với test case, và ghi solve của CTFd khi mọi test đạt.

Trình duyệt không gọi Judge0. Code không chạy trong container CTFd.

Bản đã kiểm tra trên máy này:

- CTFd `3.8.6-9-g006b7274`
- Judge0 CE 1.13.1, cổng 2358
- Ubuntu 24.04, Docker Compose
- CTFd: `http://192.168.75.136:8000`
- Judge0: `http://192.168.75.136:2358`

Đổi hai địa chỉ đó nếu máy bạn khác.

## 1. Cài plugin

Plugin cài vào:

```
~/CTFd/CTFd/plugins/judge0/
```

Gói tải về có thể tên `ctfd_codechallenger`. CTFd lấy tên thư mục làm tên package. URL, challenge type và migration của plugin này là `judge0`, nên thư mục cài phải đúng tên đó. Để nguyên tên `ctfd_codechallenger` thì plugin không load.

```
rm -rf ~/CTFd/CTFd/plugins/judge0
cp -a /path/to/ctfd_codechallenger ~/CTFd/CTFd/plugins/judge0
```

Không để cả hai thư mục trong `CTFd/plugins/`. Container `ctfd` mount `~/CTFd` vào `/opt/CTFd` và chạy từ đó. Sửa file trên host là container thấy ngay. Không cần `docker compose build`.

Bật plugin bằng restart:

    cd ~/CTFd
    docker compose restart ctfd

Đợi vài giây rồi xem log. Phải có dòng load, không có traceback:

    docker compose logs --since 2m ctfd | grep -i judge0

Dòng đúng:

    Loaded module, <module 'CTFd.plugins.judge0' from '/opt/CTFd/CTFd/plugins/judge0/__init__.py'>

Lần đầu chạy, plugin tự tạo hai bảng `judge0_challenge` và `judge0_test_case`. Không sửa schema core của CTFd. Kiểm tra:

    docker compose exec db mariadb -uctfd -pctfd ctfd -e "SHOW TABLES LIKE 'judge0%';"

Phải thấy cả hai bảng. Nếu thiếu, đọc log ngay sau dòng load. Migration lỗi sẽ in ở đó. Restart lại sau khi sửa. Migration chạy lại được, nó không tạo bảng lần hai.

Không thêm package Python. Image CTFd đã có `requests`.

## 2. Đặt URL Judge0

CTFd gọi Judge0 từ trong container. `localhost` trong container là chính container CTFd, không phải máy host và không phải container Judge0.

URL đúng trên máy này:

    http://192.168.75.136:2358

Ba chỗ đặt URL, cái nào có giá trị thì dùng trước:

1. Ô Judge0 URL trên từng challenge. Để trống thì dùng URL chung.
2. Admin → Judge0.
3. Biến môi trường `JUDGE0_URL` của container CTFd.

### Cách dùng giao diện

Mở:

    http://192.168.75.136:8000/plugins/judge0/admin/settings

Hoặc menu Admin → Judge0.

Điền `http://192.168.75.136:2358`. Token để trống vì Judge0 local không bật auth. Bấm Save.

Đúng thì chữ **Saved.** hiện cạnh nút, và thanh địa chỉ không đổi. Sai thì trình duyệt chuyển thành GET dạng:

    /plugins/judge0/admin/settings?judge0_url=...

Đó là form HTML gửi đi, không phải API. Hard-refresh trang (Ctrl+F5) rồi Save lại. Nguyên nhân cũ là script gọi `CTFd.fetch`, object này không có trên trang admin.

### Cách dùng biến môi trường

Trong `docker-compose.yml`, dưới `ctfd.environment`, thêm:

    - JUDGE0_URL=http://192.168.75.136:2358

Rồi:

    docker compose up -d ctfd

`JUDGE0_API_TOKEN` chỉ cần khi Judge0 được bật `AUTHN_TOKEN`. Token nằm trên server, không trả về trình duyệt.

### Kiểm tra từ trong container

Đừng kiểm tra bằng `curl localhost:2358` trên host rồi kết luận CTFd gọi được. Chạy từ container:

    docker compose exec ctfd python -c "import urllib.request; print(urllib.request.urlopen('http://192.168.75.136:2358/languages', timeout=5).status)"

`200` là đúng URL. `Connection refused` hoặc treo là sai URL hoặc firewall, không phải lỗi plugin.

| Judge0 đang chạy ở đâu | URL điền vào CTFd |
|---|---|
| Cổng 2358 mở trên host | `http://<IP-host>:2358` |
| Container khác, cùng Docker network với CTFd | `http://<tên-service>:2358` |
| Cùng một file compose, service tên `server` | `http://server:2358` |

`host.docker.internal` không có sẵn trên Docker Linux. Đừng dùng nếu bạn chưa tự thêm.

`docker ps` phải có dòng `0.0.0.0:2358->2358/tcp` ở container Judge0 server, và một container `workers` đang Up. Không có worker thì bài nộp treo đến timeout.

## 3. Tạo một bài

### Bài cộng hai số

Admin → Challenges → nút tạo challenge.

Challenge type: **Judge0 Code Challenge**.

- Name: Sum
- Category: programming
- Message: đọc hai số trên một dòng, in tổng
- Value: 100

Bấm Create. Hộp flag có thể bỏ trống rồi đóng. Loại challenge này không dùng flag.

Mở challenge vừa tạo. Form bên phải:

- Judge0 URL: để trống (dùng URL đã lưu ở Admin → Judge0)
- CPU time limit: 2
- Memory limit (KB): 128000
- Comparison: trim
- Bật Python 3. Các ngôn ngữ khác tùy ý
- Starter code: để trống

Bấm **Update**. Nút này chỉ lưu các ô trên. Không lưu test case.

Kéo xuống Test cases. Bấm Add test case.

Test 1, tick Sample:

    Name: sample
    Input: 2 3
    Expected output: 5

Bấm **Save** trên card đó.

Add test case lần nữa. Không tick Sample:

    Name: hidden
    Input: 10 20
    Expected output: 30

Bấm **Save** trên card này.

Mỗi card có nút Save riêng. Bấm Update của form challenge không ghi test case.

### Chơi thử

Đăng xuất admin. Đăng nhập một user thường. Admin chấm được nhưng solve của admin dễ lẫn với lần test.

Mở Challenges, rồi mở bài vừa tạo (ví dụ Sum). Bài đã có trên CTF này không mang tên Sum: bài 100 điểm đang tên `1`. Chọn Python 3. Dán, không space đầu dòng:

    a, b = map(int, input().split())
    print(a + b)

Run Code chỉ chạy test sample. Kết quả đúng là Accepted, stdout `5`, challenge chưa solved. Run không thêm dòng vào `submissions`.

Submit chạy cả test ẩn. Đúng là Accepted 2/2, challenge chuyển solved, cộng 100 điểm. Lần Submit sai trước khi solve ghi một dòng `submissions` với `type=incorrect`. Sau khi đã solve, Submit sai không ghi thêm dòng.

Ctrl+Enter cũng là Run.

### Bài sắp xếp, dài hơn

Đã có sẵn trên CTF này nếu bạn chưa xóa: **Sort it**, 200 điểm, 1 sample và 6 test ẩn.

Đề: dòng 1 là `n` (1 đến 1000). Dòng 2 là `n` số, mỗi số từ -10^9 đến 10^9. In các số không giảm, cách nhau một dấu cách.

Sample input:

    5
    1 4 2 3 5

Sample output:

    1 2 3 4 5

Lời giải Python, dán đè cả editor:

    import sys
    data = sys.stdin.read().split()
    n = int(data[0])
    nums = [int(x) for x in data[1:1+n]]
    nums.sort()
    print(" ".join(str(x) for x in nums))

Submit đúng thì Accepted 7/7. Sáu case ẩn không hiện input. Chúng gồm dãy đã sắp, dãy đảo, số trùng, số âm, một phần tử, và số sát 10^9.

## 4. Quy tắc chấm

Run không ghi solve, không ghi fail, không cộng điểm. Chỉ chạy test sample.

Submit chạy mọi test trên server. Đủ test thì ghi một dòng `solves` và một dòng `submissions` (`type=correct`), rồi xóa cache scoreboard. Sai, và chưa solve, thì ghi một dòng `submissions` với `type=incorrect`. Trên CTFd 3.8 cột `provided` nằm ở bảng `submissions`, không nằm ở `solves`. Giá trị là `judge0:python3` (đúng slug ngôn ngữ), không lưu source.

So sánh mặc định là `trim`:

- CRLF thành LF
- bỏ space ở cuối mỗi dòng
- bỏ một newline cuối
- phần còn lại phải giống hệt

`exact` so đúng từng ký tự sau khi đổi CRLF. `whitespace-insensitive` gom mọi khoảng trắng thành một dấu cách.

Judge0 báo Accepted chỉ có nghĩa tiến trình thoát mã 0. Wrong Answer do CTFd quyết định. `expected_output` không gửi sang Judge0.

Giới hạn không sửa được từ form:

    source          64 KB
    stdin một test  64 KB
    starter code    16 KB mỗi ngôn ngữ
    số test         tối đa 50
    CPU             0.1 đến 15 giây
    memory          2048 đến 512000 KB
    Run             12 lần mỗi phút mỗi challenge
    Submit          6 lần mỗi phút mỗi challenge

Bấm quá nhanh sẽ nhận "Too many runs" hoặc "Too many submissions". Đợi khoảng một phút.

## 5. Ngôn ngữ

Người chơi chọn tên, không gửi được language id. Slug lạ hoặc id số bị từ chối.

    Python 3      python3      71
    C             c            50
    C++           cpp          54
    Java          java         62
    JavaScript    javascript   63
    Go            go           60
    Rust          rust         73

Id này là của Judge0 CE 1.13.1. Nâng Judge0 thì mở `http://<IP>:2358/languages` và đối chiếu lại trước khi tin một lần solve.

Tắt một ngôn ngữ trong form challenge rồi Update. Ô chọn ngôn ngữ của người chơi không còn ngôn ngữ đó. Gửi `"language": "java"` khi Java đang tắt bị từ chối.

## 6. Sửa lỗi

### Không thấy "Judge0 Code Challenge" trong danh sách type

Log không có dòng `Loaded module ... judge0`, hoặc có ImportError phía trên.

    docker compose logs --since 5m ctfd | grep -i judge0

`SAFE_MODE` đang bật thì CTFd không load plugin nào. Restart sau khi sửa file. Không cần build lại image trên bộ compose này.

### Save URL nhưng trang nhảy thành `?judge0_url=`

Form đã gửi GET, request không tới API. Ctrl+F5. Sau refresh, Save phải hiện **Saved.** và URL không đổi. Kiểm tra DB:

    docker compose exec db mariadb -uctfd -pctfd ctfd -e "SELECT \`key\`, value FROM config WHERE \`key\`='judge0_url';"

### Run hoặc Submit trả 400 "Judge0 URL is not configured"

Chưa lưu URL chung và ô URL của challenge cũng trống. Làm mục 2. Challenge tạo trước khi có URL không tự nhận URL mới cho đến khi bạn Submit lại.

### Connection refused

URL là `localhost` hoặc `127.0.0.1`. Đổi thành IP host. Kiểm tra bằng lệnh `docker compose exec` ở mục 2, không phải curl trên host.

### Timeout, người chơi thấy Internal Error

Container `workers` của Judge0 không chạy. `docker ps` phải có cả server, db, redis và workers.

Plugin chờ Judge0 tối đa 30 giây. Vòng lặp vô hạn trong giới hạn CPU là Time Limit Exceeded, không phải lỗi này. Hạ CPU limit của challenge xuống 1 rồi nộp `while True: pass` để thấy khác nhau.

Lần Run đầu sau khi worker đứng yên có thể ra Time Limit Exceeded dù stdout đã đúng (đã thấy 3.14 giây với limit 2 giây). Bấm Run lại: lần sau về Accepted trong vài chục mili-giây. Đó là worker lạnh, không phải bài sai.

### 401 hoặc 403

403 từ chính CTFd: chưa đăng nhập, CTF đang pause, hoặc chế độ teams mà user chưa có team.

401/403 từ Judge0: Judge0 bật auth mà CTFd chưa có token. Điền token ở Admin → Judge0, hoặc đặt `JUDGE0_API_TOKEN`.

### CORS trong console trình duyệt

Plugin không gọi Judge0 từ browser. Lỗi CORS là trang khác đang gọi thẳng cổng 2358. Bỏ qua nếu Run/Submit trên CTFd vẫn 200.

### Runtime Error (NZEC) với Python

Đọc stderr. Hai lỗi hay gặp:

`IndentationError: unexpected indent` — có space hoặc tab đầu dòng. Xóa editor, gõ lại từ cột 0.

`SyntaxError` của Python cũng ra NZEC, không ra Compilation Error. Judge0 không compile CPython riêng. C, C++, Java, Go, Rust mới ra Compilation Error kèm `compile_output`.

`NameError` — thiếu dòng khai báo biến. `ValueError` khi `map(int, ...)` — input test không phải các số như code đang đọc.

### Wrong Answer dù in đúng trên máy mình

Output thừa space cuối, thiếu dấu cách, hoặc thừa dòng trống. `trim` chỉ bỏ space cuối dòng và một newline cuối. Dòng trống ở giữa vẫn tính. In đúng định dạng đề, không in thêm chữ.

### Accepted trên Run nhưng Submit thì Wrong Answer

Run không chạy test ẩn. Một case ẩn khác sample. Sửa cho đủ đề, đừng chỉ khớp ví dụ.

### "Too many runs" hoặc "Too many submissions"

Đủ 12 Run hoặc 6 Submit trong một phút cho challenge đó. Đợi rồi bấm lại. Không phải lỗi Judge0.

### Bài mở ra không có editor, chỉ ô textarea

CodeMirror nằm local tại `assets/vendor/codemirror/`, không gọi CDN. Textarea vẫn Run và Submit được. Nếu muốn editor: hard-refresh. Xem console, lỗi 404 nghĩa là thiếu file trong thư mục vendor.

### Sửa code plugin xong không thấy thay đổi

File Python được nạp lúc process khởi động. `docker compose restart ctfd`. File HTML, JS, CSS thì refresh trình duyệt, Ctrl+F5 nếu vẫn cũ.

### Bảng judge0 không có, hoặc mở challenge thì 500

Migration chưa chạy hoặc chạy lỗi. Xem log lúc start. Không insert tay vào bảng `challenges`. Restart sau khi hết traceback. Khóa phiên bản nằm ở config `judge0_alembic_version`, giá trị `c4e1a0b77d21`.

### `wait=true` hoặc "cannot be converted to UTF-8" trong log Judge0

Không phải việc phải sửa. Client gửi `base64_encoded=true`. Lỗi biên dịch C là byte thô, Judge0 từ chối trả text và đưa token. Client poll token và tự giải base64. Cứ để.

## 7. Việc không được làm

- Không chạy source người chơi bằng `eval`, `exec`, `subprocess` trong CTFd.
- Không trỏ URL Judge0 ra localhost bên trong container.
- Không thêm flag cho loại challenge này. Solve đi qua nút Submit của plugin.
- Không ghi source vào log. Log chỉ có `challenge_id`, `language_id`, số test, và status.
