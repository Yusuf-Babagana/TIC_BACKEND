# Nellobytes (nellobytesystems.com) data-bundle plan catalog.
# `id` is kept as the exact string Nellobytes uses for its `DataPlan` param —
# IDs are NOT unique across networks (e.g. MTN "500.01" != Glo "500.01"),
# so every lookup must be scoped by (network, id), never `id` alone.
#
# NOTE: Nellobytes' "Available Mobile Networks" table only documents codes for
# MTN/Glo/t2mobile/Airtel (01-04). No network code was given for 9mobile even
# though a 9mobile plan list was provided — those plans are kept here for
# display, but NellobytesService.NETWORK_CODES has no "9MOBILE" entry, so a
# 9mobile purchase attempt will fail cleanly until Nellobytes provides that code.
DATA_PLANS = [
    # MTN
    {"id": "500", "provider": "mtn", "name": "500 MB - Weekly (SME)", "price": 307.00},
    {"id": "500.00", "provider": "mtn", "name": "500 MB - Monthly (SME)", "price": 307.00},
    {"id": "1000", "provider": "mtn", "name": "1 GB - Weekly (SME)", "price": 410.00},
    {"id": "1000.00", "provider": "mtn", "name": "1 GB - Monthly (SME)", "price": 563.00},
    {"id": "2000", "provider": "mtn", "name": "2 GB - Weekly (SME)", "price": 820.00},
    {"id": "2000.00", "provider": "mtn", "name": "2 GB - Monthly (SME)", "price": 1117.00},
    {"id": "3000", "provider": "mtn", "name": "3 GB - Weekly (SME)", "price": 1230.00},
    {"id": "3000.00", "provider": "mtn", "name": "3 GB - Monthly (SME)", "price": 1629.00},
    {"id": "5000", "provider": "mtn", "name": "5 GB - Weekly (SME)", "price": 2050.00},
    {"id": "5000.00", "provider": "mtn", "name": "5 GB - Monthly (SME)", "price": 2511.00},
    {"id": "100.01", "provider": "mtn", "name": "110MB Daily Plan - 1 day (Awoof Data)", "price": 97.00},
    {"id": "200.01", "provider": "mtn", "name": "230MB Daily Plan - 1 day (Awoof Data)", "price": 194.00},
    {"id": "350.01", "provider": "mtn", "name": "500MB Daily Plan - 1 day (Awoof Data)", "price": 339.50},
    {"id": "500.01", "provider": "mtn", "name": "1GB Daily Plan + 1.5mins. - 1 day (Awoof Data)", "price": 485.00},
    {"id": "750.01", "provider": "mtn", "name": "2.5GB Daily Plan - 1 day (Awoof Data)", "price": 727.50},
    {"id": "900.01", "provider": "mtn", "name": "2.5GB 2-Day Plan - 2 days (Awoof Data)", "price": 873.00},
    {"id": "1000.01", "provider": "mtn", "name": "3.2GB 2-Day Plan - 2 days (Awoof Data)", "price": 970.00},
    {"id": "500.02", "provider": "mtn", "name": "500MB Weekly Plan - 7 days (Direct Data)", "price": 485.00},
    {"id": "800.01", "provider": "mtn", "name": "1GB Weekly Plan - 7 days (Direct Data)", "price": 776.00},
    {"id": "1000.03", "provider": "mtn", "name": "1.5GB Weekly Plan - 7 days (Direct Data)", "price": 970.00},
    {"id": "1500.03", "provider": "mtn", "name": "3.5GB Weekly Plan - 7 days (Direct Data)", "price": 1455.00},
    {"id": "2500.01", "provider": "mtn", "name": "6GB Weekly Plan - 7 days (Direct Data)", "price": 2425.00},
    {"id": "3500.01", "provider": "mtn", "name": "11GB Weekly Bundle - 7 days (Direct Data)", "price": 3395.00},
    {"id": "1500.02", "provider": "mtn", "name": "2GB+2mins Monthly Plan - 30 days (Direct Data)", "price": 1455.00},
    {"id": "2000.01", "provider": "mtn", "name": "2.7GB+2mins Monthly Plan - 30 days (Direct Data)", "price": 1940.00},
    {"id": "2500.02", "provider": "mtn", "name": "3.5GB+5mins Monthly Plan - 30 days (Direct Data)", "price": 2425.00},
    {"id": "3500.02", "provider": "mtn", "name": "7GB Monthly Plan - 30 days (Direct Data)", "price": 3395.00},
    {"id": "4500.01", "provider": "mtn", "name": "10GB+10mins Monthly Plan - 30 days (Direct Data)", "price": 4365.00},
    {"id": "5500.01", "provider": "mtn", "name": "12.5GB Monthly Plan - 30 days (Direct Data)", "price": 5335.00},
    {"id": "6500.01", "provider": "mtn", "name": "16.5GB+10mins Monthly Plan - 30 days (Direct Data)", "price": 6305.00},
    {"id": "7500.01", "provider": "mtn", "name": "20GB Monthly Plan - 30 days (Direct Data)", "price": 7275.00},
    {"id": "9000.01", "provider": "mtn", "name": "25GB Monthly Plan - 30 days (Direct Data)", "price": 8730.00},
    {"id": "11000.01", "provider": "mtn", "name": "36GB Monthly Plan - 30 days (Direct Data)", "price": 10670.00},
    {"id": "18000.01", "provider": "mtn", "name": "75GB Monthly Plan - 30 days (Direct Data)", "price": 17460.00},
    {"id": "35000.01", "provider": "mtn", "name": "165GB Monthly Plan - 30 days (Direct Data)", "price": 33950.00},
    {"id": "40000.01", "provider": "mtn", "name": "150GB 2-Month Plan - 60 days (Direct Data)", "price": 38800.00},
    {"id": "5000.01", "provider": "mtn", "name": "20GB Weekly Plan - 7 days (Direct Data)", "price": 4850.00},
    {"id": "90000.03", "provider": "mtn", "name": "480GB 3-Month Plan - 90 days (Direct Data)", "price": 87300.00},

    # Glo
    {"id": "200", "provider": "glo", "name": "200 MB - 14 days (SME)", "price": 94.00},
    {"id": "500", "provider": "glo", "name": "500 MB - 7 days (SME)", "price": 230.00},
    {"id": "1000.11", "provider": "glo", "name": "1 GB - 3 days (SME)", "price": 322.00},
    {"id": "3000.11", "provider": "glo", "name": "3 GB - 3 days (SME)", "price": 968.00},
    {"id": "5000.11", "provider": "glo", "name": "5 GB - 3 days (SME)", "price": 1614.00},
    {"id": "1000.12", "provider": "glo", "name": "1 GB - 7 days (SME)", "price": 357.00},
    {"id": "3000.12", "provider": "glo", "name": "3 GB - 7 days (SME)", "price": 1072.00},
    {"id": "5000.12", "provider": "glo", "name": "5 GB - 7 days (SME)", "price": 1787.00},
    {"id": "1000.21", "provider": "glo", "name": "1 GB - 14 days Night Plan (SME)", "price": 357.00},
    {"id": "3000.21", "provider": "glo", "name": "3 GB - 14 days Night Plan (SME)", "price": 1072.00},
    {"id": "5000.21", "provider": "glo", "name": "5 GB - 14 days Night Plan (SME)", "price": 1787.00},
    {"id": "10000.21", "provider": "glo", "name": "10 GB - 14 days Night Plan (SME)", "price": 3574.00},
    {"id": "1000", "provider": "glo", "name": "1 GB - 30 days (SME)", "price": 461.00},
    {"id": "2000", "provider": "glo", "name": "2 GB - 30 days (SME)", "price": 922.00},
    {"id": "3000", "provider": "glo", "name": "3 GB - 30 days (SME)", "price": 1383.00},
    {"id": "5000", "provider": "glo", "name": "5 GB - 30 days (SME)", "price": 2306.00},
    {"id": "10000", "provider": "glo", "name": "10 GB - 30 days (SME)", "price": 4612.00},
    {"id": "100.01", "provider": "glo", "name": "125MB - 1 day (Awoof Data)", "price": 97.00},
    {"id": "200.01", "provider": "glo", "name": "260MB - 2 day (Awoof Data)", "price": 194.00},
    {"id": "500.01", "provider": "glo", "name": "1.5GB - 14 days (Direct Data)", "price": 485.00},
    {"id": "1000.01", "provider": "glo", "name": "2.6GB - 30 days (Direct Data)", "price": 970.00},
    {"id": "1500.01", "provider": "glo", "name": "5GB - 30 days (Direct Data)", "price": 1455.00},
    {"id": "2000.01", "provider": "glo", "name": "6.15GB - 30 days (Direct Data)", "price": 1940.00},
    {"id": "2500.01", "provider": "glo", "name": "7.5GB - 30 days (Direct Data)", "price": 2425.00},
    {"id": "3000.01", "provider": "glo", "name": "10GB - 30 days (Direct Data)", "price": 2910.00},
    {"id": "4000.01", "provider": "glo", "name": "12.5GB - 30 days (Direct Data)", "price": 3880.00},
    {"id": "5000.01", "provider": "glo", "name": "16GB - 30 days (Direct Data)", "price": 4850.00},
    {"id": "8000.01", "provider": "glo", "name": "28GB - 30 days (Direct Data)", "price": 7760.00},
    {"id": "10000.01", "provider": "glo", "name": "38GB - 30 days (Direct Data)", "price": 9700.00},
    {"id": "15000.01", "provider": "glo", "name": "64GB - 30 days (Direct Data)", "price": 14550.00},
    {"id": "20000.01", "provider": "glo", "name": "107GB - 30 days (Direct Data)", "price": 19400.00},
    {"id": "500.02", "provider": "glo", "name": "2GB - 1 day (Awoof Data)", "price": 485.00},
    {"id": "1500.02", "provider": "glo", "name": "6GB - 7 days (Direct Data)", "price": 1455.00},
    {"id": "500.03", "provider": "glo", "name": "2.5GB - Weekend Plan - [Sat & Sun] (Awoof Data)", "price": 485.00},
    {"id": "200.02", "provider": "glo", "name": "875MB - Weekend Plan [Sun] (Awoof Data)", "price": 194.00},
    {"id": "30000.01", "provider": "glo", "name": "165GB - 30 days (Direct Data)", "price": 29100.00},
    {"id": "36000.01", "provider": "glo", "name": "220GB - 30 days (Direct Data)", "price": 38800.00},
    {"id": "50000.01", "provider": "glo", "name": "320GB - 30 days (Direct Data)", "price": 48500.00},
    {"id": "60000.01", "provider": "glo", "name": "380GB - 30 days (Direct Data)", "price": 58200.00},
    {"id": "75000.01", "provider": "glo", "name": "475GB - 30 days (Direct Data)", "price": 72750.00},
    {"id": "150000.03", "provider": "glo", "name": "1TB (1000GB) - 365 days (Direct Data)", "price": 150000.00},

    # Airtel
    {"id": "499.91", "provider": "airtel", "name": "1GB - 1 day (Awoof Data)", "price": 484.91},
    {"id": "599.91", "provider": "airtel", "name": "1.5GB - 2 days (Awoof Data)", "price": 581.91},
    {"id": "749.91", "provider": "airtel", "name": "2GB - 2 days (Awoof Data)", "price": 727.41},
    {"id": "999.91", "provider": "airtel", "name": "3GB - 2 days (Awoof Data)", "price": 969.91},
    {"id": "1499.91", "provider": "airtel", "name": "5GB - 2 days (Awoof Data)", "price": 1454.91},
    {"id": "499.92", "provider": "airtel", "name": "500MB - 7 days (Direct Data)", "price": 484.92},
    {"id": "799.91", "provider": "airtel", "name": "1GB - 7 days (Direct Data)", "price": 775.91},
    {"id": "999.92", "provider": "airtel", "name": "1.5GB - 7 days (Direct Data)", "price": 969.92},
    {"id": "1499.92", "provider": "airtel", "name": "3.5GB - 7 days (Direct Data)", "price": 1454.92},
    {"id": "2499.91", "provider": "airtel", "name": "6GB - 7 days (Direct Data)", "price": 2424.91},
    {"id": "2999.91", "provider": "airtel", "name": "10GB - 7 days (Direct Data)", "price": 2909.91},
    {"id": "4999.91", "provider": "airtel", "name": "18GB - 7 days (Direct Data)", "price": 4849.91},
    {"id": "1499.93", "provider": "airtel", "name": "2GB - 30 days (Direct Data)", "price": 1454.93},
    {"id": "1999.91", "provider": "airtel", "name": "3GB - 30 days (Direct Data)", "price": 1939.91},
    {"id": "2499.92", "provider": "airtel", "name": "4GB - 30 days (Direct Data)", "price": 2424.92},
    {"id": "2999.92", "provider": "airtel", "name": "8GB - 30 days (Direct Data)", "price": 2909.92},
    {"id": "3999.91", "provider": "airtel", "name": "10GB - 30 days (Direct Data)", "price": 3879.91},
    {"id": "4999.92", "provider": "airtel", "name": "13GB - 30 days (Direct Data)", "price": 4849.92},
    {"id": "5999.91", "provider": "airtel", "name": "18GB - 30 days (Direct Data)", "price": 5819.91},
    {"id": "7999.91", "provider": "airtel", "name": "25GB - 30 days (Direct Data)", "price": 7759.91},
    {"id": "9999.91", "provider": "airtel", "name": "35GB - 30 days (Direct Data)", "price": 9699.91},
    {"id": "14999.91", "provider": "airtel", "name": "60GB - 30 days (Direct Data)", "price": 14549.91},
    {"id": "19999.91", "provider": "airtel", "name": "100GB - 30 days (Direct Data)", "price": 19399.91},
    {"id": "29999.91", "provider": "airtel", "name": "160GB - 30 days (Direct Data)", "price": 29099.91},
    {"id": "39999.91", "provider": "airtel", "name": "210GB - 30 days (Direct Data)", "price": 38799.91},
    {"id": "49999.91", "provider": "airtel", "name": "300GB - 90 days (Direct Data)", "price": 48499.91},
    {"id": "59999.91", "provider": "airtel", "name": "350GB - 90 days (Direct Data)", "price": 58199.91},

    # 9mobile — plan list given, but Nellobytes' network-code table did not
    # include a code for 9mobile. Listed for display; purchases will fail
    # cleanly (NellobytesError: "Unsupported network") until a code is confirmed.
    {"id": "50", "provider": "9mobile", "name": "50 MB - 30 days (SME)", "price": 25.00},
    {"id": "100", "provider": "9mobile", "name": "100 MB - 30 days (SME)", "price": 51.00},
    {"id": "300", "provider": "9mobile", "name": "300 MB - 30 days (SME)", "price": 153.00},
    {"id": "500", "provider": "9mobile", "name": "500 MB - 30 days (SME)", "price": 246.00},
    {"id": "1000", "provider": "9mobile", "name": "1 GB - 30 days (SME)", "price": 492.00},
    {"id": "2000", "provider": "9mobile", "name": "2 GB - 30 days (SME)", "price": 984.00},
    {"id": "3000", "provider": "9mobile", "name": "3 GB - 30 days (SME)", "price": 1476.00},
    {"id": "4000", "provider": "9mobile", "name": "4 GB - 30 days (SME)", "price": 1968.00},
    {"id": "5000", "provider": "9mobile", "name": "5 GB - 30 days (SME)", "price": 2460.00},
    {"id": "10000", "provider": "9mobile", "name": "10 GB - 30 days (SME)", "price": 4920.00},
    {"id": "15000", "provider": "9mobile", "name": "15 GB - 30 days (SME)", "price": 7380.00},
    {"id": "20000", "provider": "9mobile", "name": "20 GB - 30 days (SME)", "price": 9840.00},
    {"id": "25000", "provider": "9mobile", "name": "25 GB - 30 days (SME)", "price": 12300.00},
    {"id": "100.01", "provider": "9mobile", "name": "100MB - 1 day (Awoof Data)", "price": 93.00},
    {"id": "150.01", "provider": "9mobile", "name": "180MB - 1 days (Awoof Data)", "price": 139.50},
    {"id": "200.01", "provider": "9mobile", "name": "250MB - 1 days (Awoof Data)", "price": 186.00},
    {"id": "350.01", "provider": "9mobile", "name": "450MB - 1 day (Awoof Data)", "price": 325.50},
    {"id": "500.01", "provider": "9mobile", "name": "650MB - 3 days (Awoof Data)", "price": 465.00},
    {"id": "1500.01", "provider": "9mobile", "name": "1.75GB - 7 days (Direct Data)", "price": 1395.00},
    {"id": "600.01", "provider": "9mobile", "name": "650MB - 14 days (Direct Data)", "price": 558.00},
    {"id": "1000.01", "provider": "9mobile", "name": "1.1GB - 30 days (Direct Data)", "price": 930.00},
    {"id": "1200.01", "provider": "9mobile", "name": "1.4GB - 30 days (Direct Data)", "price": 1116.00},
    {"id": "2000.01", "provider": "9mobile", "name": "2.44GB - 30 days (Direct Data)", "price": 1860.00},
    {"id": "2500.01", "provider": "9mobile", "name": "3.17GB - 30 days (Direct Data)", "price": 2325.00},
    {"id": "3000.01", "provider": "9mobile", "name": "3.91GB - 30 days (Direct Data)", "price": 2790.00},
    {"id": "4000.01", "provider": "9mobile", "name": "5.10GB - 30 days (Direct Data)", "price": 3720.00},
    {"id": "5000.01", "provider": "9mobile", "name": "6.5GB - 30 days (Direct Data)", "price": 4650.00},
    {"id": "12000.01", "provider": "9mobile", "name": "16GB - 30 days (Direct Data)", "price": 11160.00},
    {"id": "18500.01", "provider": "9mobile", "name": "24.3GB - 30 days (Direct Data)", "price": 17205.00},
    {"id": "20000.01", "provider": "9mobile", "name": "26.5GB - 30 days (Direct Data)", "price": 18600.00},
    {"id": "30000.01", "provider": "9mobile", "name": "39GB - 60 days (Direct Data)", "price": 27900.00},
]

