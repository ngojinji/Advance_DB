# Bài 4 - Neo4j: Lab CampusGraph

Neo4j 5 chạy bằng Docker (`compose.yaml`), dùng driver Python `neo4j`. File `campus.py` đã cài đặt đủ 7 task, kết quả `python campus.py check` nằm trong `check_output.txt` (8/8 dòng `PASS`). Các truy vấn dùng để trả lời câu hỏi báo cáo nằm trong `report_queries.py` / `report_output.txt`. Phần bài tập trên đồ thị cửa hàng ở `store_exercises.py` / `exercises_output.txt`.

## Kết quả lab

```
loaded: {'Course': 13, 'Student': 10}
PASS  1 passed_courses
PASS  2 prerequisite_chain
PASS  3 eligible_courses
PASS  4 suggest_friends
PASS  5 connection
PASS  6 bottleneck_courses
PASS  7a record_pass refuses
PASS  7b record_pass writes
```

Ngoài phần check, các hàm cũng được chạy với những đầu vào khác trong bài và đều ra đúng kết quả mong đợi: `prerequisite_chain("CAP401")`, `eligible_courses("S04")` → `["CS102", "MATH102", "STAT101"]`, `connection("S03", "S05")` → `["Chi", "Minh", "Phuong", "Khoa", "Giang"]`. `record_pass` với sinh viên hoặc môn không tồn tại thì báo `ValueError: unknown student or course`.

Các truy vấn chính:

```cypher
// Task 2
MATCH path = (:Course {code: $code})-[:REQUIRES*1..]->(p:Course)
RETURN p.code AS code, min(length(path)) AS depth
ORDER BY depth, code

// Task 3
MATCH (s:Student {id: $sid}), (c:Course)
WHERE NOT (s)-[:PASSED]->(c)
  AND NOT EXISTS {
      MATCH (c)-[:REQUIRES]->(p:Course)
      WHERE NOT (s)-[:PASSED]->(p)
  }
RETURN c.code AS code ORDER BY code

// Task 6
MATCH (d:Course)-[:REQUIRES*1..]->(c:Course)
RETURN c.code AS code, count(DISTINCT d) AS dependents
ORDER BY dependents DESC, code LIMIT $k
```

Task 7 gồm 3 lệnh `tx.run` trong cùng một transaction: kiểm tra sinh viên và môn có tồn tại không (`OPTIONAL MATCH`), lấy danh sách môn tiên quyết trực tiếp chưa qua, và nếu không thiếu môn nào thì `MERGE (s)-[p:PASSED]->(c) SET p.grade = $grade`. Dùng `MERGE` nên ghi lại lần hai chỉ cập nhật điểm chứ không tạo thêm relationship.

## Câu hỏi cho báo cáo

**1. Bảng SQL và truy vấn SQL cho Task 2**

```sql
CREATE TABLE course  (code TEXT PRIMARY KEY, title TEXT, credits INT);
CREATE TABLE student (id TEXT PRIMARY KEY, name TEXT, year INT);
CREATE TABLE requires (
    course_code TEXT REFERENCES course(code),
    prereq_code TEXT REFERENCES course(code),
    PRIMARY KEY (course_code, prereq_code));
CREATE TABLE passed (
    student_id  TEXT REFERENCES student(id),
    course_code TEXT REFERENCES course(code),
    grade REAL,
    PRIMARY KEY (student_id, course_code));
CREATE TABLE friend (
    a_id TEXT REFERENCES student(id),
    b_id TEXT REFERENCES student(id),
    PRIMARY KEY (a_id, b_id));

WITH RECURSIVE chain(code, depth) AS (
    SELECT prereq_code, 1 FROM requires WHERE course_code = :code
    UNION ALL
    SELECT r.prereq_code, c.depth + 1
    FROM chain c JOIN requires r ON r.course_code = c.code
)
SELECT code, MIN(depth) AS depth
FROM chain
GROUP BY code
ORDER BY depth, code;
```

Truy vấn này đã được chạy thử trên SQLite và ra cùng kết quả với Cypher, cả cho DE301 lẫn CAP401.

Bản SQL dài khoảng 10 dòng và phải chia làm hai phần: phần neo (bước đầu tiên) và phần đệ quy tự join với chính nó. Người đọc phải hình dung được vòng lặp mới hiểu truy vấn làm gì. Bản Cypher chỉ có 3 dòng, và `-[:REQUIRES*1..]->` đọc lên đúng như câu "đi theo REQUIRES một hoặc nhiều bước". Phần tổng hợp `MIN(depth) ... GROUP BY` thì hai bên giống nhau. Ngoài ra bảng `requires` trong SQL chỉ là bảng nối, còn trong Neo4j quan hệ là thành phần chính của mô hình.

