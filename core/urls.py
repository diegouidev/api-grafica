from django.urls import path, include
from rest_framework.routers import DefaultRouter
# Importe o ProdutoViewSet junto com o ClienteViewSet
from .views import (
    ClienteViewSet, ProdutoViewSet, OrcamentoViewSet, ItemOrcamentoViewSet,
    PedidoViewSet, ItemPedidoViewSet, DashboardStatsView, PagamentoViewSet, 
    DespesaViewSet, DespesaConsolidadaView, VendasRecentesView, FaturamentoPorPagamentoView, 
    RelatorioFaturamentoView, OrcamentoPDFView, PedidoPDFView, EmpresaSettingsView, UserProfileView, 
    ChangePasswordView, EmpresaPublicaView, EvolucaoVendasView, PedidosPorStatusView,
    ProdutosMaisVendidosView, ClientesMaisAtivosView, RelatorioClientesView, RelatorioPedidosView, RelatorioOrcamentosView,
    RelatorioProdutosView
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
    path('public/empresa/', EmpresaPublicaView.as_view(), name='empresa-publica'),
    path('dashboard-stats/', DashboardStatsView.as_view(), name='dashboard-stats'),
    path('despesas/', DespesaConsolidadaView.as_view(), name='despesa-consolidada'),
    path('vendas-recentes/', VendasRecentesView.as_view(), name='vendas-recentes'),
    path('faturamento-por-pagamento/', FaturamentoPorPagamentoView.as_view(), name='faturamento-por-pagamento'),
    path('relatorios/faturamento/', RelatorioFaturamentoView.as_view(), name='relatorio-faturamento'),
    path('orcamentos/<int:pk>/pdf/', OrcamentoPDFView.as_view(), name='orcamento-pdf'),
    path('pedidos/<int:pk>/pdf/', PedidoPDFView.as_view(), name='pedido-pdf'),
    path('empresa-settings/', EmpresaSettingsView.as_view(), name='empresa-settings'),
    path('profile/', UserProfileView.as_view(), name='user-profile'),
    path('profile/change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('relatorios/evolucao-vendas/', EvolucaoVendasView.as_view(), name='evolucao-vendas'),
    path('relatorios/pedidos-por-status/', PedidosPorStatusView.as_view(), name='pedidos-por-status'),
    path('relatorios/produtos-mais-vendidos/', ProdutosMaisVendidosView.as_view(), name='produtos-mais-vendidos'),
    path('relatorios/clientes-mais-ativos/', ClientesMaisAtivosView.as_view(), name='clientes-mais-ativos'),
    path('relatorios/clientes/', RelatorioClientesView.as_view(), name='relatorio-clientes'),
    path('relatorios/pedidos/', RelatorioPedidosView.as_view(), name='relatorio-pedidos'),
    path('relatorios/orcamentos/', RelatorioOrcamentosView.as_view(), name='relatorio-orcamentos'),
    path('relatorios/produtos/', RelatorioProdutosView.as_view(), name='relatorio-produtos'),
    
]