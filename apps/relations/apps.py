from django.apps import AppConfig


class RelationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.relations'
    
    def ready(self):
        import apps.relations.signals  # noqa
