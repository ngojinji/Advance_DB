import sys

from neo4j import GraphDatabase

sys.stdout.reconfigure(encoding="utf-8")

driver = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "learnneo4j"))


def run(cypher, **params):
    return driver.execute_query(cypher, params).records


def show(records):
    for r in records:
        print("  ", dict(r))


def load_store():
    run("MATCH (n) DETACH DELETE n")
    run("DROP CONSTRAINT person_name IF EXISTS")
    run("""
        CREATE (linh:Person {name: "Linh", city: "Hanoi", age: 21}),
               (nam:Person  {name: "Nam",  city: "Da Nang", age: 22}),
               (mai:Person  {name: "Mai",  city: "Hanoi", age: 20}),
               (hung:Person {name: "Hung", city: "Hue", age: 23}),
               (py:Book  {title: "Python Basics", price: 120000}),
               (sql:Book {title: "SQL in Practice", price: 150000}),
               (viz:Book {title: "Data Viz", price: 135000}),
               (linh)-[:FRIEND {since: 2023}]->(nam),
               (nam)-[:FRIEND {since: 2024}]->(mai),
               (mai)-[:FRIEND {since: 2025}]->(hung),
               (linh)-[:BOUGHT {year: 2026}]->(py),
               (linh)-[:BOUGHT {year: 2026}]->(sql),
               (nam)-[:BOUGHT {year: 2025}]->(sql),
               (nam)-[:BOUGHT {year: 2026}]->(viz),
               (mai)-[:BOUGHT {year: 2026}]->(py),
               (mai)-[:BOUGHT {year: 2026}]->(viz)""")


def bai1():
    print("--- Bai 1 ---")
    run("""
        UNWIND $people AS row
        MERGE (p:Person {name: row.name})
        SET p.city = row.city, p.age = row.age""", people=[
        {"name": "Tuan", "city": "Hanoi", "age": 22},
        {"name": "Vy", "city": "Can Tho", "age": 21},
        {"name": "Quang", "city": "Hanoi", "age": 24},
        {"name": "Thao", "city": "Da Nang", "age": 20},
        {"name": "Duc", "city": "Hanoi", "age": 23},
    ])
    run("""
        UNWIND $pairs AS pair
        MATCH (a:Person {name: pair[0]}), (b:Person {name: pair[1]})
        MERGE (a)-[:FRIEND {since: pair[2]}]->(b)""", pairs=[
        ["Linh", "Tuan", 2024], ["Nam", "Quang", 2025], ["Nam", "Thao", 2023],
        ["Tuan", "Duc", 2022], ["Tuan", "Vy", 2025], ["Thao", "Duc", 2026],
    ])
    print("so nguoi:", run("MATCH (p:Person) RETURN count(p) AS n")[0]["n"])
    print("ban truc tiep cua Linh:")
    show(run("""MATCH (:Person {name: "Linh"})-[:FRIEND]-(f:Person)
                RETURN f.name AS name, f.city AS city ORDER BY name"""))
    print("ban cua ban cua Linh dang song o Hanoi:")
    show(run("""
        MATCH (me:Person {name: "Linh"})-[:FRIEND]-(:Person)-[:FRIEND]-(fof:Person)
        WHERE fof <> me
          AND NOT (me)-[:FRIEND]-(fof)
          AND fof.city = "Hanoi"
        RETURN DISTINCT fof.name AS name, fof.city AS city
        ORDER BY name"""))


def bai2():
    print("\n--- Bai 2 ---")
    print("goi y sach cho Mai (ban cua Mai mua, Mai chua mua):")
    show(run("""
        MATCH (me:Person {name: "Mai"})-[:FRIEND]-(friend:Person)-[:BOUGHT]->(book:Book)
        WHERE NOT (me)-[:BOUGHT]->(book)
        RETURN book.title AS recommendation, collect(DISTINCT friend.name) AS from_friends,
               count(DISTINCT friend) AS score
        ORDER BY score DESC, recommendation"""))
    print("goi y kieu 'nguoi mua cung sach voi Mai cung mua':")
    show(run("""
        MATCH (me:Person {name: "Mai"})-[:BOUGHT]->(:Book)<-[:BOUGHT]-(other:Person)-[:BOUGHT]->(book:Book)
        WHERE other <> me AND NOT (me)-[:BOUGHT]->(book)
        RETURN book.title AS recommendation, count(DISTINCT other) AS also_bought
        ORDER BY also_bought DESC, recommendation"""))
    print("tong tien moi nguoi da chi:")
    show(run("""
        MATCH (p:Person)
        OPTIONAL MATCH (p)-[:BOUGHT]->(b:Book)
        RETURN p.name AS person, count(b) AS books, coalesce(sum(b.price), 0) AS spent
        ORDER BY spent DESC, person"""))


