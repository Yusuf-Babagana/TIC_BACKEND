# TIC Backend API Reference

**Base URL**: `https://ticbackend.pythonanywhere.com`

**Auth**: All endpoints except register, login, token-refresh, OTP, and public product listings require a Bearer JWT token.  
`Authorization: Bearer <access_token>`

---

## Authentication

### POST /users/register/
Create a new user. Returns JWT tokens + wallet info.

```json
{ "username": "john", "email": "john@email.com", "phone_number": "080...", "password": "..." }
```
→ `201`
```json
{ "message": "...", "user": { "id": 1, "username": "john", ... }, "token": { "access": "jwt...", "refresh": "jwt..." }, "wallet": { "balance": "0.00", ... } }
```

### POST /users/login/
```json
{ "username": "john", "password": "..." }
```
→ `200`
```json
{ "access": "jwt...", "refresh": "jwt...", "user": { "id": 1, "username": "john", "email": "...", "phone_number": "...", "first_name": "...", "last_name": "..." }, "wallet": { "balance": "0.00", "bank_name": null, "account_number": null } }
```

### POST /users/token/refresh/
```json
{ "refresh": "jwt..." }
```
→ `200` `{ "access": "new-jwt..." }`

### POST /users/send-otp/
```json
{ "email": "john@email.com" }
// or { "phone_number": "080..." }
```
→ `200` `{ "message": "OTP sent successfully" }`

### POST /users/verify-otp/
```json
{ "email": "john@email.com", "otp": "123456" }
```
→ `200` `{ "message": "OTP verified successfully" }`

---

## Wallet

### GET /wallet/balance/
→ `200`
```json
{ "balance": "1500.00", "bank_name": "Wema Bank", "account_number": "9876543210" }
```

### GET /wallet/history/
Paginated (20/page). Filtered to current user.
→ `200`
```json
{ "count": 45, "next": "...", "previous": null, "results": [ { "id": 1, "trans_type": "DATA", "amount": "500.00", "reference": "SUCCESS-ABC123...", "status": "SUCCESSFUL", "formatted_date": "30 May, 2026 - 10:30 AM" } ] }
```

### POST /wallet/generate-account/
Creates Monnify virtual account.
→ `200`
```json
{ "message": "Account generated successfully", "data": { "bank_name": "Wema Bank", "account_number": "9876543210", "account_reference": "TIC-1" } }
```

### POST /wallet/submit-bvn/
```json
{ "bvn": "22241354089", "nin": "72533591954" }
```
→ Same response as generate-account.

### POST /wallet/webhook/monnify/
**No auth.** CSRF exempt. Monnify pushes deposits here. See `wallet/views.py`.

---

## VTU — Plans

### GET /vtu/plans/?category=DATA&provider=mtn
`category` required (`DATA` or `CABLE`). `provider` optional.
→ `200`
```json
[ { "id": 78, "provider": "mtn", "name": "1 GB (1 Day)", "price": 315.0 }, ... ]
```

---

## VTU — Unified Purchase

### POST /vtu/purchase/
Single endpoint for all categories.
```json
{ "category": "DATA", "target_id": "08069278540", "plan_id": 78 }
// Airtime: { "category": "AIRTIME", "target_id": "080...", "plan_id": 1, "amount": "200" }
// Cable:   { "category": "CABLE",   "target_id": "1234567890", "plan_id": 3, "amount": "4400" }
// Elect:   { "category": "ELECTRICITY", "target_id": "meter_no", "plan_id": 1, "amount": "2000" }
```
→ `200` (proxied from CheapDataHub)
```json
{ "status": "true", "message": "Data Purchase Successful", "reference": "CDH-REF-123" }
```

---

## VTU — Reseller Endpoints (CheapDataHub-format)

### POST /api/v1/resellers/airtime/purchase/
```json
{ "provider_id": 1, "phone_number": "08069278540", "amount": "200" }
```

