from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    # --- Adicione o método ready abaixo ---
    def ready(self):
        # Importa os sinais para que eles sejam registrados
        import core.signals