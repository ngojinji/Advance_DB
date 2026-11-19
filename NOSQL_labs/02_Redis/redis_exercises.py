import json
import sys
import time

import redis

sys.stdout.reconfigure(encoding="utf-8")

r = redis.Redis(host="localhost", port=6379, decode_responses=True)


def bai1():
    print("--- Bai 1 ---")
    r.delete("board")
    r.zadd("board", {"linh": 1200, "nam": 950, "mai": 1430, "hung": 1100, "lan": 870, "tuan": 1300})
    r.zincrby("board", 250, "nam")
    top = r.zrevrange("board", 0, 2, withscores=True)
    for rank, (player, score) in enumerate(top, start=1):
        print(rank, player, int(score))
    print("thu hang cua nam:", r.zrevrank("board", "nam") + 1)


users = [
    (1, "Linh", "Hanoi", 21), (2, "Nam", "Da Nang", 22), (3, "Mai", "Hanoi", 20),
    (4, "Hung", "Hue", 23), (5, "Lan", "Ho Chi Minh", 21), (6, "Tuan", "Hanoi", 24),
]


def bai2():
    print("\n--- Bai 2 ---")
    for key in r.scan_iter("user:*"):
        r.delete(key)
    for key in r.scan_iter("city:*"):
        r.delete(key)

    for uid, name, city, age in users:
        r.hset(f"user:{uid}", mapping={"name": name, "city": city, "age": age})
        r.sadd(f"city:{city}", uid)

    print("HGETALL user:1 ->", r.hgetall("user:1"))

    def users_in(city):
        return [r.hgetall(f"user:{uid}") for uid in sorted(r.smembers(f"city:{city}"))]

    for city in ["Hanoi", "Da Nang"]:
        print(city, "->", users_in(city))

    old = r.hget("user:5", "city")
    r.hset("user:5", "city", "Hanoi")
    r.smove(f"city:{old}", "city:Hanoi", 5)
    print("sau khi Lan chuyen ra Hanoi:", [u["name"] for u in users_in("Hanoi")])


def slow_query(product_id):
    time.sleep(1)
    return {"id": product_id, "title": "Python Basics", "price": 12.5}


def get_product(product_id):
    key = f"product:{product_id}"
    cached = r.get(key)
    if cached is not None:
        return json.loads(cached)
    product = slow_query(product_id)
    r.set(key, json.dumps(product), ex=300)
    return product


def bai3(n=100):
    print("\n--- Bai 3 ---")
    r.delete("product:7")

    start = time.perf_counter()
    for _ in range(n):
        slow_query(7)
    no_cache = time.perf_counter() - start

    times = []
    for _ in range(n):
        t = time.perf_counter()
        get_product(7)
        times.append(time.perf_counter() - t)
    with_cache = sum(times)

    print(f"khong cache: {no_cache:.2f} s")
    print(f"co cache   : {with_cache:.3f} s  (lan dau {times[0] * 1000:.1f} ms, "
          f"99 lan sau trung binh {sum(times[1:]) / (n - 1) * 1000:.3f} ms)")
    print(f"nhanh hon  : {no_cache / with_cache:.1f} lan")


if __name__ == "__main__":
    bai1()
    bai2()
    bai3()
