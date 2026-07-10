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


def network_name_from_provider_id(provider_id):
    for name, pid in PROVIDERS["networks"].items():
        if pid == int(provider_id):
            return name
    return None


def resolve_disco_id(name):
    return PROVIDERS["electricity"].get(name.upper())


def disco_name_from_id(disco_id):
    for name, did in PROVIDERS["electricity"].items():
        if did == int(disco_id):
            return name
    return None


def resolve_cable_id(name):
    return PROVIDERS["cable"].get(name.upper())


TRANSACTION_TYPE_MAP = {
    "DATA": "DATA",
    "AIRTIME": "AIRTIME",
    "CABLE": "UTILITY",
    "ELECTRICITY": "UTILITY",
}