**2. Vì sao Task 2 chỉ trả về mỗi môn một lần? Có bao nhiêu đường đi từ CAP401 tới CS101?**

`MATCH path = ...-[:REQUIRES*1..]->(p)` trả về một hàng cho mỗi đường đi, nên một môn tới được bằng nhiều đường sẽ xuất hiện nhiều lần. Trong `RETURN p.code, min(length(path))`, `p.code` tự động trở thành khoá nhóm, nên các hàng cùng môn được gộp làm một và chỉ giữ độ dài ngắn nhất. Với CAP401, trước khi gộp có 11 hàng (11 đường đi tới các môn tiên quyết), sau khi gộp còn 8 môn.

Từ CAP401 tới CS101 có **2 đường**:

```
CAP401 -> ML201 -> CS102 -> CS101              (3 bước)
CAP401 -> DB301 -> DB201 -> CS102 -> CS101     (4 bước)
```

Vì vậy CS101 có depth = 3.

**3. Operator đầu tiên và số db hits khi có và không có constraint**

PROFILE truy vấn Task 3 với `"S01"`:

| | Có constraint `student_id` | Không có constraint |
|---|---|---|
| Operator tìm sinh viên | `NodeUniqueIndexSeek` (`UNIQUE s:Student(id) WHERE id = $sid`) | `NodeByLabelScan` (`s:Student`) rồi `Filter` |
| Tổng db hits | 194 | 213 |

Khi có constraint, Neo4j có sẵn unique index trên `Student.id` nên nhảy thẳng tới đúng một node. Khi không có, nó phải đọc mọi node `:Student` rồi lọc theo `id`. Hiện giờ chỉ chênh 19 db hits vì mới có 10 sinh viên, và phần lớn chi phí nằm ở chỗ kiểm tra 13 môn học. Với 100.000 sinh viên, `NodeByLabelScan` phải đọc 100.000 node và lọc 100.000 lần cho mỗi lần gọi hàm, nên số db hits tăng lên vài trăm nghìn. Trong khi đó `NodeUniqueIndexSeek` vẫn chỉ tốn vài db hits, gần như không đổi. Phần còn lại của truy vấn chỉ phụ thuộc vào số môn học chứ không phụ thuộc vào số sinh viên.

**4. Vì sao FRIEND chỉ lưu một chiều? Lưu cả hai chiều thì Task 4, Task 5 sai ở đâu?**

Tình bạn là quan hệ đối xứng, và Neo4j cho phép duyệt relationship theo cả hai chiều với cùng một chi phí (`-[:FRIEND]-`). Vì vậy lưu một chiều là đủ để biểu diễn, đỡ tốn chỗ, và không có nguy cơ hai chiều lệch nhau (ví dụ xoá chiều này mà quên chiều kia).

Để kiểm tra, cả 11 cặp bạn được thêm chiều ngược lại (thành 22 relationship) rồi chạy lại hai hàm. Với cách viết hiện tại, Task 4 và Task 5 vẫn ra đúng: `connection("S01", "S08")` vẫn là `An, Binh, Dung, Lan`, `suggest_friends("S02")` vẫn là `Minh 4, Phuong 4, Chi 3`. Lý do là Task 4 dùng điều kiện tồn tại `NOT (s)-[:FRIEND]-(o)` và đếm `count(DISTINCT c)`, còn Task 5 dùng `shortestPath`, nên số relationship giữa hai người không ảnh hưởng.

Nhưng chỉ cần liệt kê bạn bè theo kiểu không hướng là kết quả bị nhân đôi: bạn của An ra `['Binh', 'Giang', 'Binh', 'Giang']`. Nếu Task 4 viết theo kiểu đi qua bạn bè (bạn của bạn) và đếm `count(*)` thay vì `DISTINCT`, mỗi người sẽ bị đếm gấp đôi, và thứ hạng có thể sai khi các cặp chênh nhau. Task 5 không sai về kết quả, nhưng `shortestPath` phải duyệt gấp đôi số relationship, và nếu đổi sang `allShortestPaths` thì mỗi đường đi xuất hiện nhiều lần với các tổ hợp chiều khác nhau. Nói chung, lưu hai chiều không thêm thông tin gì mà chỉ thêm việc phải nhớ dùng `DISTINCT` ở khắp nơi.

**5. Lưu mọi lần học (trượt rồi học lại): điểm trên relationship hay node `:Enrollment`?**

