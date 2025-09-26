from django.urls import path, include
from rest_framework.routers import DefaultRouter
# Importe o ProdutoViewSet junto com o ClienteViewSet
from .views import (
    ClienteViewSet, ProdutoViewSet, OrcamentoViewSet, ItemOrcamentoViewSet,
    PedidoViewSet, ItemPedidoViewSet
)

router = DefaultRouter()

router.register(r'clientes', ClienteViewSet)
router.register(r'produtos', ProdutoViewSet)
router.register(r'orcamentos', OrcamentoViewSet)
router.register(r'itens-orcamento', ItemOrcamentoViewSet)
router.register(r'pedidos', PedidoViewSet)
router.register(r'itens-pedido', ItemPedidoViewSet)

urlpatterns = [
    path('', include(router.urls)),
]