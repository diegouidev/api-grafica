from django.urls import path, include
from rest_framework.routers import DefaultRouter
# Importe o ProdutoViewSet junto com o ClienteViewSet
from .views import (
    ClienteViewSet, ProdutoViewSet, OrcamentoViewSet, ItemOrcamentoViewSet,
    PedidoViewSet, ItemPedidoViewSet, DashboardStatsView, PagamentoViewSet, 
    DespesaViewSet, DespesaConsolidadaView, VendasRecentesView, FaturamentoPorPagamentoView
)

router = DefaultRouter()

router.register(r'clientes', ClienteViewSet)
router.register(r'orcamentos', OrcamentoViewSet)
router.register(r'itens-orcamento', ItemOrcamentoViewSet)
router.register(r'pedidos', PedidoViewSet)
router.register(r'itens-pedido', ItemPedidoViewSet)
router.register(r'produtos', ProdutoViewSet, basename='produto')
router.register(r'pagamentos', PagamentoViewSet, basename='pagamento')
router.register(r'despesas-gerais', DespesaViewSet, basename='despesa')

urlpatterns = [
    path('', include(router.urls)),
    path('dashboard-stats/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('despesas/', DespesaConsolidadaView.as_view(), name='despesa-consolidada'),
    path('vendas-recentes/', VendasRecentesView.as_view(), name='vendas-recentes'),
    path('faturamento-por-pagamento/', FaturamentoPorPagamentoView.as_view(), name='faturamento-por-pagamento'),
]