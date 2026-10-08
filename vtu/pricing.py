from decimal import ROUND_HALF_UP, Decimal

from .models import ServicePricing

CENT = Decimal("0.01")


def get_pricing_rule(category, provider):
    """Provider-specific active rule, else the "*" fallback, else None."""
    provider = (provider or "").strip().upper()
    rules = {
        r.provider: r
        for r in ServicePricing.objects.filter(
            category=category, is_active=True, provider__in=[provider, "*"]
        )
    }
    return rules.get(provider) or rules.get("*")


def customer_price(category, provider, amount):
    """What the customer is charged for a variable-amount service."""
    amount = Decimal(str(amount))
    rule = get_pricing_rule(category, provider)
    if rule is None:
        return amount.quantize(CENT, rounding=ROUND_HALF_UP)
    price = amount + amount * rule.percent_adjust / Decimal("100") + rule.flat_fee
    return max(price, CENT).quantize(CENT, rounding=ROUND_HALF_UP)