def bai3():
    print("\n--- Bai 3 ---")
    run("MATCH (s:Station) DETACH DELETE s")
    line_a = [("Cat Linh", 0), ("La Thanh", 2), ("Thai Ha", 2), ("Lang", 3),
              ("Thuong Dinh", 3), ("Vanh Dai 3", 2), ("Phung Khoang", 3), ("Van Quan", 2),
              ("Ha Dong", 3), ("Yen Nghia", 4)]
    line_b = [("Nhon", 0), ("Cau Giay", 9), ("Lang", 4), ("Kim Ma", 3), ("Ga Ha Noi", 4)]
    line_c = [("Cau Giay", 0), ("Nguyen Trai", 6), ("Van Quan", 7)]
    for line, stations in [("2A", line_a), ("3", line_b), ("X", line_c)]:
        run("""
            UNWIND range(0, size($stations) - 1) AS i
            MERGE (s:Station {name: $stations[i][0]})
            SET s.lines = CASE WHEN $line IN coalesce(s.lines, []) THEN s.lines
                               ELSE coalesce(s.lines, []) + $line END""",
            stations=[list(s) for s in stations], line=line)
        run("""
            UNWIND range(1, size($stations) - 1) AS i
            MATCH (a:Station {name: $stations[i-1][0]}), (b:Station {name: $stations[i][0]})
            MERGE (a)-[:NEXT {minutes: $stations[i][1], line: $line}]->(b)""",
            stations=[list(s) for s in stations], line=line)
    n = run("MATCH (s:Station) RETURN count(s) AS n")[0]["n"]
    m = run("MATCH ()-[r:NEXT]->() RETURN count(r) AS n")[0]["n"]
    print(f"{n} ga, {m} doan NEXT")

    for a, b in [("Cat Linh", "Yen Nghia"), ("Nhon", "Ha Dong"), ("Ga Ha Noi", "Van Quan")]:
        rec = run("""
            MATCH (a:Station {name: $a}), (b:Station {name: $b}),
                  p = shortestPath((a)-[:NEXT*..30]-(b))
            RETURN [s IN nodes(p) | s.name] AS route, length(p) AS hops,
                   reduce(t = 0, r IN relationships(p) | t + r.minutes) AS minutes""", a=a, b=b)[0]
        print(f"{a} -> {b}: {rec['hops']} doan, {rec['minutes']} phut")
        print("   ", " -> ".join(rec["route"]))

    print("tat ca tuyen ngan nhat Nhon -> Ha Dong:")
    for r in run("""
            MATCH (a:Station {name: "Nhon"}), (b:Station {name: "Ha Dong"}),
                  p = allShortestPaths((a)-[:NEXT*..30]-(b))
            RETURN [s IN nodes(p) | s.name] AS route,
                   reduce(t = 0, r IN relationships(p) | t + r.minutes) AS minutes
            ORDER BY minutes"""):
        print("   ", " -> ".join(r["route"]), f"({r['minutes']} phut)")


