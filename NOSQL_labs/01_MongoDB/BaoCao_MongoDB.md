# Bài 1 - MongoDB

MongoDB 8 chạy bằng Docker (file `compose.yaml`), bài làm bằng Python với pymongo. Code ở file `mongodb_exercises.py`, kết quả chạy ở `output.txt`.

## Bài tập 1

Ngoài 3 đơn có sẵn trong bài (1001-1003), thêm 5 đơn 1004-1008, mỗi đơn có cấu trúc khác nhau:

- 1004: có thêm địa chỉ giao hàng lồng nhiều cấp (`shipping.address`) và ghi chú `note`
- 1005: thanh toán làm 2 lần nên `payments` là một mảng; sản phẩm là ebook có thêm `format`, `download_limit`
- 1006: khách hàng có email, số điện thoại, đơn có `rating`
- 1007: đơn bị huỷ, không có `items`, chỉ có thông tin `cancel`
- 1008: khách là công ty, có `tax_id`; một dòng hàng có `discount_pct`, một dòng là combo

Insert vào collection bình thường, không cần sửa schema gì cả.

Truy vấn tìm các đơn có chứa một sku:

```js
db.orders.find({ "items.sku": "BK-01" })
```

Với `BK-01` ra 4 đơn là 1001, 1003, 1004, 1008. Với `BK-03` ra 1002 và 1006. Mặc dù `items` là mảng nhưng chỉ cần viết `items.sku` là MongoDB tự tìm trong từng phần tử của mảng. Đơn 1007 không có `items` thì cũng không bị lỗi, chỉ là không khớp.

## Bài tập 2

```js
db.orders.aggregate([
  { $match: { status: { $in: ["paid", "shipped"] } } },
  { $unwind: "$items" },
  { $group: {
      _id: "$customer.city",
      orders: { $addToSet: "$_id" },
      revenue: { $sum: { $multiply: [
        "$items.qty", "$items.price",
        { $subtract: [1, { $divide: [{ $ifNull: ["$items.discount_pct", 0] }, 100] }] }
      ] } }
  } },
  { $project: { _id: 0, city: "$_id", num_orders: { $size: "$orders" },
                revenue: { $round: ["$revenue", 2] } } },
  { $sort: { revenue: -1 } }
])
```

| Thành phố | Số đơn | Doanh thu |
|---|---:|---:|
| Hanoi | 3 | 455.5 |
| Da Nang | 2 | 80.0 |
| Hue | 1 | 12.5 |
| Ho Chi Minh | 1 | 9.9 |

Chỉ tính đơn `paid` và `shipped`, bỏ đơn đã huỷ. Vì đơn 1008 có giảm giá 10% ở một dòng hàng nên nhân thêm `(1 - discount_pct/100)`, các đơn không có trường này thì `$ifNull` cho về 0. Số đơn đếm bằng `$addToSet` vì sau `$unwind` một đơn có nhiều mặt hàng sẽ bị tách thành nhiều dòng, nếu `$sum: 1` thì sẽ đếm sai.

Kiểm tra lại Hà Nội: 1001 = 2×12.5 + 18 = 43, 1003 = 12.5, 1008 = 20×12.5×0.9 + 5×35 = 400, tổng 455.5, đúng với kết quả.

## Bài tập 3

Sinh ngẫu nhiên 10.000 đơn vào collection `orders_big` rồi chạy `explain` cho truy vấn `{ "customer.city": "Hanoi", status: "paid" }` trước và sau khi tạo index `{ "customer.city": 1, status: 1 }`.

| | Trước | Sau |
|---|---|---|
| Stage | COLLSCAN | IXSCAN → FETCH |
| nReturned | 253 | 253 |
| totalKeysExamined | 0 | 253 |
| totalDocsExamined | 10000 | 253 |
| executionTimeMillis | 5 | 1 |

Khi chưa có index, MongoDB phải đọc hết 10.000 document để lấy ra 253 kết quả. Sau khi có index thì nó chỉ đọc đúng 253 document cần lấy. Thời gian chênh nhau không nhiều vì dữ liệu còn nhỏ, nhưng số document phải đọc giảm khoảng 40 lần. Nếu collection lên tới hàng triệu document thì khác biệt sẽ rõ hơn nhiều.
