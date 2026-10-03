# Hướng dẫn plugin Code cho CTFd

Plugin thêm challenge type **Code Challenge**. Người chơi viết code trên trình duyệt. CTFd gửi code sang Judge0, so output với test case, và ghi solve của CTFd khi mọi test đạt.

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
~/CTFd/CTFd/plugins/ctfd_code/
```

Gói tải về có thể tên `ctfd_codechallenger`. CTFd lấy tên thư mục làm tên package. URL, challenge type và migration của plugin này là `ctfd_code`, nên thư mục cài phải đúng tên đó. Để nguyên tên `ctfd_codechallenger` thì plugin không load.

```
rm -rf ~/CTFd/CTFd/plugins/ctfd_code
cp -a /path/to/ctfd_codechallenger ~/CTFd/CTFd/plugins/ctfd_code
```

Không để cả hai thư mục trong `CTFd/plugins/`. Container `ctfd` mount `~/CTFd` vào `/opt/CTFd` và chạy từ đó. Sửa file trên host là container thấy ngay. Không cần `docker compose build`.

Bật plugin bằng restart:

    cd ~/CTFd
    docker compose restart ctfd

Đợi vài giây rồi xem log. Phải có dòng load, không có traceback:

    docker compose logs --since 2m ctfd | grep -i ctfd_code

Dòng đúng:

    Loaded module, <module 'CTFd.plugins.ctfd_code' from '/opt/CTFd/CTFd/plugins/ctfd_code/__init__.py'>

Lần đầu chạy, plugin tự tạo hai bảng `ctfd_code_challenge` và `ctfd_code_test_case`. Không sửa schema core của CTFd. Kiểm tra:

    docker compose exec db mariadb -uctfd -pctfd ctfd -e "SHOW TABLES LIKE 'ctfd_code%';"

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

    http://192.168.75.136:8000/plugins/ctfd_code/admin/settings

Hoặc menu Admin → Judge0.

Điền `http://192.168.75.136:2358`. Token để trống vì Judge0 local không bật auth. Bấm Save.

Đúng thì chữ **Saved.** hiện cạnh nút, và thanh địa chỉ không đổi. Sai thì trình duyệt chuyển thành GET dạng:

    /plugins/ctfd_code/admin/settings?ctfd_code_url=...

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

Challenge type: **Code Challenge**.

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

Submit chạy mọi test trên server. Đủ test thì ghi một dòng `solves` và một dòng `submissions` (`type=correct`), rồi xóa cache scoreboard. Sai, và chưa solve, thì ghi một dòng `submissions` với `type=incorrect`. Trên CTFd 3.8 cột `provided` nằm ở bảng `submissions`, không nằm ở `solves`. Giá trị là `ctfd_code:python3` (đúng slug ngôn ngữ), không lưu source.

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

## 7. Việc không được làm

- Không chạy source người chơi bằng `eval`, `exec`, `subprocess` trong CTFd.
- Không trỏ URL Judge0 ra localhost bên trong container.
- Không thêm flag cho loại challenge này. Solve đi qua nút Submit của plugin.
- Không ghi source vào log. Log chỉ có `challenge_id`, `language_id`, số test, và status.
