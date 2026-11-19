# Bài 3 - Cassandra: Lab SensorRing

IP các node trên máy này:

| Container | IP |
|---|---|
| cass1 | 172.22.0.2 |
| cass2 | 172.22.0.3 |
| cass3 | 172.22.0.4 |

## Kết quả các bước

**Bước 0.** `nodetool status` hiện 3 dòng `UN`. `python sensorring.py load` nạp 3000 số đo của 30 cảm biến vào keyspace `iot` (RF = 3).

**Bước 1 - partition key quyết định node.** Token của 5 cảm biến đầu tiên giống hệt bảng trong bài, ví dụ `hn-01` là `-6927399588689370405`. Với keyspace `iot` (RF = 3), `getendpoints` cho `hn-01` trả về cả 3 IP và `nodetool status iot` báo mỗi node Owns 100%.

Với keyspace `ring1` (RF = 1), các cảm biến được chia cho các node:

```
hn-01 -> 172.22.0.4    hn-04 -> 172.22.0.4
hn-02 -> 172.22.0.3    hn-05 -> 172.22.0.3
hn-03 -> 172.22.0.3    hn-06 -> 172.22.0.4
```

Cột Owns của `ring1` là 32.7% + 31.6% + 35.7% = 100%.

Kiểm tra quy tắc "node kế tiếp theo chiều kim đồng hồ" bằng `nodetool ring` (48 token, mỗi node 16):

- `hn-01` có token `-6927399588689370405`. Token đầu tiên lớn hơn hoặc bằng nó là `-6648083467482496530`, thuộc `172.22.0.4`, khớp với `getendpoints`.
- `hn-02` có token `1779598930076072019`. Token kế tiếp là `2068553595866611698`, thuộc `172.22.0.3`, cũng khớp.

**Bước 2 - truy vấn theo partition và quét toàn bảng.** `WHERE temperature > 31.5` không có `ALLOW FILTERING` thì bị từ chối với lỗi `InvalidRequest ... might involve data filtering`. So sánh qua tracing:

| | Truy vấn theo `sensor_id = 'hn-01'` | `temperature > 31.5 ALLOW FILTERING` |
|---|---|---|
| Cách đọc | single-partition query | range requests trên 49 + 16 range, seq scan |
| Số hàng đọc | 3 | 2208 + 792 = 3000 |
| Số hàng trả về | 3 | 131 |
| Thời gian (Request complete) | 13 167 µs | 72 739 µs |

**Bước 3 - mất node.**

| Số node sống | ONE | QUORUM | ALL |
|---|---|---|---|
| 3 | OK | OK | OK |
| 2 (tắt cass3) | OK | OK | Unavailable: need 3 replicas, 2 alive |
| 1 (tắt thêm cass2) | OK | Unavailable: need 2 replicas, 1 alive | Unavailable: need 3 replicas, 1 alive |

Lỗi `Unavailable` trả về ngay, vì lệnh chỉ được chạy sau khi `nodetool status` đã báo `DN`.

**Bước 4 - bản sao bị cũ.** Bật lại cass2, tắt hinted handoff trên cass1 và cass2 (`statushandoff` báo `not running`), rồi ghi `hn-99` ở mức QUORUM trong lúc cass3 đang tắt. Sau đó bật cass3 và tắt cass1, cass2. Đọc `hn-99` từ cass3 ở mức ONE ra `(0 rows)`, tức cass3 không có lần ghi đó. Bật lại cả ba node rồi đọc ở mức ALL thì ra đúng 1 hàng `hn-99 | 41 | 30`, vì coordinator lấy bản mới nhất và read repair ghi bù cho cass3. Cuối cùng chạy `nodetool repair iot` báo `Repair completed successfully`. Do các node đã khởi động lại nên `statushandoff` lại báo `running`.

## Câu hỏi cho báo cáo

**1. Vì sao token của `hn-01` giống ví dụ, còn IP node sở hữu thì khác?**

Token chỉ phụ thuộc vào giá trị partition key và hàm băm. Cassandra dùng Murmur3Partitioner ở mọi cài đặt, nên `murmur3('hn-01')` ở đâu cũng ra `-6927399588689370405`. Còn node nào sở hữu token đó thì phụ thuộc vào cách các token của node được phân bố trên vòng (mỗi node có 16 vnode được cấp khi join) và vào IP mà Docker cấp cho container. Hai thứ này khác nhau giữa các máy: ở đây mạng Docker là `172.22.0.x` chứ không phải `172.23.0.x` như ví dụ. Dù vậy quy tắc "token kế tiếp theo chiều kim đồng hồ" vẫn đúng, như đã kiểm tra ở Bước 1.

