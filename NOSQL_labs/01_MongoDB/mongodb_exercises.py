import random
import sys

from pymongo import MongoClient

sys.stdout.reconfigure(encoding="utf-8")

client = MongoClient("mongodb://localhost:27017")
db = client.shop

base_orders = [
    {"_id": 1001, "customer": {"name": "Linh", "city": "Hanoi"}, "status": "paid",
     "items": [{"sku": "BK-01", "title": "Python Basics", "qty": 2, "price": 12.5},
               {"sku": "BK-07", "title": "SQL in Practice", "qty": 1, "price": 18.0}],
     "tags": ["student", "first-order"]},
    {"_id": 1002, "customer": {"name": "Nam", "city": "Da Nang"}, "status": "shipped",
     "items": [{"sku": "BK-03", "title": "Data Viz", "qty": 1, "price": 22.0}]},
    {"_id": 1003, "customer": {"name": "Mai", "city": "Hanoi"}, "status": "paid",
     "items": [{"sku": "BK-01", "title": "Python Basics", "qty": 1, "price": 12.5}],
     "coupon": "WELCOME10"},
]

new_orders = [
    {"_id": 1004, "customer": {"name": "Hung", "city": "Hue"}, "status": "paid",
     "items": [{"sku": "BK-01", "title": "Python Basics", "qty": 1, "price": 12.5}],
     "shipping": {"address": {"street": "12 Le Loi", "district": "Phu Hoi"},
                  "method": "express", "fee": 2.0},
     "note": "Giao giờ hành chính"},
    {"_id": 1005, "customer": {"name": "Lan", "city": "Ho Chi Minh"}, "status": "paid",
     "items": [{"sku": "EB-02", "title": "NoSQL Distilled (ebook)", "qty": 1, "price": 9.9,
                "format": "pdf", "download_limit": 3}],
     "payments": [{"method": "card", "amount": 5.0}, {"method": "wallet", "amount": 4.9}]},
    {"_id": 1006, "customer": {"name": "Tuan", "city": "Da Nang",
                               "email": "tuan@example.com", "phone": "0901234567"},
     "status": "shipped",
     "items": [{"sku": "BK-07", "title": "SQL in Practice", "qty": 2, "price": 18.0},
               {"sku": "BK-03", "title": "Data Viz", "qty": 1, "price": 22.0}],
     "tags": ["gift"], "rating": {"stars": 5, "comment": "Sách đẹp"}},
    {"_id": 1007, "customer": {"name": "Ha", "city": "Hanoi"}, "status": "cancelled",
     "cancel": {"reason": "Đặt nhầm", "at": "2026-11-15"}},
    {"_id": 1008, "customer": {"name": "Cong ty ABC", "city": "Hanoi", "type": "business",
                               "tax_id": "0101234567"},
     "status": "paid",
     "items": [{"sku": "BK-01", "title": "Python Basics", "qty": 20, "price": 12.5,
                "discount_pct": 10},
               {"sku": "CB-01", "title": "Combo Data", "qty": 5, "price": 35.0,
                "bundle": ["BK-03", "BK-07"]}],
     "invoice_required": True},
]


def find_by_sku(sku):
    return list(db.orders.find({"items.sku": sku},
                               {"customer.name": 1, "status": 1, "items.sku": 1}).sort("_id", 1))


def bai1():
    print("--- Bai 1 ---")
    db.orders.drop()
    db.orders.insert_many(base_orders)
    db.orders.insert_many(new_orders)
    print("So don:", db.orders.count_documents({}))
    for o in new_orders:
        print(o["_id"], sorted(o.keys()))
    for sku in ["BK-01", "BK-03"]:
        print(f"\nfind items.sku = {sku}")
        for d in find_by_sku(sku):
            print(d)


def bai2():
    print("\n--- Bai 2 ---")
    pipeline = [
        {"$match": {"status": {"$in": ["paid", "shipped"]}}},
        {"$unwind": "$items"},
        {"$group": {
            "_id": "$customer.city",
            "orders": {"$addToSet": "$_id"},
            "revenue": {"$sum": {"$multiply": [
                "$items.qty", "$items.price",
                {"$subtract": [1, {"$divide": [{"$ifNull": ["$items.discount_pct", 0]}, 100]}]},
            ]}},
        }},
        {"$project": {"_id": 0, "city": "$_id", "num_orders": {"$size": "$orders"},
                      "revenue": {"$round": ["$revenue", 2]}}},
        {"$sort": {"revenue": -1}},
    ]
    for row in db.orders.aggregate(pipeline):
        print(row)


cities = ["Hanoi", "Ho Chi Minh", "Da Nang", "Hue", "Can Tho", "Hai Phong",
          "Nha Trang", "Vinh", "Quy Nhon", "Da Lat"]
statuses = ["paid", "shipped", "cancelled", "pending"]
skus = [("BK-01", "Python Basics", 12.5), ("BK-03", "Data Viz", 22.0),
        ("BK-07", "SQL in Practice", 18.0), ("EB-02", "NoSQL Distilled", 9.9)]
names = ["Linh", "Nam", "Mai", "Hung", "Lan", "Tuan", "Ha", "Minh", "Trang", "Duc"]


def random_order(i):
    items = [{"sku": s, "title": t, "qty": random.randint(1, 5), "price": p}
             for s, t, p in random.sample(skus, random.randint(1, 3))]
    return {"_id": i, "customer": {"name": random.choice(names), "city": random.choice(cities)},
            "status": random.choice(statuses), "items": items}


def show_explain(plan):
    node = plan["queryPlanner"]["winningPlan"]
    node = node.get("queryPlan", node)
    stages = []
    while node:
        stages.append(node["stage"])
        node = node.get("inputStage")
    s = plan["executionStats"]
    print("stage:", " <- ".join(stages))
    print("nReturned:", s["nReturned"])
    print("totalKeysExamined:", s["totalKeysExamined"])
    print("totalDocsExamined:", s["totalDocsExamined"])
    print("executionTimeMillis:", s["executionTimeMillis"])


def bai3():
    print("\n--- Bai 3 ---")
    random.seed(42)
    big = db.orders_big
    big.drop()
    big.insert_many([random_order(i) for i in range(1, 10001)])
    print("So document:", big.count_documents({}))

    query = {"customer.city": "Hanoi", "status": "paid"}
    print("\nTruoc khi tao index:")
    show_explain(big.find(query).explain())

    big.create_index([("customer.city", 1), ("status", 1)])
    print("\nSau khi tao index:")
    show_explain(big.find(query).explain())


if __name__ == "__main__":
    bai1()
    bai2()
    bai3()