Cần một node `:Enrollment`. Điểm nằm trên `PASSED` chỉ ổn khi mỗi cặp (sinh viên, môn) có đúng một kết quả. Nếu dùng nhiều relationship song song cho cùng một cặp thì `MERGE` ở Task 7 không còn dùng được, và rất khó gắn thêm thông tin cho từng lần học như học kỳ, giảng viên hay lớp. Mô hình mới:

```
(:Student)-[:TOOK]->(:Enrollment {semester, grade, status})-[:OF]->(:Course)
```

Mỗi lần học là một node riêng. Có thể nối thêm `(:Enrollment)-[:TAUGHT_BY]->(:Lecturer)` nếu cần.

Task 1 viết lại (lấy điểm cao nhất trong các lần đã qua):

```cypher
MATCH (:Student {id: $sid})-[:TOOK]->(e:Enrollment {status: 'passed'})-[:OF]->(c:Course)
WITH c.code AS code, max(e.grade) AS grade
RETURN code, grade
ORDER BY grade DESC, code
```

Đã thử trên dữ liệu: thêm cho S04 lần học CS102 bị trượt (3.5, học kỳ 2025-1) và lần học lại đạt (7.0, học kỳ 2025-2). Truy vấn trên trả về `[('MATH101', 7.5), ('CS102', 7.0), ('CS101', 6.5)]`, và vẫn xem được đủ lịch sử hai lần học. Các task 3 và 7 cũng phải đổi `(s)-[:PASSED]->(p)` thành `(s)-[:TOOK]->(:Enrollment {status: 'passed'})-[:OF]->(p)`.

**6. Task 7: kiểm tra và ghi nằm ở hai `execute_query` riêng, trong khi chương trình khác đang xoá `PASSED` thì sao?**

Mỗi `execute_query` là một transaction tự commit riêng. Thứ tự sau đây có thể xảy ra:

1. Lệnh kiểm tra thấy S08 đã qua CS101 → hợp lệ.
2. Chương trình kia xoá `(S08)-[:PASSED]->(CS101)` và commit.
3. Lệnh ghi tạo `(S08)-[:PASSED]->(CS102)`.

Kết quả là S08 đã qua CS102 nhưng không qua CS101, dữ liệu vi phạm đúng quy tắc mà hàm muốn bảo vệ. Đây là lỗi check-then-act, giống bài giữ ghế ở lab Redis. Ngoài ra nếu lệnh ghi lỗi giữa chừng thì cũng không có gì để rollback cùng với bước kiểm tra.

Gộp vào một `execute_write` thì kiểm tra và ghi cùng commit hoặc cùng rollback: ném `ValueError` sẽ huỷ cả transaction nên không có gì được ghi, và driver tự thử lại khi gặp lỗi tạm thời. Cần lưu ý là Neo4j mặc định ở mức read committed, nên lệnh đọc không khoá dữ liệu. Muốn chặn hẳn trường hợp bị xoá chen vào thì trong transaction có thể khoá các relationship `PASSED` của môn tiên quyết trước khi kiểm tra (ví dụ `SET p._lock = true` rồi `REMOVE`), hoặc gộp kiểm tra và ghi thành một câu Cypher duy nhất.

## Bài tập

Các bài này làm trên đồ thị cửa hàng (Linh, Nam, Mai, Hung và 3 cuốn sách) tạo đúng như trong bài.

**1. Thêm 5 người, tìm bạn của bạn của Linh ở Hà Nội.** Thêm Tuan, Vy, Quang, Thao, Duc bằng `UNWIND ... MERGE`, cùng 6 quan hệ bạn bè mới. Bạn trực tiếp của Linh là Nam và Tuan.

```cypher
MATCH (me:Person {name: "Linh"})-[:FRIEND]-(:Person)-[:FRIEND]-(fof:Person)
WHERE fof <> me AND NOT (me)-[:FRIEND]-(fof) AND fof.city = "Hanoi"
RETURN DISTINCT fof.name
```

Kết quả: **Duc, Mai, Quang**. Phải loại chính Linh (đi Linh → Nam → Linh) và những người đã là bạn trực tiếp. `DISTINCT` cần thiết vì một người có thể tới được qua nhiều người bạn chung.

**2. Gợi ý sách cho Mai và tổng tiền mỗi người đã chi.** Theo bạn bè: sách bạn của Mai đã mua mà Mai chưa mua → **SQL in Practice** (từ Nam). Theo kiểu "người mua cùng sách cũng mua": cũng ra SQL in Practice, với 2 người (Linh mua chung Python Basics, Nam mua chung Data Viz).

| Người | Số sách | Đã chi |
|---|---:|---:|
| Nam | 2 | 285 000 |
| Linh | 2 | 270 000 |
| Mai | 2 | 255 000 |
| những người còn lại | 0 | 0 |