**2. Thêm `cass4` vào cluster có keyspace `ring1` thì các partition hiện có ra sao?**

`cass4` nhận 16 token mới rải trên vòng. Mỗi token mới cắt một đoạn ra khỏi range của node đang đứng sau nó, nên chỉ những partition có token rơi vào các đoạn bị cắt mới chuyển sang `cass4` (streaming từ node cũ sang). Các partition còn lại giữ nguyên chỗ. Không phải di chuyển toàn bộ dữ liệu, chỉ khoảng 1/4 dữ liệu là chuyển sang node mới. Đây là ưu điểm của consistent hashing so với kiểu `hash % số_node`, vốn sẽ xáo trộn gần như mọi key khi số node thay đổi. Sau khi thêm node xong thì chạy `nodetool cleanup` trên các node cũ để xoá phần dữ liệu không còn thuộc về chúng.

**3. `ALLOW FILTERING` đọc bao nhiêu hàng để trả về bao nhiêu hàng? Thiết kế bảng cho "các số đo trên 31.5°C trong một ngày".**

Truy vấn đọc 3000 hàng (2208 ở cass1 + 792 ở range còn lại), tức toàn bộ bảng, để trả về 131 hàng. Khoảng 96% số hàng đọc lên rồi bị bỏ đi.

Bảng thay thế đặt ngày làm partition key và nhiệt độ làm clustering column đầu tiên:

```sql
CREATE TABLE iot.readings_by_day_temp (
    day         date,
    temperature double,
    ts          timestamp,
    sensor_id   text,
    humidity    double,
    PRIMARY KEY ((day), temperature, ts, sensor_id)
) WITH CLUSTERING ORDER BY (temperature DESC, ts ASC, sensor_id ASC);

SELECT * FROM iot.readings_by_day_temp
WHERE day = '2026-10-22' AND temperature > 31.5;
```

Truy vấn chỉ đọc một partition, và vì các hàng trong partition đã được sắp theo nhiệt độ giảm dần nên Cassandra đọc từ đầu partition đến khi gặp giá trị ≤ 31.5 thì dừng. `ts` và `sensor_id` có trong khoá để hai số đo cùng nhiệt độ không ghi đè lên nhau. Khi ghi thì ứng dụng ghi vào cả `readings_by_sensor` lẫn bảng này. Nếu một ngày có quá nhiều số đo thì có thể chia thêm bucket, ví dụ `((day, hour), ...)`.

**4. Bảng kết quả Bước 3, và RF = 5 thì QUORUM cần bao nhiêu bản sao?**

Bảng kết quả ở phần Bước 3 bên trên. Với RF = 5, QUORUM cần ⌊5/2⌋ + 1 = 3 bản sao, nên chịu được mất 5 - 3 = 2 node mà vẫn đọc ghi được ở mức QUORUM.

**5. Ở Bước 4, nếu cả ghi và đọc đều dùng QUORUM thì có đọc phải dữ liệu cũ không?**

Không. Với RF = 3, ghi QUORUM nghĩa là W = 2 bản sao đã xác nhận, đọc QUORUM nghĩa là R = 2 bản sao trả lời. R + W = 4 > RF = 3, nên tập node được đọc và tập node đã ghi luôn có ít nhất một node chung. Node chung đó có bản mới, và coordinator chọn bản có timestamp mới nhất. Ở Bước 4 đọc phải dữ liệu cũ là vì đọc ở mức ONE (R = 1, R + W = 3, không lớn hơn RF), và node duy nhất trả lời lại đúng là node đã bỏ lỡ lần ghi. Nếu đọc QUORUM thì khi chỉ còn cass3 sống, truy vấn sẽ báo `Unavailable` chứ không trả về dữ liệu sai.

**6. Hệ thống IoT chấp nhận mất vài số đo nhưng không được ngừng nhận dữ liệu thì chọn consistency nào cho ghi?**

Chọn `ONE` (hoặc `ANY` nếu cần ưu tiên tính sẵn sàng hơn nữa). Bước 3 cho thấy `ONE` vẫn ghi được khi cluster chỉ còn 1 node, trong khi `QUORUM` và `ALL` đều báo lỗi. Ghi ở `ONE` cũng nhanh nhất vì chỉ chờ một bản sao xác nhận. Đổi lại, nếu node duy nhất nhận ghi chết trước khi kịp đồng bộ thì có thể mất vài số đo, nhưng yêu cầu ở đây chấp nhận điều đó. Các bản sao còn lại sẽ được bù dần qua hinted handoff, read repair và `nodetool repair`. `ANY` còn cho ghi được ngay cả khi không bản sao nào sống (coordinator giữ hint), nhưng khi đó dữ liệu chưa đọc được cho đến khi có bản sao sống lại.

