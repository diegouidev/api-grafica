# core/admin.py

from django.contrib import admin
from .models import (
    Cliente,
    Produto,
    Orcamento,
    ItemOrcamento,
    Pedido,
    ItemPedido,
    Despesa
)

# O comando admin.site.register() torna o modelo visível e gerenciável
# na interface de administração do Django.

admin.site.register(Cliente)
admin.site.register(Produto)
admin.site.register(Orcamento)
admin.site.register(ItemOrcamento)
admin.site.register(Pedido)
admin.site.register(ItemPedido)
admin.site.register(Despesa)