### POST /api/v1/resellers/data/purchase/
```json
{ "bundle_id": 78, "phone_number": "08069278540" }
```
`bundle_id` = the `id` field from `GET /vtu/plans/`.

### POST /api/v1/resellers/electricity/purchase/
```json
{ "disco_id": 1, "meter_number": "...", "amount": "2000", "meter_type": "prepaid", "phone": "080..." }
```

### POST /api/v1/resellers/cable/purchase/
```json
{ "plan_id": 3, "cardnumber": "1234567890", "phone": "080..." }
```

---

## Fashion — Products

### GET /fashion/categories/
### GET /fashion/categories/{id}/
Public. → `[{ "id": 1, "name": "Men", "image": "...", "product_count": 5 }]`

### GET /fashion/products/
### GET /fashion/products/{id}/
Public. `?category=1` to filter.
→ `[{ "id": 1, "category": 1, "name": "...", "description": "...", "price": "5000.00", "stock": 10, "image": "...", "is_available": true, "created_at": "..." }]`

---

## Fashion — Measurements

### GET /fashion/measurements/
### PATCH /fashion/measurements/
```json
{ "neck": 15.5, "chest": 40, "waist": 34, "shoulder": 18, "length": 28 }
```
Auto-creates if none exists.

---

## Fashion — Tailoring

### POST /fashion/custom-tailoring/
Multipart: `description` (text) + `reference_image` (file, optional).
→ `201` `{ "id": 1, "status": "pending", ... }`

### GET /fashion/my-orders/
Returns current user's orders.

### POST /fashion/pay-tailoring/
```json
{ "order_id": 1 }
```
Deducts `price_quote` from wallet, sets status to `paid`.
→ `200` `{ "message": "Payment successful", "order_id": 1 }`

### POST /fashion/custom-requests/
Alternative create endpoint (multipart). Same as custom-tailoring.

### GET|PATCH /fashion/admin/orders/{pk}/
Admin only. Update status/price_quote.

---

## Fashion — Notifications

### GET /fashion/notifications/
Current user's notifications.
→ `[{ "id": 1, "order": 1, "message": "Order updated...", "is_read": false, "created_at": "..." }]`

### PATCH /fashion/notifications/{pk}/read/
Marks as read. Always sets `is_read=true`.
→ `{ "is_read": true }`

---

## Common Errors

| Code | Meaning |
|------|---------|
| `400` | Bad request (missing/invalid fields) |
| `401` | Unauthorized (missing/expired token) |
| `402` | Insufficient wallet balance |
| `404` | Resource not found |
| `502` | CheapDataHub provider error |
| `503` | Service temporarily unavailable |

All error responses: `{ "status": "false", "message": "..." }` or `{ "error": "..." }`.

---

## Transaction Types

| trans_type | Meaning |
|-----------|---------|
| `DATA` | Data bundle purchase |
| `AIRTIME` | Airtime top-up |
| `UTILITY` | Electricity / Cable / Tailoring payment |
| `DEPOSIT` | Wallet funding via Monnify |

## Transaction Statuses

| status | Meaning |
|--------|---------|
| `SUCCESSFUL` | Completed successfully |
| `FAILED` | Provider rejected or system error |
| `PENDING` | Awaiting processing |

---

## CheapDataHub Provider IDs

| Network | provider_id |
|---------|-------------|
| MTN | 1 |
| GLO | 2 |
| AIRTEL | 3 |
| 9MOBILE | 4 |

| DISCO | disco_id |
|-------|----------|
| AEDC | 1 | EKEDC | 2 | IBEDC | 3 | IKEDC | 4 |
| KADUNA | 5 | PHED | 6 | JED | 7 | EEDC | 8 |
| YOLA | 9 | BENIN | 10 |

| Cable | plan_id prefix |
|-------|----------------|
| GOTV | 1.x |
| DSTV | 2.x |
| STARTIMES | 3.x |