# Nellobytes Cable TV package codes. Only DStv package codes were provided —
# their docs list GOtv/StarTimes/Showmax as available CableTV types
# (APICableTVTypeV2.asp) but never pasted actual package codes for them, so
# those are NOT included here. Purchases for GOTV/STARTIMES/SHOWMAX will fail
# cleanly (NellobytesService.CABLE_TV_CODES has entries for all four, but
# there are no plans to select from those three) until real package codes
# are supplied.
CABLE_PLANS = [
    {"id": "dstv-padi", "provider": "DSTV", "name": "DStv Padi", "price": 4400.00},
    {"id": "dstv-yanga", "provider": "DSTV", "name": "DStv Yanga", "price": 6000.00},
    {"id": "dstv-confam", "provider": "DSTV", "name": "DStv Confam", "price": 11000.00},
    {"id": "dstv79", "provider": "DSTV", "name": "DStv Compact", "price": 19000.00},
    {"id": "dstv3", "provider": "DSTV", "name": "DStv Premium", "price": 44500.00},
    {"id": "dstv7", "provider": "DSTV", "name": "DStv Compact Plus", "price": 30000.00},
    {"id": "dstv9", "provider": "DSTV", "name": "DStv Premium-French", "price": 69000.00},
    {"id": "dstv10", "provider": "DSTV", "name": "DStv Premium-Asia", "price": 50500.00},
    {"id": "confam-extra", "provider": "DSTV", "name": "DStv Confam + ExtraView", "price": 17000.00},
    {"id": "yanga-extra", "provider": "DSTV", "name": "DStv Yanga + ExtraView", "price": 12000.00},
    {"id": "padi-extra", "provider": "DSTV", "name": "DStv Padi + ExtraView", "price": 10400.00},
    {"id": "dstv30", "provider": "DSTV", "name": "DStv Compact + Extra View", "price": 25000.00},
    {"id": "com-frenchtouch", "provider": "DSTV", "name": "DStv Compact + French Touch", "price": 26000.00},
    {"id": "dstv33", "provider": "DSTV", "name": "DStv Premium + Extra View", "price": 50500.00},
    {"id": "com-frenchtouch-extra", "provider": "DSTV", "name": "DStv Compact + French Touch + ExtraView", "price": 32000.00},
    {"id": "dstv43", "provider": "DSTV", "name": "DStv Compact Plus + French Plus", "price": 54500.00},
    {"id": "complus-frenchtouch", "provider": "DSTV", "name": "DStv Compact Plus + French Touch", "price": 37000.00},
    {"id": "dstv45", "provider": "DSTV", "name": "DStv Compact Plus + Extra View", "price": 36000.00},
    {"id": "complus-french-extraview", "provider": "DSTV", "name": "DStv Compact Plus + FrenchPlus + Extra View", "price": 60500.00},
    {"id": "dstv47", "provider": "DSTV", "name": "DStv Compact + French Plus", "price": 43500.00},
    {"id": "dstv62", "provider": "DSTV", "name": "DStv Premium + French + Extra View", "price": 75000.00},
    {"id": "frenchplus-addon", "provider": "DSTV", "name": "DStv French Plus Add-on", "price": 24500.00},
    {"id": "dstv-greatwall", "provider": "DSTV", "name": "DStv Great Wall Standalone Bouquet", "price": 3800.00},
    {"id": "frenchtouch-addon", "provider": "DSTV", "name": "DStv French Touch Add-on", "price": 7000.00},
    {"id": "french11", "provider": "DSTV", "name": "DStv French 11", "price": 10800.00},
    {"id": "dstv-yanga-showmax", "provider": "DSTV", "name": "DStv Yanga + Showmax", "price": 8250.00},
    {"id": "dstv-greatwall-showmax", "provider": "DSTV", "name": "DStv Great Wall Standalone Bouquet + Showmax", "price": 8300.00},
    {"id": "dstv-compact-plus-showmax", "provider": "DSTV", "name": "DStv Compact Plus + Showmax", "price": 32250.00},
    {"id": "dstv-confam-showmax", "provider": "DSTV", "name": "DStv Confam + Showmax", "price": 13250.00},
    {"id": "dstv-compact-showmax", "provider": "DSTV", "name": "DStv Compact + Showmax", "price": 21250.00},
    {"id": "dstv-padi-showmax", "provider": "DSTV", "name": "DStv Padi + Showmax", "price": 8900.00},
    {"id": "dstv-asia-showmax", "provider": "DSTV", "name": "DStv Asia + Showmax", "price": 19400.00},
    {"id": "dstv-premium-french-showmax", "provider": "DSTV", "name": "DStv Premium + French + Showmax", "price": 69000.00},
    {"id": "dstv-premium-showmax", "provider": "DSTV", "name": "DStv Premium + Showmax", "price": 44500.00},
    {"id": "dstv-indian", "provider": "DSTV", "name": "DStv Indian", "price": 14900.00},
    {"id": "dstv-indian-add-on", "provider": "DSTV", "name": "DStv India Add-on", "price": 14900.00},
    {"id": "dstv-movie-bundle-add-on", "provider": "DSTV", "name": "DStv Movie Bundle Add-on", "price": 3500.00},
    {"id": "dstv-premium-wafr-showmax", "provider": "DSTV", "name": "DStv Premium W/Afr + Showmax", "price": 50500.00},
    {"id": "dstv-showmax-premier-league", "provider": "DSTV", "name": "DStv Showmax Premier League Add-on", "price": 3600.00},
    {"id": "dstv-compact-plus-movie", "provider": "DSTV", "name": "DStv Compact Plus Movie Bundle Add-on E36", "price": 3500.00},
]


def get_data_plan(plan_id, network):
    """
    Reads DataPlan from the DB (not the DATA_PLANS list above) — the DB is what
    seed_plans/sync_plans populate from DATA_PLANS and what admins subsequently
    edit (price, is_active) via the dashboard, so purchases must respect those
    edits instead of a frozen snapshot.
    """
    from .models import DataPlan

    plan_id = str(plan_id)
    network = (network or "").strip().upper()
    plan = DataPlan.objects.filter(network=network, plan_id=plan_id, is_active=True).first()
    if plan is None:
        return None
    return {
        "id": plan.plan_id,
        "provider": plan.network.lower(),
        "name": plan.plan_name,
        "price": plan.selling_price,
    }


def get_cable_plan(plan_id, provider):
    """Reads CablePlan from the DB — see get_data_plan's note above."""
    from .models import CablePlan

    plan_id = str(plan_id)
    provider = (provider or "").strip().upper()
    plan = CablePlan.objects.filter(provider_name=provider, plan_id=plan_id, is_active=True).first()
    if plan is None:
        return None
    return {
        "id": plan.plan_id,
        "provider": plan.provider_name,
        "name": plan.plan_name,
        "price": plan.selling_price,
    }
