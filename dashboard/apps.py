from django.apps import AppConfig


class DashboardConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'dashboard'

    def ready(self):
        import dashboard.signals
        from dashboard.signals import (
            connect_marketing_signals,
            connect_fashion_signals,
            connect_wallet_signals,
        )
        try:
            connect_marketing_signals()
            connect_fashion_signals()
            connect_wallet_signals()
        except Exception:
            pass
