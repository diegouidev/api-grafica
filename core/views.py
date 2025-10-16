from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Q, Value, CharField
from .models import Pedido, Despesa
import datetime

from .models import (
    Cliente, Produto, Orcamento, ItemOrcamento, Pedido, ItemPedido, Pagamento
)
from .serializers import (
    ClienteSerializer, ProdutoSerializer, OrcamentoSerializer,
    ItemOrcamentoSerializer, PedidoSerializer, ItemPedidoSerializer, PagamentoSerializer, DespesaConsolidadaSerializer, DespesaSerializer
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


class DespesaViewSet(viewsets.ModelViewSet):
    queryset = Despesa.objects.all().order_by('-data')
    serializer_class = DespesaSerializer

# --- VIEW CUSTOMIZADA PARA LISTAGEM UNIFICADA ---
class DespesaConsolidadaView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, *args, **kwargs):
        despesas_gerais = Despesa.objects.annotate(tipo=Value('Geral', output_field=CharField())).values('id', 'descricao', 'valor', 'data', 'categoria', 'tipo')
        custos_producao = Pedido.objects.filter(custo_producao__gt=0).annotate(tipo=Value('Produção', output_field=CharField())).values('id', 'custo_producao', 'data_criacao', 'tipo', 'cliente__nome')
        custos_formatados = [{'id': f"p_{custo['id']}", 'descricao': f"Custo do Pedido #{custo['id']} ({custo['cliente__nome']})", 'valor': custo['custo_producao'], 'data': custo['data_criacao'].date(), 'categoria': 'Custo de Produção', 'tipo': custo['tipo']} for custo in custos_producao]
        lista_combinada = sorted(list(despesas_gerais) + custos_formatados, key=lambda x: x['data'], reverse=True)
        serializer = DespesaConsolidadaSerializer(lista_combinada, many=True)
        return Response(serializer.data)


class DashboardStatsView(APIView):
    """
    View para fornecer estatísticas agregadas e dinâmicas para o dashboard.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # --- PERÍODO DE ANÁLISE (MÊS ATUAL) ---
        today = datetime.date.today()
        start_of_month = today.replace(day=1)

        # Filtra os pedidos e despesas pelo mês atual
        pedidos_no_mes = Pedido.objects.filter(data_criacao__gte=start_of_month)
        despesas_gerais_no_mes = Despesa.objects.filter(data__gte=start_of_month)

        # 1. FATURAMENTO: Soma do valor_total de TODOS os pedidos criados no mês.
        faturamento = pedidos_no_mes.aggregate(total=Sum('valor_total'))['total'] or 0

        # 2. DESPESAS TOTAIS: Soma das despesas gerais + custo de produção dos pedidos do mês.
        despesas_operacionais = despesas_gerais_no_mes.aggregate(total=Sum('valor'))['total'] or 0
        custo_producao_pedidos = pedidos_no_mes.aggregate(total=Sum('custo_producao'))['total'] or 0
        despesas_totais = despesas_operacionais + custo_producao_pedidos
        
        # 3. LUCRO BRUTO: Faturamento do mês menos o custo de produção dos pedidos do mês.
        lucro = faturamento - custo_producao_pedidos

        # --- CÁLCULOS GLOBAIS (NÃO DEPENDEM DO MÊS) ---

        # 4. VALOR A RECEBER: Soma de todos os saldos devedores de pedidos PENDENTES ou PARCIAIS.
        pedidos_nao_quitados = Pedido.objects.filter(
            Q(status_pagamento='PENDENTE') | Q(status_pagamento='PARCIAL')
        )
        total_devido = pedidos_nao_quitados.aggregate(total=Sum('valor_total'))['total'] or 0
        total_pago_parcialmente = Pagamento.objects.filter(pedido__in=pedidos_nao_quitados).aggregate(total=Sum('valor'))['total'] or 0
        a_receber = total_devido - total_pago_parcialmente

        # Monta o objeto de resposta final
        data = {
            'faturamento': faturamento,
            'despesas': despesas_totais,
            'lucro': lucro,
            'valor_a_receber': a_receber,
        }

        return Response(data)
    


class PagamentoViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API para gerenciar pagamentos.
    Atualiza automaticamente o status do pedido relacionado após a criação de um pagamento.
    """
    queryset = Pagamento.objects.all()
    serializer_class = PagamentoSerializer

    def perform_create(self, serializer):
        """
        Método customizado que é executado ao criar um novo pagamento.
        """
        # 1. Salva a instância do novo pagamento no banco de dados.
        pagamento = serializer.save()

        # 2. Pega o pedido que está associado a este pagamento.
        pedido = pagamento.pedido

        # 3. Calcula a soma de TODOS os pagamentos para este pedido.
        total_pago = pedido.pagamentos.aggregate(total=Sum('valor'))['total'] or 0

        # 4. A LÓGICA DE NEGÓCIO:
        # Compara o total pago com o valor total do pedido.
        if total_pago >= pedido.valor_total:
            # Se o valor foi quitado (ou ultrapassado), marca o pedido como PAGO.
            pedido.status_pagamento = Pedido.StatusPagamento.PAGO
        else:
            # Se ainda falta pagar, marca como PARCIAL.
            pedido.status_pagamento = Pedido.StatusPagamento.PARCIAL
        
        # 5. Salva a alteração do status no pedido.
        pedido.save()


class VendasRecentesView(APIView):
    """
    View customizada que retorna os 5 pedidos mais recentes.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # 1. Busca todos os pedidos no banco de dados
        # 2. Ordena pelos mais recentes (data de criação decrescente)
        # 3. Pega apenas os 5 primeiros resultados
        ultimos_pedidos = Pedido.objects.all().order_by('-data_criacao')[:5]
        
        # 4. Usa o PedidoSerializer que já temos para formatar os dados
        serializer = PedidoSerializer(ultimos_pedidos, many=True)
        
        # 5. Retorna os dados formatados
        return Response(serializer.data)
    

class FaturamentoPorPagamentoView(APIView):
    """
    View customizada que retorna o faturamento total do mês,
    agrupado por forma de pagamento.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        today = datetime.date.today()
        start_of_month = today.replace(day=1)

        # 1. Busca todos os pagamentos do mês atual
        # 2. Usa .values() para agrupar por 'forma_pagamento'
        # 3. Usa .annotate() para criar um novo campo 'total' com a soma dos valores de cada grupo
        # 4. Ordena do maior para o menor total
        faturamento_agrupado = Pagamento.objects.filter(data__gte=start_of_month)\
            .values('forma_pagamento')\
            .annotate(total=Sum('valor'))\
            .order_by('-total')

        return Response(faturamento_agrupado)