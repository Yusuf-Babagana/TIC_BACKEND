PROVIDERS = {
    "networks": {
        "MTN": 1,
        "GLO": 2,
        "AIRTEL": 3,
        "9MOBILE": 4,
    },
    "electricity": {
        "AEDC": 1,
        "EKEDC": 2,
        "IBEDC": 3,
        "IKEDC": 4,
        "KADUNA": 5,
        "PHED": 6,
        "JED": 7,
        "EEDC": 8,
        "YOLA": 9,
        "BENIN": 10,
    },
    "cable": {
        "GOTV": 1,
        "DSTV": 2,
        "STARTIMES": 3,
    },
}


def resolve_network_id(name):
    return PROVIDERS["networks"].get(name.upper())


def resolve_disco_id(name):
    return PROVIDERS["electricity"].get(name.upper())


def resolve_cable_id(name):
    return PROVIDERS["cable"].get(name.upper())


TRANSACTION_TYPE_MAP = {
    "DATA": "DATA",
    "AIRTIME": "AIRTIME",
    "CABLE": "UTILITY",
    "ELECTRICITY": "UTILITY",
}
