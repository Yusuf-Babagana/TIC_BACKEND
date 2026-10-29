# VTU provider gateway

Provider-agnostic purchase pipeline for airtime, data, cable TV and electricity.
Code: `vtu/gateway/`. Adapters: **Nellobytes** (full) and **Gongoz** (conservative, see below);
adding another is described below.

## How it works

```
views.py ──► engine.execute_purchase()
               1. replay if Idempotency-Key already used          (ledger)
               2. router.select()  eligible providers, ordered     (router, health)
               3. ledger.reserve() debit wallet + PENDING txn, atomically
               4. for each provider: PurchaseAttempt row → adapter.purchase()
                    ACCEPTED   → stop, txn stays PENDING until confirmed
                    AMBIGUOUS  → stop, txn stays PENDING, NO failover, NO refund
                    REJECTED   → next provider only if failover-safe; else stop
               5. every attempt REJECTED → ledger.settle(FAILED) = refund once
Later:  webhook / status poll / reconcile command ─► engine.reconcile_transaction() ─► ledger.settle()
```

| Module | Responsibility |
|---|---|
| `adapters/<name>.py` | The *only* place that knows a provider's URLs, params, status strings. |
| `base.py` | `ProviderAdapter` contract. |
| `types.py` | Normalised `PurchaseRequest`, `ProviderResult`, `Outcome`, `ErrorCategory`, `OrderStatus`, `redact()`. |
| `config.py` / `registry.py` | `.env` loading + validation; adapter registry. |
| `router.py` / `health.py` | Provider choice (pluggable policy) and circuit breaker. |
| `ledger.py` | All wallet movement; state transitions; audit events; exactly-once refund. |
| `engine.py` | Orchestration, reconciliation, webhook handling. |

### The failover rule (money safety)

The next provider is tried **only** when the previous returned `REJECTED` with a
provider-side category (`auth`, `provider_balance`, `maintenance`, `rate_limit`,
`unsupported`) — i.e. it answered and confirmed it created no order. A timeout, dropped
connection, unparseable body, or any reply carrying an order id is `AMBIGUOUS`: the
order may exist, so the engine stops, keeps the money reserved and reconciles by
asking that provider. A bad recipient/amount (`invalid_request`) is not retried
elsewhere — every provider would refuse it.

### Transaction states

`PENDING → SUCCESSFUL` (terminal) · `PENDING → FAILED` (wallet refunded once,
`refunded_at` set) · `FAILED → REFUNDED` (legacy admin button only; blocked if
`refunded_at` is set). Every change writes a `TransactionEvent` (visible inline on the
Transaction admin page). If a provider reports success *after* we refunded, nothing
changes automatically; a `CRITICAL` log and an `ANOMALY` event are recorded for a human.

## Configure a provider (.env)

See `.env.example`. Pattern `VTU_<NAME>_<SETTING>`:

```env
VTU_NELLOBYTES_ENABLED=true
VTU_NELLOBYTES_USER_ID=...
VTU_NELLOBYTES_API_KEY=...
VTU_NELLOBYTES_PRIORITY=10      # lower = tried first
```

Legacy `VTU_USER_ID` / `VTU_API_KEY` still work. A provider enabled but missing a
required setting is **never routed** and is reported by `python manage.py check`.
Secrets exist only in the environment: never in the DB, admin, API responses or logs.

Check it: `python manage.py vtu_providers` (add `--test` for a read-only
auth/balance probe that places no order).

## Priority and failover

Effective priority (lower first): admin override (Django admin → *Provider states*)
> `VTU_<NAME>_PRIORITY` > adapter `default_priority`. A provider is skipped when
disabled in `.env`, disabled in admin, misconfigured, unsupported for the request, or
suspended. After `VTU_FAILURE_THRESHOLD` (5) consecutive health-affecting failures it is
suspended for `VTU_SUSPEND_MINUTES` (10), then tried again; one more failure re-suspends
immediately, one success resets it. Other policies (lowest cost, best success rate):
subclass `router.RoutingPolicy` and set `VTU_ROUTING_POLICY=dotted.path.Class`.

## Add a new provider

1. **Read the provider's official API docs.** Do not guess endpoints or status codes.
2. Create `vtu/gateway/adapters/<name>.py`:

```python
from ..base import ProviderAdapter
from ..config import ConfigSpec
from ..types import (ErrorCategory, OrderStatus, Outcome, ProviderResult, Service, StatusResult)

class ExampleAdapter(ProviderAdapter):
    name = "example"                     # lowercase; env prefix VTU_EXAMPLE_
    label = "Example VTU"
    services = (Service.AIRTIME, Service.DATA)
    config_spec = ConfigSpec(
        required=("API_KEY",), optional={"BASE_URL": "https://api.example.com"},
        secrets=("API_KEY",),
    )
    default_priority = 20                # default_enabled stays False

    def supports(self, r):               # networks / plans you can actually serve
        return r.service in self.services and r.network in {"MTN", "GLO"}

    def purchase(self, r):
        # r.reference is the idempotent request id to send to the provider.
        # Return REJECTED only if the provider *answered and said no*; anything
        # doubtful (timeout, reset, unparseable) MUST be AMBIGUOUS.
        ...

    def query_status(self, provider_order_id="", reference=""):
        # SUCCESSFUL only on an explicit success; FAILED only on explicit failure/reversal;
        # PENDING while processing; UNKNOWN if unsure or the lookup fails.
        ...

    def check_connectivity(self):        # read-only auth/balance call - never an order
        return {"ok": True, "detail": "...", "elapsed_ms": 12}

    def parse_webhook(self, request):    # if it sends callbacks
        # Verify the signature here and raise WebhookRejected if invalid; return
        # WebhookEvent(..., claimed_status=OrderStatus.X, verified=True). Without a
        # signature return verified=False: the engine then confirms via query_status.
        ...
```

3. Register: add `register(ExampleAdapter)` in `vtu/gateway/adapters/__init__.py`.
4. Add its variables to `.env` and `.env.example`; give the provider its callback URL
   `https://<host>/vtu/webhook/example/` (generic route; automatic).
5. **Test**: copy the Nellobytes cases in `vtu/test_gateway.py` with a mocked HTTP layer
   (accepted, each rejection class, timeout → ambiguous, status mapping, no secrets in
   results). `python manage.py test vtu`.
6. `python manage.py vtu_providers --test`, then enable it.

Not covered by the framework: **per-provider plan codes.** Data/cable plans store
Nellobytes' codes in `DataPlan.plan_id` / `CablePlan.plan_id`. A second provider with
different codes needs a mapping (translate `request.plan_id` inside its `supports`/
`purchase`, and return `supports=False` for plans it cannot map).

## Pending transactions and reconciliation

A purchase stays `PENDING` until a provider answer is confirmed by one of:
the provider callback (`/vtu/webhook/<provider>/`, Nellobytes keeps its original
`/vtu/webhook/nellobytes/`), the app polling `/wallet/transaction-status/<ref>/`, or the
sweep `python manage.py reconcile_nellobytes_orders` (all providers; schedule every few
minutes). All three call `engine.reconcile_transaction`, which queries the provider holding
the order and settles only on a definite SUCCESSFUL/FAILED. `UNKNOWN`/`PENDING`/query
errors never refund. Unsigned callbacks are treated as a "check now" hint, never as truth.
A PENDING transaction with **no** submission recorded (worker died before calling any
provider) is refunded after 10 minutes. Stuck `PENDING` orders that providers cannot
resolve: confirm in the provider's own dashboard, then use the Transaction admin action
*Mark PENDING as FAILED and refund* (or leave them if delivered).

## Idempotency

Clients may send `Idempotency-Key: <8-100 chars [A-Za-z0-9._:-]>` (or `idempotency_key`
in the body). The same key never debits twice or submits twice; a repeat returns the
original reference (`idempotent_replay: true`). Unique per user (DB constraint).
Requests without a key behave as before.

## Testing safely

`python manage.py test vtu wallet` — providers are fakes or a mocked HTTP layer; the test
base class fails any test that makes an unmocked HTTP call. Never test failover with real
funds; use `vtu_providers --test` (read-only) against live providers.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| "temporarily under maintenance" (503) | all providers suspended/disabled, or provider float empty (`provider_balance`). `vtu_providers`; Provider states admin page. |
| `INVALID_CREDENTIALS` | wrong/rotated key or IP not whitelisted. `vtu_providers --test`. |
| Orders stuck PENDING | callbacks not arriving (see Webhook Log in dashboard); run the reconcile command. |
| `vtu.W001` in `manage.py check` | enabled provider missing a required env var. |
| Provider keeps getting suspended | Provider states → *Last error*; failures within `VTU_FAILURE_THRESHOLD`. Reset circuit action clears it. |
| Log line `VTU ANOMALY` | provider says delivered after we refunded: reconcile manually with the provider. |

