from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Q
from .models import Pedido, Despesa
import datetime
# Importe o modelo e o serializer de Produto
from .models import (
    Cliente, Produto, Orcamento, ItemOrcamento, Pedido, ItemPedido
)
from .serializers import (
    ClienteSerializer, ProdutoSerializer, OrcamentoSerializer,
    ItemOrcamentoSerializer, PedidoSerializer, ItemPedidoSerializer
)


class ClienteViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API que permite aos clientes serem visualizados ou editados.
    """
    queryset = Cliente.objects.all().order_by('-data_cadastro')
    serializer_class = ClienteSerializer

class ProdutoViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API que permite aos produtos serem visualizados ou editados.
    Permite filtrar por tipo_precificacao (ex: /api/produtos/?tipo_precificacao=M2)
    """
    serializer_class = ProdutoSerializer

    def get_queryset(self):
        queryset = Produto.objects.all().order_by('nome')
        tipo = self.request.query_params.get('tipo_precificacao')
        if tipo is not None:
            queryset = queryset.filter(tipo_precificacao=tipo)
        return queryset


class OrcamentoViewSet(viewsets.ModelViewSet):
    queryset = Orcamento.objects.all().order_by('-data_criacao')
    serializer_class = OrcamentoSerializer

    def perform_create(self, serializer):
        # O serializer.save() já vai criar o orçamento e os itens
        # graças à nossa configuração no serializer.
        # O Django REST Framework é inteligente o suficiente para lidar
        # com a criação de objetos aninhados se o serializer estiver configurado.
        # Depois de salvar, chamamos o método para recalcular o total.
        orcamento_instance = serializer.save()
        orcamento_instance.recalcular_total()

class ItemOrcamentoViewSet(viewsets.ModelViewSet):
    queryset = ItemOrcamento.objects.all()
    serializer_class = ItemOrcamentoSerializer


class PedidoViewSet(viewsets.ModelViewSet):
    queryset = Pedido.objects.all()
    serializer_class = PedidoSerializer

class ItemPedidoViewSet(viewsets.ModelViewSet):
    queryset = ItemPedido.objects.all()
    serializer_class = ItemPedidoSerializer



class DashboardStatsView(APIView):
    """
    View para fornecer estatísticas agregadas para o dashboard.
    """
    permission_classes = [IsAuthenticated] # Garante que apenas usuários logados acessem

    def get(self, request, *args, **kwargs):
        # Pega o primeiro e último dia do mês atual
        today = datetime.date.today()
        start_of_month = today.replace(day=1)

        # Filtra os pedidos e despesas pelo mês atual
        pedidos_no_mes = Pedido.objects.filter(data_criacao__gte=start_of_month)
        despesas_no_mes = Despesa.objects.filter(data__gte=start_of_month)

        # 1. Calcula o Faturamento (Pedidos com status 'PAGO')
        faturamento = pedidos_no_mes.filter(status_pagamento='PAGO').aggregate(
            total=Sum('valor_total')
        )['total'] or 0

        # 2. Calcula as Despesas
        despesas = despesas_no_mes.aggregate(
            total=Sum('valor')
        )['total'] or 0

        # 3. Calcula o Valor a Receber (Pedidos com status 'PENDENTE' ou 'PARCIAL')
        a_receber = pedidos_no_mes.filter(
            Q(status_pagamento='PENDENTE') | Q(status_pagamento='PARCIAL')
        ).aggregate(
            total=Sum('valor_total')
        )['total'] or 0

        # 4. Calcula o Lucro
        lucro = faturamento - despesas

        # Monta o objeto de resposta
        data = {
            'faturamento': faturamento,
            'despesas': despesas,
            'lucro': lucro,
            'valor_a_receber': a_receber,
        }

        return Response(data)