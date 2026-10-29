from django.apps import AppConfig
from django.core import checks


class VtuConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'vtu'

    def ready(self):
        checks.register(check_provider_configuration, checks.Tags.compatibility)


def check_provider_configuration(app_configs, **kwargs):
    """Surface .env mistakes for any provider that is switched on but missing settings."""
    from vtu.gateway import registry

    return [
        checks.Warning(problem, hint="Set it in .env (see .env.example) or disable the provider.", id="vtu.W001")
        for problem in registry.validate_configuration()
    ]
