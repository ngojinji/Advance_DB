# Bài 2 - Redis: Lab TicketRush



## Kết quả các bước

**Bước 1 - giữ ghế.** Cho 50 thread cùng giữ ghế A1. Bản `GET` rồi `SET` chạy 5 lần ra số người thắng lần lượt là 4, 18, 19, 19, 20, mỗi lần một khác và lần nào cũng nhiều hơn 1. Bản `SET NX EX` thì cả 5 lần đều đúng 1 người thắng. `TTL hold:c1:A1` giảm từ 300 xuống 298 sau 2 giây. Thử giữ ghế với TTL 2 giây thì sau 2,5 giây key tự mất.

**Bước 2 - giữ, xác nhận, nhả bằng Lua.** Kịch bản trong bài cho ra `True, False, False, True, False` và sơ đồ ghế `{'A1': 'sold', 'A2': 'free'}`, đúng như dự đoán. Thêm một thử nghiệm: mai giữ A2, nam gọi `release` thì bị từ chối, mai `release` thì được, A2 trở về `free`.

Ghế đã bán để chung trong một set `sold:c1` vì muốn liệt kê mọi ghế đã bán chỉ cần một lệnh `SMEMBERS`, còn nếu mỗi ghế một key thì phải `SCAN` cả keyspace. Ngoài ra `SADD` một ghế hai lần thì set vẫn chỉ có một phần tử, nên có gọi lại cũng không sao.

**Bước 3 - flash sale.** 500 người tranh 100 vé:

| Cách làm | Lần 1 | Lần 2 | Lần 3 |
|---|---|---|---|
| `DECR` rồi xét dấu | bán 100, stock 0 | bán 100, stock 0 | bán 100, stock 0 |
| `GET` > 0 rồi mới `DECR` | bán 116, stock -16 | bán 110, stock -10 | bán 108, stock -8 |

Bản sai bán quá 8-16 vé mỗi lần, cùng lỗi check-then-act như Bước 1.

**Bước 4 - giới hạn tần suất (5 request / 10 giây).** Gửi 8 request liên tiếp thì cả fixed window và sliding window đều cho qua 5, chặn 3. Khác nhau ở thử nghiệm ranh giới: gửi 5 request ngay trước khi hết cửa sổ, chờ 0,4 giây rồi gửi thêm 5:

- fixed window: cả 10 request đều qua, vì sang cửa sổ mới thì bộ đếm về 0
- sliding window: chỉ 5 request đầu qua, 5 request sau bị chặn

Gắn vào luồng giữ ghế, 7 lần `try_hold` liên tiếp ra `ok, taken, taken, taken, taken, rate_limited, rate_limited`.

**Bước 5 - phòng chờ.** u1, u2, u3 vào hàng ở vị trí 1, 2, 3. u1 vào lại vẫn ở vị trí 1 (nhờ `NX`). `admit` 2 người thì ra `['u1', 'u2']`, u3 lên vị trí 1.

**Bước 6 - stress test.** 100 người tranh 20 ghế, chạy 10 lần, lần nào cũng ra `20 20 20`.

## Câu hỏi cho báo cáo

**1. Vì sao `SET NX EX` tránh được race còn `GET` rồi `SET` thì không?**

`GET` rồi `SET` là hai lệnh riêng. Trong khoảng giữa hai lệnh đó, các thread khác cũng `GET` và cũng thấy ghế còn trống, nên tất cả cùng `SET` và đều tưởng mình giữ được ghế. `SET NX EX` thì kiểm tra và ghi trong cùng một lệnh. Redis chạy từng lệnh một nên không có khoảng hở nào để thread khác chen vào: chỉ lệnh đầu tiên ghi được, các lệnh sau nhận về `nil`.

**2. Khách giữ ghế rồi đóng trình duyệt thì sao?**

Key `hold:c1:A1` vẫn còn đó cho đến khi hết TTL (300 giây), sau đó Redis tự xoá key và ghế trở lại trống. Không cần job nào đi dọn. Tính năng xử lý việc này là thời hạn hết hạn của key (`EX` trong `SET`). Ở Bước 1 có thử với TTL 2 giây và thấy key tự mất.

**3. Nếu `confirm` không so sánh chủ sở hữu thì sai ở đâu?**