Dùng `OPTIONAL MATCH` để những người chưa mua gì vẫn hiện ra với 0, thay vì biến mất khỏi kết quả.

**3. Mạng metro.** Dựng một mạng đơn giản lấy tên ga ở Hà Nội gồm 15 ga, chia làm 3 tuyến: tuyến 2A Cát Linh - Yên Nghĩa, tuyến 3 Nhổn - Ga Hà Nội (giao với 2A ở Láng), và một tuyến giả định X Cầu Giấy - Nguyễn Trãi - Văn Quán. Mỗi đoạn là `(:Station)-[:NEXT {minutes, line}]->(:Station)`.

```cypher
MATCH (a:Station {name: $a}), (b:Station {name: $b}),
      p = shortestPath((a)-[:NEXT*..30]-(b))
RETURN [s IN nodes(p) | s.name] AS route, length(p) AS hops,
       reduce(t = 0, r IN relationships(p) | t + r.minutes) AS minutes
```

| Từ → đến | Số đoạn | Phút | Tuyến |
|---|---:|---:|---|
| Cát Linh → Yên Nghĩa | 8 | 31 | Cát Linh, La Thành, Thái Hà, Láng, Cầu Giấy, Nguyễn Trãi, Văn Quán, Hà Đông, Yên Nghĩa |
| Nhổn → Hà Đông | 4 | 25 | Nhổn, Cầu Giấy, Nguyễn Trãi, Văn Quán, Hà Đông |
| Ga Hà Nội → Văn Quán | 5 | 24 | Ga Hà Nội, Kim Mã, Láng, Cầu Giấy, Nguyễn Trãi, Văn Quán |

Duyệt không hướng vì tàu chạy cả hai chiều. Ví dụ Cát Linh → Yên Nghĩa cho thấy `shortestPath` chỉ đếm số ga chứ không đếm thời gian: tuyến tìm được đi qua 8 đoạn mất 31 phút, trong khi đi thẳng tuyến 2A tuy qua 9 đoạn nhưng chỉ mất 24 phút. Muốn tìm tuyến nhanh nhất theo `minutes` thì cần thuật toán có trọng số như Dijkstra của thư viện GDS.

**4. Lịch sử làm việc theo hai cách.**

- Cách 1: `(:Person)-[:WORKED_AT {title, start, end}]->(:Company)`
- Cách 2: `(:Person)-[:HELD]->(:Job {title, start, end})-[:AT]->(:Company)`

Cách 1 gọn, truy vấn ngắn, hợp với các câu hỏi chỉ xoay quanh người và công ty. Ví dụ "ai đang làm ở Viettel" (`WHERE w.end IS NULL`, ra Mai và Linh), hay "ai từng làm cùng thời điểm với Linh ở FPT" (so khoảng `start`/`end` của hai relationship, ra Nam).

Cách 2 dài hơn một bước nhưng mỗi vị trí công việc là một node, nên có thể nối thêm quan hệ vào chính vị trí đó. Trong bài đã thử `(:Job)-[:PROMOTED_TO]->(:Job)` (Linh từ Intern lên Data Analyst) và `(:Job)-[:REPORTS_TO]->(:Person)` (Nam làm Developer báo cáo cho Hung). Cách 1 không làm được hai việc này, vì Neo4j không cho relationship trỏ vào relationship. Cách 2 cũng xử lý tự nhiên trường hợp một người giữ nhiều vị trí ở cùng công ty: Linh có 2 vị trí ở FPT. Tóm lại, nếu chỉ cần hỏi ai làm ở đâu, khi nào thì dùng cách 1. Nếu bản thân vị trí công việc cũng có quan hệ với thứ khác (quản lý, dự án, thăng chức) thì dùng cách 2.

**5. PROFILE trước và sau khi tạo uniqueness constraint.**

```
MATCH (p:Person {name: "Linh"}) RETURN p
```

| | Trước | Sau |
|---|---|---|
| Kế hoạch | `NodeByLabelScan` (9 rows) → `Filter` → `ProduceResults` | `NodeUniqueIndexSeek` (1 row) → `ProduceResults` |
| Tổng db hits | 23 | 5 |

Trước khi có constraint, Neo4j không có index trên `Person.name`, nên phải đọc cả 9 node `:Person` rồi lọc lấy node có `name = "Linh"`. `CREATE CONSTRAINT ... REQUIRE p.name IS UNIQUE` tự tạo một unique index, nên sau đó Neo4j tìm thẳng tới node Linh trong index. Số db hits giảm từ 23 xuống 5, và mức chênh này tăng theo số người trong đồ thị. Constraint còn chặn dữ liệu trùng: tạo thêm một người tên Linh bị báo `ConstraintError`.
