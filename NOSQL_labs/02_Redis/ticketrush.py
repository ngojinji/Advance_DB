import random
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import redis

sys.stdout.reconfigure(encoding="utf-8")

r = redis.Redis(host="localhost", port=6379, decode_responses=True)


def race(fn, n=50):
    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(fn, range(n)))


# Buoc 1
def hold_naive(event, seat, user):
    key = f"hold:{event}:{seat}"
    if r.get(key) is None:
        time.sleep(0.01)
        r.set(key, user, ex=300)
        return True
    return False


def hold_nx(event, seat, user, ttl=300):
    return bool(r.set(f"hold:{event}:{seat}", user, nx=True, ex=ttl))


# Buoc 2
HOLD = r.register_script("""
if redis.call('SISMEMBER', KEYS[2], ARGV[2]) == 1 then return 0 end
if redis.call('SET', KEYS[1], ARGV[1], 'NX', 'EX', ARGV[3]) then return 1 end
return 0
""")

CONFIRM = r.register_script("""
if redis.call('GET', KEYS[1]) == ARGV[1] then
  redis.call('SADD', KEYS[2], ARGV[2])
  redis.call('DEL', KEYS[1])
  return 1
end
return 0
""")

RELEASE = r.register_script("""
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
end
return 0
""")


def hold(event, seat, user, ttl=300):
    return bool(HOLD(keys=[f"hold:{event}:{seat}", f"sold:{event}"], args=[user, seat, ttl]))


def confirm(event, seat, user):
    return bool(CONFIRM(keys=[f"hold:{event}:{seat}", f"sold:{event}"], args=[user, seat]))


def release(event, seat, user):
    return bool(RELEASE(keys=[f"hold:{event}:{seat}"], args=[user]))


def seat_map(event, seats):
    sold = r.smembers(f"sold:{event}")
    return {s: "sold" if s in sold else "held" if r.exists(f"hold:{event}:{s}") else "free"
            for s in seats}


# Buoc 3
def buy_general(event, user):
    left = r.decr(f"stock:{event}")
    if left < 0:
        r.incr(f"stock:{event}")
        return False
    r.sadd(f"buyers:{event}", user)
    return True


def buy_general_broken(event, user):
    if int(r.get(f"stock:{event}")) > 0:
        time.sleep(0.001)
        r.decr(f"stock:{event}")
        r.sadd(f"buyers:{event}", user)
        return True
    return False


# Buoc 4
def allow_fixed(user, limit=5, window=10):
    key = f"rl:fixed:{user}:{int(time.time() // window)}"
    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, window, nx=True)
    count, _ = pipe.execute()
    return count <= limit


SLIDING = r.register_script("""
local now, window, limit = tonumber(ARGV[1]), tonumber(ARGV[2]), tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, now - window)
if redis.call('ZCARD', KEYS[1]) < limit then
  redis.call('ZADD', KEYS[1], now, ARGV[4])
  redis.call('PEXPIRE', KEYS[1], window)
  return 1
end
return 0
""")


def allow_sliding(user, limit=5, window_ms=10_000):
    now = int(time.time() * 1000)
    return bool(SLIDING(keys=[f"rl:sliding:{user}"], args=[now, window_ms, limit, uuid.uuid4().hex]))


def try_hold(event, seat, user):
    if not allow_sliding(user):
        return "rate_limited"
    return "ok" if hold(event, seat, user) else "taken"


# Buoc 5
def join_queue(event, user):
    r.zadd(f"queue:{event}", {user: time.time()}, nx=True)
    return r.zrank(f"queue:{event}", user) + 1


def admit(event, n):
    return [user for user, _ in r.zpopmin(f"queue:{event}", n)]


# Buoc 6
SEATS = [f"S{i}" for i in range(1, 21)]


def buyer(i):
    user = f"user{i}"
    for seat in SEATS:
        if hold("c1", seat, user):
            time.sleep(random.random() * 0.05)
            if confirm("c1", seat, user):
                return seat
    return None