## Bài tập

**1. Bảng "10 đơn mới nhất của một khách hàng" và bảng "đơn theo ngày".**

```sql
CREATE TABLE shop.orders_by_customer (
    customer_id text,
    order_ts    timestamp,
    order_id    int,
    city        text,
    status      text,
    total       double,
    PRIMARY KEY ((customer_id), order_ts, order_id)
) WITH CLUSTERING ORDER BY (order_ts DESC, order_id ASC);

CREATE TABLE shop.orders_by_day (
    day         date,
    order_ts    timestamp,
    order_id    int,
    customer_id text,
    status      text,
    total       double,
    PRIMARY KEY ((day), order_ts, order_id)
) WITH CLUSTERING ORDER BY (order_ts ASC, order_id ASC);
```

Mỗi đơn được ghi vào cả hai bảng (40 đơn ngẫu nhiên của 3 khách). Truy vấn `SELECT ... FROM orders_by_customer WHERE customer_id = 'linh' LIMIT 10` trả về 10 đơn của linh, mới nhất ở trên cùng, không cần `ORDER BY` vì partition đã sắp sẵn theo `order_ts DESC`. `order_id` nằm trong khoá để hai đơn đặt cùng thời điểm không ghi đè nhau (đơn 1008 và 1035 cùng lúc 2026-11-11 08:00 vẫn ra đủ cả hai). Truy vấn `orders_by_day WHERE day = '2026-11-03'` trả về 4 đơn trong ngày, theo thứ tự thời gian.

**2. Thêm số đo cho ba cảm biến và thử truy vấn bỏ qua partition key.**

Ghi 60 số đo cho `dn-01`, `dn-02`, `hue-01`. Truy vấn theo `sensor_id = 'dn-01'` chạy bình thường. Hai truy vấn bỏ qua partition key, `WHERE temperature > 30` và `WHERE ts > '2026-11-10 02:00:00'`, đều bị từ chối với cùng một lỗi:

```
InvalidRequest: code=2200 [Invalid query] message="Cannot execute this query as it might
involve data filtering and thus may have unpredictable performance. If you want to execute
this query despite the performance unpredictability, use ALLOW FILTERING"
```

Lỗi này nói rằng khi không có partition key, Cassandra không biết dữ liệu nằm ở node nào nên phải quét mọi partition trên mọi node rồi lọc, và chi phí tăng theo kích thước bảng. `ts` dù là clustering column vẫn không lọc được, vì clustering column chỉ có tác dụng sắp xếp bên trong một partition đã được chỉ định.

**3. Đổi schema sang partition theo bucket tháng.**

```sql
CREATE TABLE shop.readings_by_sensor_month (
    sensor_id   text,
    month       text,
    ts          timestamp,
    temperature double,
    humidity    double,
    PRIMARY KEY ((sensor_id, month), ts)
) WITH CLUSTERING ORDER BY (ts DESC);
```

Ghi 364 số đo của `dn-01` trong 3 tháng (6 giờ một lần) thì dữ liệu chia thành 3 partition: tháng 9 có 120 hàng, tháng 10 có 124 hàng, tháng 11 có 120 hàng.

Lý do: với `PRIMARY KEY ((sensor_id), ts)`, mọi số đo của một cảm biến từ trước đến nay dồn vào một partition, nên partition lớn mãi không giới hạn. Một cảm biến gửi mỗi giây một lần thì sau một năm partition có khoảng 31 triệu hàng, vượt xa ngưỡng khuyến nghị dưới 100 MB. Partition quá to làm đọc chậm, compaction và repair nặng, và toàn bộ partition chỉ nằm trên vài node nên tải không chia đều. Thêm `month` vào partition key thì mỗi partition chỉ chứa tối đa một tháng dữ liệu, kích thước có giới hạn và biết trước.

Cái giá là truy vấn phải biết tháng. `WHERE sensor_id = 'dn-01'` mà thiếu `month` giờ bị từ chối với lỗi giống bài 2. Muốn lấy một khoảng thời gian vắt qua hai tháng thì ứng dụng phải liệt kê các bucket, ví dụ `month IN ('2026-10', '2026-11') AND ts >= '2026-10-31' AND ts < '2026-11-01 12:00'` trả về 6 hàng lấy từ 2 partition. Cỡ bucket (ngày, tuần hay tháng) nên chọn theo tốc độ ghi của cảm biến, sao cho mỗi partition vẫn nhỏ.
