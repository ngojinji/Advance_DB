import random
import sys
from datetime import datetime, timedelta

from cassandra.cluster import Cluster, ExecutionProfile, EXEC_PROFILE_DEFAULT
from cassandra.policies import WhiteListRoundRobinPolicy

sys.stdout.reconfigure(encoding="utf-8")

profile = ExecutionProfile(load_balancing_policy=WhiteListRoundRobinPolicy(["127.0.0.1"]))
cluster = Cluster(["127.0.0.1"], execution_profiles={EXEC_PROFILE_DEFAULT: profile})
session = cluster.connect()

session.execute("""
    CREATE KEYSPACE IF NOT EXISTS shop
    WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 3}""")
session.set_keyspace("shop")


def bai1():
    print("--- Bai 1 ---")
    session.execute("DROP TABLE IF EXISTS orders_by_customer")
    session.execute("DROP TABLE IF EXISTS orders_by_day")
    session.execute("""
        CREATE TABLE orders_by_customer (
            customer_id text,
            order_ts    timestamp,
            order_id    int,
            city        text,
            status      text,
            total       double,
            PRIMARY KEY ((customer_id), order_ts, order_id)
        ) WITH CLUSTERING ORDER BY (order_ts DESC, order_id ASC)""")
    session.execute("""
        CREATE TABLE orders_by_day (
            day         date,
            order_ts    timestamp,
            order_id    int,
            customer_id text,
            status      text,
            total       double,
            PRIMARY KEY ((day), order_ts, order_id)
        ) WITH CLUSTERING ORDER BY (order_ts ASC, order_id ASC)""")

    ins_c = session.prepare("INSERT INTO orders_by_customer (customer_id, order_ts, order_id, city, status, total) "
                            "VALUES (?, ?, ?, ?, ?, ?)")
    ins_d = session.prepare("INSERT INTO orders_by_day (day, order_ts, order_id, customer_id, status, total) "
                            "VALUES (?, ?, ?, ?, ?, ?)")

    random.seed(1)
    customers = {"linh": "Hanoi", "nam": "Da Nang", "mai": "Hanoi"}
    start = datetime(2026, 11, 1, 8, 0)
    order_id = 1000
    for _ in range(40):
        order_id += 1
        cust = random.choice(list(customers))
        ts = start + timedelta(hours=random.randint(0, 24 * 10))
        status = random.choice(["paid", "shipped", "cancelled"])
        total = round(random.uniform(10, 200), 2)
        session.execute(ins_c, (cust, ts, order_id, customers[cust], status, total))
        session.execute(ins_d, (ts.date(), ts, order_id, cust, status, total))
    print("da ghi 40 don vao ca 2 bang")

    print("\n10 don moi nhat cua linh:")
    rows = session.execute("SELECT order_ts, order_id, status, total FROM orders_by_customer "
                           "WHERE customer_id = 'linh' LIMIT 10")
    for row in rows:
        print(row.order_ts, row.order_id, row.status, row.total)

    print("\nDon trong ngay 2026-11-03:")
    rows = session.execute("SELECT order_ts, order_id, customer_id, total FROM orders_by_day "
                           "WHERE day = '2026-11-03'")
    for row in rows:
        print(row.order_ts, row.order_id, row.customer_id, row.total)


def bai2():
    print("\n--- Bai 2 ---")
    session.execute("DROP TABLE IF EXISTS readings_by_sensor")
    session.execute("""
        CREATE TABLE readings_by_sensor (
            sensor_id   text,
            ts          timestamp,
            temperature double,
            humidity    double,
            PRIMARY KEY ((sensor_id), ts)
        ) WITH CLUSTERING ORDER BY (ts DESC)""")
    ins = session.prepare("INSERT INTO readings_by_sensor (sensor_id, ts, temperature, humidity) VALUES (?, ?, ?, ?)")
    random.seed(2)
    start = datetime(2026, 11, 10, 0, 0)
    for sensor in ["dn-01", "dn-02", "hue-01"]:
        for i in range(20):
            session.execute(ins, (sensor, start + timedelta(minutes=10 * i),
                                  round(random.uniform(20, 34), 1), round(random.uniform(50, 90), 1)))
    print("da ghi 60 so do cho dn-01, dn-02, hue-01")

    rows = session.execute("SELECT ts, temperature FROM readings_by_sensor WHERE sensor_id = 'dn-01' LIMIT 3")
    print("\ntheo partition key (dn-01, 3 so do moi nhat):")
    for row in rows:
        print(row.ts, row.temperature)

    for q in ["SELECT * FROM readings_by_sensor WHERE temperature > 30",
              "SELECT * FROM readings_by_sensor WHERE ts > '2026-11-10 02:00:00'"]:
        print(f"\n{q}")
        try:
            session.execute(q)
            print("chay duoc")
        except Exception as e:
            print(f"{type(e).__name__}: {e}")


def bai3():
    print("\n--- Bai 3 ---")
    session.execute("DROP TABLE IF EXISTS readings_by_sensor_month")
    session.execute("""
        CREATE TABLE readings_by_sensor_month (
            sensor_id   text,
            month       text,
            ts          timestamp,
            temperature double,
            humidity    double,
            PRIMARY KEY ((sensor_id, month), ts)
        ) WITH CLUSTERING ORDER BY (ts DESC)""")
    ins = session.prepare("INSERT INTO readings_by_sensor_month (sensor_id, month, ts, temperature, humidity) "
                          "VALUES (?, ?, ?, ?, ?)")
    random.seed(3)
    start = datetime(2026, 9, 1)
    n = 0
    ts = start
    while ts < datetime(2026, 12, 1):
        session.execute(ins, ("dn-01", ts.strftime("%Y-%m"), ts,
                              round(random.uniform(20, 34), 1), round(random.uniform(50, 90), 1)))
        ts += timedelta(hours=6)
        n += 1
    print(f"da ghi {n} so do cho dn-01 tu 2026-09 den 2026-11")

    for month in ["2026-09", "2026-10", "2026-11"]:
        c = session.execute("SELECT count(*) FROM readings_by_sensor_month "
                            "WHERE sensor_id = 'dn-01' AND month = %s", (month,)).one()[0]
        print(f"partition (dn-01, {month}): {c} hang")

    rows = session.execute("SELECT ts, temperature FROM readings_by_sensor_month "
                           "WHERE sensor_id = 'dn-01' AND month = '2026-11' LIMIT 3")
    print("\n3 so do moi nhat thang 11:")
    for row in rows:
        print(row.ts, row.temperature)

    rows = session.execute("SELECT ts, temperature FROM readings_by_sensor_month "
                           "WHERE sensor_id = 'dn-01' AND month IN ('2026-10', '2026-11') "
                           "AND ts >= '2026-10-31 00:00:00' AND ts < '2026-11-01 12:00:00'")
    print("\nkhoang 2026-10-31 -> 2026-11-01 12h (qua 2 partition):")
    for row in rows:
        print(row.ts, row.temperature)

    print("\nthieu month:")
    try:
        session.execute("SELECT * FROM readings_by_sensor_month WHERE sensor_id = 'dn-01'")
        print("chay duoc")
    except Exception as e:
        print(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    bai1()
    bai2()
    bai3()
    cluster.shutdown()
