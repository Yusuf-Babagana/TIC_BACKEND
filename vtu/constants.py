DATA_PLANS = [
    {"id": 70, "provider": "airtel", "name": "1GB (Social Bundle) - 3 Days", "price": 295.00},
    {"id": 13, "provider": "airtel", "name": "500MB - 7 Days", "price": 490.00},
    {"id": 71, "provider": "airtel", "name": "1GB - 7 Days", "price": 530.00},
    {"id": 72, "provider": "airtel", "name": "2GB - 7 Days", "price": 930.00},
    {"id": 73, "provider": "airtel", "name": "3GB - 30 Days", "price": 1200.00},
    {"id": 74, "provider": "airtel", "name": "5GB - 30 Days", "price": 1900.00},
    {"id": 75, "provider": "airtel", "name": "10GB - 30 Days", "price": 3500.00},
    {"id": 43, "provider": "mtn", "name": "110MB - 1 Day", "price": 99.00},
    {"id": 46, "provider": "mtn", "name": "1GB SME - 30 Days", "price": 570.00},
    {"id": 51, "provider": "mtn", "name": "75GB - 30 Days", "price": 17990.00},
    {"id": 47, "provider": "mtn", "name": "500MB SME - 30 Days", "price": 340.00},
    {"id": 48, "provider": "mtn", "name": "2GB SME - 30 Days", "price": 1000.00},
    {"id": 49, "provider": "mtn", "name": "3GB SME - 30 Days", "price": 1450.00},
    {"id": 50, "provider": "mtn", "name": "5GB SME - 30 Days", "price": 2200.00},
    {"id": 52, "provider": "mtn", "name": "10GB SME - 30 Days", "price": 3500.00},
    {"id": 36, "provider": "glo", "name": "1GB Corporate Gifting - 30 Days", "price": 425.00},
    {"id": 37, "provider": "glo", "name": "500MB - 30 Days", "price": 280.00},
    {"id": 38, "provider": "glo", "name": "2GB - 30 Days", "price": 920.00},
    {"id": 39, "provider": "glo", "name": "5GB - 30 Days", "price": 2100.00},
    {"id": 40, "provider": "glo", "name": "10GB - 30 Days", "price": 3800.00},
    {"id": 41, "provider": "glo", "name": "15GB - 30 Days", "price": 5400.00},
    {"id": 42, "provider": "9mobile", "name": "500MB - 30 Days", "price": 320.00},
    {"id": 43, "provider": "9mobile", "name": "1GB - 30 Days", "price": 530.00},
    {"id": 44, "provider": "9mobile", "name": "2GB - 30 Days", "price": 1020.00},
    {"id": 45, "provider": "9mobile", "name": "5GB - 30 Days", "price": 2350.00},
]

CABLE_PLANS = [
    {"id": 3, "provider": "DSTV", "name": "DStv Padi", "price": 4400.00},
    {"id": 5, "provider": "DSTV", "name": "DStv Yanga", "price": 6300.00},
    {"id": 6, "provider": "DSTV", "name": "DStv Confam", "price": 9300.00},
    {"id": 7, "provider": "DSTV", "name": "DStv Compact", "price": 12000.00},
    {"id": 8, "provider": "DSTV", "name": "DStv Compact Plus", "price": 18000.00},
    {"id": 9, "provider": "DSTV", "name": "DStv Premium", "price": 24000.00},
    {"id": 4, "provider": "GOTV", "name": "GOtv Smallie-monthly", "price": 1900.00},
    {"id": 13, "provider": "GOTV", "name": "GOtv Max", "price": 8500.00},
    {"id": 10, "provider": "GOTV", "name": "GOtv Lite", "price": 1200.00},
    {"id": 11, "provider": "GOTV", "name": "GOtv Value", "price": 2500.00},
    {"id": 12, "provider": "GOTV", "name": "GOtv Plus", "price": 3800.00},
    {"id": 14, "provider": "GOTV", "name": "GOtv Supa", "price": 6500.00},
    {"id": 15, "provider": "STARTIMES", "name": "StarTimes Basic", "price": 1500.00},
    {"id": 16, "provider": "STARTIMES", "name": "StarTimes Classic", "price": 3000.00},
    {"id": 17, "provider": "STARTIMES", "name": "StarTimes Premium", "price": 5000.00},
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