def wait_until_before_boundary(window=10, before=0.2):
    time.sleep((window - time.time() % window - before) % window)


def step1():
    print("=== Buoc 1 ===")
    for k in range(5):
        r.flushdb()
        wins = race(lambda i: hold_naive("c1", "A1", f"user{i}"))
        print(f"naive lan {k + 1}: winners = {sum(wins)}")
    for k in range(5):
        r.flushdb()
        wins = race(lambda i: hold_nx("c1", "A1", f"user{i}"))
        print(f"SET NX lan {k + 1}: winners = {sum(wins)}")
    print("TTL hold:c1:A1 =", r.ttl("hold:c1:A1"))
    time.sleep(2)
    print("TTL sau 2s     =", r.ttl("hold:c1:A1"))
    r.flushdb()
    hold_nx("c1", "A1", "linh", ttl=2)
    print("giu A1 voi TTL 2s, ton tai:", bool(r.exists("hold:c1:A1")))
    time.sleep(2.5)
    print("sau 2.5s, ton tai:", bool(r.exists("hold:c1:A1")))


def step2():
    print("\n=== Buoc 2 ===")
    r.flushdb()
    print(hold("c1", "A1", "linh"))
    print(hold("c1", "A1", "nam"))
    print(confirm("c1", "A1", "nam"))
    print(confirm("c1", "A1", "linh"))
    print(hold("c1", "A1", "nam"))
    print(seat_map("c1", ["A1", "A2"]))
    print(hold("c1", "A2", "mai"), release("c1", "A2", "nam"), release("c1", "A2", "mai"))
    print(seat_map("c1", ["A1", "A2"]))
    print("SMEMBERS sold:c1 =", r.smembers("sold:c1"))


def step3():
    print("\n=== Buoc 3 ===")
    for k in range(3):
        r.flushdb()
        r.set("stock:g1", 100)
        ok = race(lambda i: buy_general("g1", f"user{i}"), n=500)
        print(f"DECR lan {k + 1}: sold={sum(ok)} stock={r.get('stock:g1')} buyers={r.scard('buyers:g1')}")
    for k in range(3):
        r.flushdb()
        r.set("stock:g1", 100)
        ok = race(lambda i: buy_general_broken("g1", f"user{i}"), n=500)
        print(f"GET roi DECR lan {k + 1}: sold={sum(ok)} stock={r.get('stock:g1')} buyers={r.scard('buyers:g1')}")


def step4():
    print("\n=== Buoc 4 ===")
    r.flushdb()
    print("fixed 8 request:", [allow_fixed("linh") for _ in range(8)])
    wait_until_before_boundary()
    first = [allow_fixed("bot") for _ in range(5)]
    time.sleep(0.4)
    second = [allow_fixed("bot") for _ in range(5)]
    print("fixed o ranh gioi:  ", first + second, "->", sum(first + second), "request duoc qua")

    r.flushdb()
    print("sliding 8 request:", [allow_sliding("linh") for _ in range(8)])
    wait_until_before_boundary()
    first = [allow_sliding("bot") for _ in range(5)]
    time.sleep(0.4)
    second = [allow_sliding("bot") for _ in range(5)]
    print("sliding o ranh gioi:", first + second, "->", sum(first + second), "request duoc qua")

    r.flushdb()
    print("try_hold 7 lan:", [try_hold("c1", "B1", "bot2") for _ in range(7)])


def step5():
    print("\n=== Buoc 5 ===")
    r.flushdb()
    for name in ["u1", "u2", "u3"]:
        print(name, join_queue("c1", name))
    print(join_queue("c1", "u1"))
    print(admit("c1", 2))
    print(join_queue("c1", "u3"))


def step6(runs=10):
    print("\n=== Buoc 6 ===")
    for k in range(runs):
        r.flushdb()
        got = [s for s in race(buyer, n=100) if s]
        print(f"lan {k + 1}: {len(got)} {len(set(got))} {r.scard('sold:c1')}")


if __name__ == "__main__":
    step1()
    step2()
    step3()
    step4()
    step5()
    step6()