def bai4():
    print("\n--- Bai 4 ---")
    run("MATCH (n) WHERE n:Company OR n:Job DETACH DELETE n")
    run("MATCH ()-[w:WORKED_AT]->() DELETE w")
    history = [
        ("Linh", "FPT", "Intern", "2022-06-01", "2022-12-31"),
        ("Linh", "FPT", "Data Analyst", "2023-01-01", "2024-08-31"),
        ("Linh", "Viettel", "Data Engineer", "2024-09-01", None),
        ("Nam", "FPT", "Developer", "2021-03-01", "2023-06-30"),
        ("Nam", "VNG", "Senior Developer", "2023-07-01", None),
        ("Mai", "Viettel", "Tester", "2023-02-01", None),
    ]
    rows = [dict(zip(["person", "company", "title", "start", "end"], h)) for h in history]

    run("""
        UNWIND $rows AS r
        MATCH (p:Person {name: r.person})
        MERGE (c:Company {name: r.company})
        CREATE (p)-[:WORKED_AT {title: r.title, start: date(r.start),
                                end: CASE WHEN r.end IS NULL THEN null ELSE date(r.end) END}]->(c)""",
        rows=rows)
    run("""
        UNWIND $rows AS r
        MATCH (p:Person {name: r.person}), (c:Company {name: r.company})
        CREATE (p)-[:HELD]->(j:Job {title: r.title, start: date(r.start),
                                     end: CASE WHEN r.end IS NULL THEN null ELSE date(r.end) END})-[:AT]->(c)""",
        rows=rows)
    run("""
        MATCH (:Person {name: "Linh"})-[:HELD]->(j1:Job {title: "Intern"}),
              (:Person {name: "Linh"})-[:HELD]->(j2:Job {title: "Data Analyst"})
        CREATE (j1)-[:PROMOTED_TO]->(j2)""")
    run("""
        MATCH (j:Job {title: "Developer"})<-[:HELD]-(:Person {name: "Nam"}),
              (mgr:Person {name: "Hung"})
        CREATE (j)-[:REPORTS_TO]->(mgr)""")

    print("Cach 1 - property tren relationship:")
    print(" ai dang lam o Viettel:")
    show(run("""
        MATCH (p:Person)-[w:WORKED_AT]->(:Company {name: "Viettel"})
        WHERE w.end IS NULL
        RETURN p.name AS name, w.title AS title, toString(w.start) AS since"""))
    print(" nhung ai tung lam cung luc o FPT voi Linh:")
    show(run("""
        MATCH (me:Person {name: "Linh"})-[a:WORKED_AT]->(c:Company {name: "FPT"})<-[b:WORKED_AT]-(other:Person)
        WHERE other <> me AND a.start <= coalesce(b.end, date()) AND b.start <= coalesce(a.end, date())
        RETURN DISTINCT other.name AS colleague, c.name AS company"""))

    print("Cach 2 - node trung gian :Job:")
    print(" lich su cong viec cua Linh:")
    show(run("""
        MATCH (:Person {name: "Linh"})-[:HELD]->(j:Job)-[:AT]->(c:Company)
        RETURN j.title AS title, c.name AS company, toString(j.start) AS start,
               toString(j.end) AS end
        ORDER BY j.start"""))
    print(" thang chuc va quan ly (chi lam duoc khi Job la node):")
    show(run("""
        MATCH (a:Job)-[:PROMOTED_TO]->(b:Job)<-[:HELD]-(p:Person)
        RETURN p.name AS person, a.title AS from_title, b.title AS to_title"""))
    show(run("""
        MATCH (p:Person)-[:HELD]->(j:Job)-[:REPORTS_TO]->(m:Person)
        RETURN p.name AS person, j.title AS title, m.name AS manager"""))


def bai5():
    print("\n--- Bai 5 ---")
    run("DROP CONSTRAINT person_name IF EXISTS")

    def profile():
        summary = driver.execute_query('PROFILE MATCH (p:Person {name: "Linh"}) RETURN p').summary

        def walk(plan):
            yield plan
            for c in plan.get("children", []):
                yield from walk(c)

        ops = list(walk(summary.profile))
        for op in ops:
            print(f"   {op['operatorType'].split('@')[0]:<22} rows={op.get('rows')} dbHits={op.get('dbHits')}"
                  f"  {op['args'].get('Details', '')}")
        print("   tong db hits:", sum(op.get("dbHits", 0) for op in ops))

    print("TRUOC khi tao constraint:")
    profile()
    run("CREATE CONSTRAINT person_name IF NOT EXISTS FOR (p:Person) REQUIRE p.name IS UNIQUE")
    print("SAU khi tao constraint:")
    profile()
    try:
        run('CREATE (:Person {name: "Linh", city: "Hue"})')
    except Exception as e:
        print("tao them mot Linh nua ->", type(e).__name__)


if __name__ == "__main__":
    try:
        load_store()
        bai1()
        bai2()
        bai3()
        bai4()
        bai5()
    finally:
        driver.close()