## Gongoz (`adapters/gongoz.py`)

Built from the vendor's Postman docs and dashboard id tables. Those docs show **no response
bodies, no status vocabulary, no reference/idempotency field and no webhook format**, so the
adapter never guesses them:

* **Enable:** `VTU_GONGOZ_ENABLED=true`, `VTU_GONGOZ_API_KEY=<token>` (never the sample token
  printed in the public docs). Off by default. Optional `VTU_GONGOZ_PRIORITY` (default 20, so it
  is the fallback behind Nellobytes).
* **Accepted** only when Gongoz answers 200/201 with an order `id`; stored as `<endpoint>:<id>`
  (e.g. `topup:58`). 401/403/429/400/404 are confirmed rejections (400 with "balance/insufficient"
  is treated as *our* Gongoz float being empty and its text is never shown to customers). Timeouts,
  5xx, a reply without an id, or non-JSON are **ambiguous** (no failover, no refund).
* **Completion is opt-in.** Orders stay PENDING until you list Gongoz's real status words:
  make one small real purchase, `GET /api/topup/<id>` (or data/billpayment/cablesub) and read the
  `Status` value, then set `VTU_GONGOZ_SUCCESS_STATUSES` / `VTU_GONGOZ_FAILED_STATUSES`
  (comma-separated, case-insensitive). An unlisted word is logged ("unconfigured status ...") and
  left unresolved.
* **Timeouts cannot be reconciled automatically.** Gongoz can be queried only by *its* id. If the
  submit reply never arrived, check the order in Gongoz's dashboard and settle via the Transaction
  admin action.
* **Webhooks are refused** (format undocumented); resolution is by polling. The "Webhook URL"
  setting on Gongoz's dashboard should stay empty.
* **Airtime** (MTN, GLO, 9MOBILE, AIRTEL) and **electricity** (11 discos) work with the built-in id
  tables. **Data and cable are served only for plans you map** in admin -> *Provider plan codes*:
  `provider=gongoz`, service, network, **our** `plan_id`, and Gongoz's own plan id from its price
  list. Check that size/validity/price match before mapping: its catalogue has many plan types
  (SME, GIFTING, CORPORATE...) that differ from ours. Unmapped plans are never routed there.
* Customer lookup (`validateiuc` / `validatemeter`) is wired but only used if Nellobytes cannot
  verify; the reply field for the name is unknown, so an unrecognised reply is refused.
* Cable name `STARTIME` in Gongoz's table = our `STARTIMES` (id 3).
* Assumed, unverified: that airtime orders are queried at `/api/topup/<id>` (the docs' airtime
  query URL points at `/api/data/id`, probably a copy-paste error).

### Making Gongoz the primary provider (what the mobile app sees)

The app only talks to our backend (`/vtu/plans/`, `/vtu/purchase/`), so no app update is needed.

1. `.env`: `VTU_GONGOZ_ENABLED=true`, `VTU_GONGOZ_API_KEY=...`, `VTU_GONGOZ_PRIORITY=1`,
   `VTU_NELLOBYTES_PRIORITY=50` (kept as airtime/electricity fallback; or set
   `VTU_NELLOBYTES_ENABLED=false` to stop using it entirely). Airtime and electricity go to
   Gongoz first with no further setup.
2. Data and cable plan ids are provider-specific codes, so import Gongoz's catalogue:
   `python manage.py gongoz_import_plans` (preview), then `... --apply --margin 10`
   (new plans priced at Gongoz cost + 10%; existing imported plans keep admin prices; re-run any
   time to refresh costs and retire plans Gongoz dropped). Add `--deactivate-nellobytes` so the
   app lists only Gongoz plans. Without that flag both catalogues are listed. Use
   `--exclude-types` / `--types` to filter plan types (default skips TALKMORE voice plans).
3. Plans carry a `source`. Gongoz-sourced plan ids are never sent to Nellobytes and vice versa,
   so a plan can never be bought from a provider that has a different bundle under that id.
4. `seed_plans` only touches Nellobytes-sourced plans, so it can't wipe imported ones.
5. Customer verification (meter / smartcard) tries providers in priority order and falls through
   to the next when one cannot confirm.
