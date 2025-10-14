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
    """
    queryset = Produto.objects.all().order_by('nome')
    serializer_class = ProdutoSerializer


class OrcamentoViewSet(viewsets.ModelViewSet):
    queryset = Orcamento.objects.all()
    serializer_class = OrcamentoSerializer

    
    @action(detail=True, methods=['post'], url_path='converter-para-pedido')
    def converter_para_pedido(self, request, pk=None):
        """
        Ação customizada para criar um Pedido a partir de um Orçamento.
        """
        orcamento = self.get_object()

        # 1. Validação: Verificar se já não existe um pedido para este orçamento
        if hasattr(orcamento, 'pedido'):
            return Response(
                {'error': 'Este orçamento já foi convertido em um pedido.'},
                status=status.HTTP_409_CONFLICT
            )

        # 2. Criação do Pedido
        novo_pedido = Pedido.objects.create(
            cliente=orcamento.cliente,
            orcamento_origem=orcamento,
            valor_total=orcamento.valor_total,
            # Você pode definir status iniciais aqui
            status_producao='Aguardando',
            status_pagamento='PENDENTE'
        )

        # 3. Criação dos Itens do Pedido (copiando dos itens do orçamento)
        itens_para_criar = []
        for item_orcamento in orcamento.itens.all():
            itens_para_criar.append(
                ItemPedido(
                    pedido=novo_pedido,
                    produto=item_orcamento.produto,
                    quantidade=item_orcamento.quantidade,
                    largura=item_orcamento.largura,
                    altura=item_orcamento.altura,
                    subtotal=item_orcamento.subtotal
                )
            )
        
        ItemPedido.objects.bulk_create(itens_para_criar)

        # 4. (Opcional) Atualizar o status do orçamento
        orcamento.status = 'Aprovado'
        orcamento.save()

        # 5. Retornar a resposta com os dados do novo pedido
        serializer = PedidoSerializer(novo_pedido)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

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