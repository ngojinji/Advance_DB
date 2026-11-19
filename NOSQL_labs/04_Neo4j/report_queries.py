import sqlite3
import sys

import campus
from campus import driver

sys.stdout.reconfigure(encoding="utf-8")


def extra_examples():
    print("=== Vi du them ===")
    campus.setup()
    print("prerequisite_chain('CAP401') =", campus.prerequisite_chain("CAP401"))
    print("eligible_courses('S04') =", campus.eligible_courses("S04"))
    print("connection('S03', 'S05') =", campus.connection("S03", "S05"))
    print("suggest_friends('S08') =", campus.suggest_friends("S08"))
    print("bottleneck_courses(5) =", campus.bottleneck_courses(5))
    for args in [("S99", "CS101", 8.0), ("S01", "XX999", 8.0)]:
        try:
            campus.record_pass(*args)
        except ValueError as e:
            print(f"record_pass{args} -> ValueError: {e}")


def q1_sql():
    print("\n=== Cau 1: SQL WITH RECURSIVE (sqlite) ===")
    con = sqlite3.connect(":memory:")
    con.executescript("""
        CREATE TABLE course (code TEXT PRIMARY KEY, title TEXT, credits INT);
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
    """)
    con.executemany("INSERT INTO course VALUES (?, ?, ?)", campus.COURSES)
    con.executemany("INSERT INTO requires VALUES (?, ?)", campus.REQUIRES)
    sql = """
        WITH RECURSIVE chain(code, depth) AS (
            SELECT prereq_code, 1 FROM requires WHERE course_code = :code
            UNION ALL
            SELECT r.prereq_code, c.depth + 1
            FROM chain c JOIN requires r ON r.course_code = c.code
        )
        SELECT code, MIN(depth) AS depth
        FROM chain
        GROUP BY code
        ORDER BY depth, code;"""
    for code in ["DE301", "CAP401"]:
        print(code, con.execute(sql, {"code": code}).fetchall())


def q2_paths():
    print("\n=== Cau 2: so duong di CAP401 -> CS101 ===")
    records = driver.execute_query("""
        MATCH path = (:Course {code: 'CAP401'})-[:REQUIRES*1..]->(:Course {code: 'CS101'})
        RETURN [n IN nodes(path) | n.code] AS route, length(path) AS len
        ORDER BY len, route""").records
    for r in records:
        print(" -> ".join(r["route"]), f"(do dai {r['len']})")
    print("tong so duong di:", len(records))
    n = driver.execute_query("""
        MATCH path = (:Course {code: 'CAP401'})-[:REQUIRES*1..]->(p:Course)
        RETURN count(path) AS rows_before, count(DISTINCT p) AS rows_after""").records[0]
    print("so hang truoc khi gom:", n["rows_before"], "| sau khi gom theo mon:", n["rows_after"])


def walk(plan):
    yield plan
    for child in plan.get("children", []):
        yield from walk(child)


def profile_task3():
    summary = driver.execute_query("PROFILE " + campus.ELIGIBLE_QUERY, sid="S01").summary
    ops = list(walk(summary.profile))
    leaves = [op for op in ops if not op.get("children")]
    total = sum(op.get("dbHits", 0) for op in ops)
    names = [op["operatorType"].split("@")[0] for op in ops]
    return leaves, total, names


def q3_profile():
    print("\n=== Cau 3: PROFILE Task 3 voi S01 ===")
    campus.setup()
    leaves, total, names = profile_task3()
    print("CO constraint:")
    print("  cac operator:", names)
    print("  operator dau tien (la):", [(l["operatorType"].split("@")[0], l["args"].get("Details", "")) for l in leaves])
    print("  tong db hits:", total)

    driver.execute_query("DROP CONSTRAINT student_id")
    leaves, total, names = profile_task3()
    print("KHONG constraint student_id:")
    print("  cac operator:", names)
    print("  operator dau tien (la):", [(l["operatorType"].split("@")[0], l["args"].get("Details", "")) for l in leaves])
    print("  tong db hits:", total)
    driver.execute_query(
        "CREATE CONSTRAINT student_id IF NOT EXISTS FOR (s:Student) REQUIRE s.id IS UNIQUE")
    print("da tao lai constraint student_id")


def q4_both_directions():
    print("\n=== Cau 4: luu FRIEND ca hai chieu ===")
    campus.setup()
    driver.execute_query("""
        MATCH (a:Student)-[:FRIEND]->(b:Student)
        MERGE (b)-[:FRIEND]->(a)""")
    n = driver.execute_query("MATCH ()-[f:FRIEND]->() RETURN count(f) AS n").records[0]["n"]
    print("so relationship FRIEND:", n)
    print("connection('S01', 'S08') =", campus.connection("S01", "S08"))
    print("suggest_friends('S02') =", campus.suggest_friends("S02"))
    r = driver.execute_query("""
        MATCH (s:Student {id: 'S01'})-[:FRIEND]-(f)
        RETURN collect(f.name) AS friends""").records[0]["friends"]
    print("ban cua An (khong huong):", r)
    campus.setup()


def q5_enrollment():
    print("\n=== Cau 5: mo hinh :Enrollment ===")
    campus.setup()
    driver.execute_query("""
        MATCH (s:Student)-[p:PASSED]->(c:Course)
        CREATE (s)-[:TOOK]->(:Enrollment {semester: '2025-1', grade: p.grade, status: 'passed'})-[:OF]->(c)""")
    driver.execute_query("""
        MATCH (s:Student {id: 'S04'}), (c:Course {code: 'CS102'})
        CREATE (s)-[:TOOK]->(:Enrollment {semester: '2025-1', grade: 3.5, status: 'failed'})-[:OF]->(c)
        CREATE (s)-[:TOOK]->(:Enrollment {semester: '2025-2', grade: 7.0, status: 'passed'})-[:OF]->(c)""")
    records = driver.execute_query("""
        MATCH (:Student {id: $sid})-[:TOOK]->(e:Enrollment {status: 'passed'})-[:OF]->(c:Course)
        WITH c.code AS code, max(e.grade) AS grade
        RETURN code, grade
        ORDER BY grade DESC, code""", sid="S04").records
    print("passed_courses tren mo hinh moi, S04:", [(r["code"], r["grade"]) for r in records])
    records = driver.execute_query("""
        MATCH (:Student {id: 'S04'})-[:TOOK]->(e:Enrollment)-[:OF]->(:Course {code: 'CS102'})
        RETURN e.semester AS semester, e.grade AS grade, e.status AS status
        ORDER BY semester""").records
    print("lich su hoc CS102 cua S04:", [dict(r) for r in records])
    campus.setup()


if __name__ == "__main__":
    try:
        extra_examples()
        q1_sql()
        q2_paths()
        q3_profile()
        q4_both_directions()
        q5_enrollment()
    finally:
        driver.close()