Bất kỳ ai cũng xác nhận được ghế người khác đang giữ. Ví dụ A giữ A1 nhưng chưa trả tiền, B gọi `confirm` và ghế chuyển sang đã bán, trong khi người trả tiền là B chứ không phải người đang giữ. Một trường hợp khác: hạn giữ của A hết, B giữ lại ghế đó, sau đó A mới thanh toán xong và gọi `confirm`. Không kiểm tra chủ thì ghế bị chốt cho A, còn B mất ghế dù đang giữ hợp lệ. Trong kịch bản Bước 2, `confirm("c1", "A1", "nam")` trả về `False` chính là nhờ bước so sánh này.

**4. Khi nào fixed window là đủ, khi nào cần sliding window?**

Fixed window đủ dùng khi giới hạn chỉ mang tính ước lượng và việc vượt một chút không gây hại, ví dụ đếm lượt gọi API theo phút để thống kê hoặc chặn spam nhẹ. Nó rẻ: mỗi user chỉ cần một bộ đếm. Cần sliding window khi giới hạn phải chặt, như chống bot lúc mở bán vé hay giới hạn số lần đăng nhập sai. Thử nghiệm ở Bước 4 cho thấy fixed window để lọt gấp đôi giới hạn (10 thay vì 5) nếu bot canh đúng lúc chuyển cửa sổ, còn sliding window thì không bao giờ vượt.

**5. Dữ liệu nào cần ghi thêm vào cơ sở dữ liệu bền vững, và khi nào?**

Những gì liên quan đến tiền và quyền sở hữu vé: đơn hàng, ghế nào bán cho ai, thông tin thanh toán. Việc giữ ghế, bộ đếm rate limit và phòng chờ chỉ là trạng thái tạm, mất thì cũng không sao.

Nếu Redis khởi động lại sau `confirm` mà đơn chưa được ghi xuống DB thì `sold:c1` có thể bị mất (Redis có thể mất khoảng 1 giây ghi gần nhất). Khách đã trả tiền nhưng ghế lại thành trống và có thể bán cho người khác. Vì vậy thứ tự nên là: khi thanh toán thành công, ghi đơn vào DB quan hệ trong một transaction trước (có ràng buộc unique trên `(event, seat)` để chặn bán trùng), sau đó mới `confirm` trên Redis. Nếu Redis mất dữ liệu thì dựng lại `sold:{event}` từ DB.

## Bài tập

**1. Bảng xếp hạng bằng sorted set.** Thêm 6 người chơi bằng `ZADD`, cộng thêm 250 điểm cho nam bằng `ZINCRBY`, rồi lấy top 3 bằng `ZREVRANGE board 0 2 WITHSCORES`:

| Hạng | Người chơi | Điểm |
|---|---|---|
| 1 | mai | 1430 |
| 2 | tuan | 1300 |
| 3 | nam | 1200 |

Thứ hạng lấy từ vị trí trong kết quả, hoặc dùng `ZREVRANK board nam` (đánh số từ 0, nên cộng 1).

**2. Hồ sơ người dùng bằng hash, tìm theo thành phố.** Mỗi user là một hash `user:{id}` gồm `name`, `city`, `age`. Song song đó, mỗi thành phố có một set `city:{tên}` chứa id các user ở thành phố đó, đóng vai trò như một index tự xây. Tìm user ở Hanoi là `SMEMBERS city:Hanoi` rồi `HGETALL` từng id, ra Linh, Mai, Tuan. Khi user đổi thành phố thì phải cập nhật cả hash lẫn set: Lan chuyển ra Hanoi thì `HSET user:5 city Hanoi` và `SMOVE city:Ho Chi Minh city:Hanoi 5`. Redis không tự làm việc này, ứng dụng phải tự giữ cho hai chỗ khớp nhau.

**3. Đo tăng tốc của cache-aside với 100 yêu cầu.**

Dùng lại hàm `get_product` trong bài, trong đó `slow_query` giả lập truy vấn DB mất 1 giây. Gọi 100 lần cho cùng sản phẩm, lần đầu không cache và lần sau có cache:

| | Tổng thời gian 100 yêu cầu |
|---|---|
| Không cache (luôn gọi `slow_query`) | 100.06 s |
| Có cache-aside | 1.141 s |

Khi có cache, lần đầu bị miss nên vẫn mất 1005 ms, 99 lần sau đều hit và trung bình chỉ khoảng 1.4 ms mỗi lần. Tính chung thì nhanh hơn khoảng 88 lần. Gần như toàn bộ 1.14 giây là của lần miss đầu tiên, nên càng nhiều yêu cầu lặp lại thì mức tăng tốc càng lớn. Tính riêng một lần hit so với một lần query thì nhanh hơn khoảng 700 lần.
