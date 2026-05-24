NETWORKS = [
    {"id": 1, "name": "mtn"},
    {"id": 2, "name": "glo"},
    {"id": 3, "name": "airtel"},
    {"id": 4, "name": "9mobile"},
]

DATA_PLANS = [
    {"id": 1, "provider": "mtn", "name": "500MB (30 Days)", "price": 350.00},
    {"id": 46, "provider": "mtn", "name": "1GB (30 Days)", "price": 570.00},
    {"id": 2, "provider": "mtn", "name": "2GB (30 Days)", "price": 1100.00},
    {"id": 3, "provider": "mtn", "name": "5GB (30 Days)", "price": 2500.00},
    {"id": 4, "provider": "mtn", "name": "10GB (30 Days)", "price": 4500.00},
    {"id": 5, "provider": "glo", "name": "500MB (30 Days)", "price": 300.00},
    {"id": 6, "provider": "glo", "name": "1GB (30 Days)", "price": 500.00},
    {"id": 7, "provider": "glo", "name": "2GB (30 Days)", "price": 1000.00},
    {"id": 8, "provider": "glo", "name": "5GB (30 Days)", "price": 2300.00},
    {"id": 9, "provider": "glo", "name": "10GB (30 Days)", "price": 4000.00},
    {"id": 10, "provider": "airtel", "name": "500MB (30 Days)", "price": 330.00},
    {"id": 11, "provider": "airtel", "name": "1GB (30 Days)", "price": 550.00},
    {"id": 12, "provider": "airtel", "name": "2GB (30 Days)", "price": 1050.00},
    {"id": 13, "provider": "airtel", "name": "5GB (30 Days)", "price": 2400.00},
    {"id": 14, "provider": "airtel", "name": "10GB (30 Days)", "price": 4300.00},
    {"id": 15, "provider": "9mobile", "name": "500MB (30 Days)", "price": 320.00},
    {"id": 16, "provider": "9mobile", "name": "1GB (30 Days)", "price": 530.00},
    {"id": 17, "provider": "9mobile", "name": "2GB (30 Days)", "price": 1020.00},
    {"id": 18, "provider": "9mobile", "name": "5GB (30 Days)", "price": 2350.00},
]

CABLE_PLANS = [
    {"id": 1, "provider": "gotv", "name": "GOtv Lite", "price": 1200.00},
    {"id": 2, "provider": "gotv", "name": "GOtv Value", "price": 2500.00},
    {"id": 3, "provider": "gotv", "name": "GOtv Plus", "price": 3800.00},
    {"id": 4, "provider": "gotv", "name": "GOtv Max", "price": 5200.00},
    {"id": 5, "provider": "gotv", "name": "GOtv Supa", "price": 6500.00},
    {"id": 6, "provider": "dstv", "name": "DStv Padi", "price": 4400.00},
    {"id": 7, "provider": "dstv", "name": "DStv Yanga", "price": 6300.00},
    {"id": 8, "provider": "dstv", "name": "DStv Confam", "price": 9300.00},
    {"id": 9, "provider": "dstv", "name": "DStv Compact", "price": 12000.00},
    {"id": 10, "provider": "dstv", "name": "DStv Compact Plus", "price": 18000.00},
    {"id": 11, "provider": "dstv", "name": "DStv Premium", "price": 24000.00},
    {"id": 12, "provider": "startimes", "name": "StarTimes Basic", "price": 1500.00},
    {"id": 13, "provider": "startimes", "name": "StarTimes Classic", "price": 3000.00},
    {"id": 14, "provider": "startimes", "name": "StarTimes Premium", "price": 5000.00},
]


def get_data_plan(plan_id):
    for p in DATA_PLANS:
        if p["id"] == plan_id:
            return p
    return None


def get_cable_plan(plan_id):
    for p in CABLE_PLANS:
        if p["id"] == plan_id:
            return p
    return None
