from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Q
from .models import Pedido, Despesa
import datetime

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

    def get_queryset(self):
        """
        Este método agora retorna uma lista de orçamentos, excluindo
        aqueles que já foram aprovados.
        """
        # A MÁGICA ACONTECE AQUI:
        # Pegamos todos os orçamentos, ordenamos pelos mais recentes,
        # e então excluímos todos que tiverem o status 'Aprovado'.
        return Orcamento.objects.all().order_by('-data_criacao').exclude(status='Aprovado')

    # --- GARANTA QUE ESTE MÉTODO COMPLETO ESTÁ AQUI DENTRO ---
    @action(detail=True, methods=['post'], url_path='converter-para-pedido')
    def converter_para_pedido(self, request, pk=None):
        """
        Ação customizada para criar um Pedido a partir de um Orçamento.
        """
        orcamento = self.get_object()

        # Validação para não converter duas vezes
        if hasattr(orcamento, 'pedido'):
            return Response(
                {'error': 'Este orçamento já foi convertido em um pedido.'},
                status=status.HTTP_409_CONFLICT
            )

        # Criação do Pedido
        novo_pedido = Pedido.objects.create(
            cliente=orcamento.cliente,
            orcamento_origem=orcamento,
            valor_total=orcamento.valor_total,
            status_producao='Aguardando',
            status_pagamento='PENDENTE'
        )

        # Copiando os Itens do Orçamento para o Pedido
        itens_para_criar = [
            ItemPedido(
                pedido=novo_pedido,
                produto=item_orcamento.produto,
                quantidade=item_orcamento.quantidade,
                largura=item_orcamento.largura,
                altura=item_orcamento.altura,
                subtotal=item_orcamento.subtotal
            )
            for item_orcamento in orcamento.itens.all()
        ]
        ItemPedido.objects.bulk_create(itens_para_criar)

        # Atualiza o status do orçamento original
        orcamento.status = 'Aprovado'
        orcamento.save()

        # Retorna os dados do novo pedido criado
        # (Precisamos do PedidoSerializer para isso)
        
        serializer = PedidoSerializer(novo_pedido)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class ItemOrcamentoViewSet(viewsets.ModelViewSet):
    queryset = ItemOrcamento.objects.all()
    serializer_class = ItemOrcamentoSerializer


class PedidoViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API que permite aos pedidos serem visualizados ou editados.
    A lista é ordenada pelos pedidos mais recentes.
    """
    serializer_class = PedidoSerializer
    queryset = Pedido.objects.all().order_by('-data_criacao')

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