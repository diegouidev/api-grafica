from rest_framework import viewsets, status, filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Pedido, Despesa
from django.db import transaction
import datetime
from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML, CSS
from django.shortcuts import get_object_or_404
from rest_framework.permissions import AllowAny
from django.db.models import Avg, Sum, Q, Value, CharField, Max, F, ExpressionWrapper, fields, Count, DecimalField, Case, When
from django.utils import timezone
from django.db.models.functions import TruncMonth, Coalesce

from .models import (
    Cliente, Produto, Orcamento, ItemOrcamento, Pedido, ItemPedido, Pagamento, Empresa
)
from .serializers import (
    ClienteSerializer, ProdutoSerializer, OrcamentoSerializer,
    ItemOrcamentoSerializer, PedidoSerializer, ItemPedidoSerializer, PagamentoSerializer, DespesaConsolidadaSerializer, 
    DespesaSerializer, EmpresaSerializer, UserSerializer, ChangePasswordSerializer, EmpresaPublicaSerializer, RelatorioClienteSerializer,
    RelatorioPedidosAtrasadosSerializer, FormaPagamentoAgrupadoSerializer, StatusOrcamentoAgrupadoSerializer, 
    ProdutosOrcadosAgrupadoSerializer, RelatorioOrcamentoRecenteSerializer, RelatorioProdutoVendidoSerializer,
    RelatorioProdutoLucrativoSerializer, RelatorioProdutoBaixaDemandaSerializer
)
from django.contrib.auth.models import User
from django.utils.timezone import now
from django.db.models.functions import TruncMonth
from django.db.models import Count


class ClienteViewSet(viewsets.ModelViewSet):
    queryset = Cliente.objects.all().order_by('-data_cadastro')
    serializer_class = ClienteSerializer
    
    # --- A MÁGICA ESTÁ AQUI ---
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    # Define os campos pelos quais podemos fazer uma busca textual
    search_fields = ['nome', 'cpf_cnpj', 'email']

class ProdutoViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API que permite aos produtos serem visualizados ou editados.
    Permite filtrar por tipo_precificacao (ex: /api/produtos/?tipo_precificacao=M2)
    """
    serializer_class = ProdutoSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['nome']

    def get_queryset(self):
        queryset = Produto.objects.all().order_by('nome')
        tipo = self.request.query_params.get('tipo_precificacao')
        if tipo is not None:
            queryset = queryset.filter(tipo_precificacao=tipo)
        return queryset


class OrcamentoViewSet(viewsets.ModelViewSet):
    queryset = Orcamento.objects.all().order_by('-data_criacao')
    serializer_class = OrcamentoSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['cliente__nome', 'id']

    def get_queryset(self):
        """
        Retorna os orçamentos mais recentes, excluindo os já aprovados.
        """
        return (
            Orcamento.objects
            .all()
            .order_by('-data_criacao')
            .exclude(status='Aprovado')
        )

    # ---------------------------------------------------------
    # Métodos ajustados para exibir erros de validação no terminal
    # ---------------------------------------------------------
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            print("\n❌ ERRO AO CRIAR ORÇAMENTO:")
            print(serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if not serializer.is_valid():
            print("\n❌ ERRO AO EDITAR ORÇAMENTO:")
            print(serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        self.perform_update(serializer)
        return Response(serializer.data)

    # ---------------------------------------------------------
    # Conversão de orçamento em pedido
    # ---------------------------------------------------------
    @action(detail=True, methods=['post'], url_path='converter-para-pedido')
    def converter_para_pedido(self, request, pk=None):
        """
        Cria um Pedido a partir deste Orçamento, copiando inclusive
        a descricao_customizada de cada item.
        """
        orcamento = self.get_object()

        # Evita conversão duplicada: OneToOneField cria o reverse accessor "pedido"
        if hasattr(orcamento, 'pedido'):
            return Response(
                {'error': 'Este orçamento já foi convertido em um pedido.'},
                status=status.HTTP_409_CONFLICT
            )

        itens_orc = list(orcamento.itens.all())
        if not itens_orc:
            return Response(
                {'error': 'Este orçamento não possui itens para converter.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            novo_pedido = Pedido.objects.create(
                cliente=orcamento.cliente,
                orcamento_origem=orcamento,
                valor_total=0,  # será recalculado depois
                status_producao='Aguardando',
                status_pagamento=Pedido.StatusPagamento.PENDENTE,
            )

            itens_para_criar = []
            for io in itens_orc:
                itens_para_criar.append(
                    ItemPedido(
                        pedido=novo_pedido,
                        produto=io.produto,  # pode ser None se for item manual
                        quantidade=io.quantidade,
                        largura=io.largura,
                        altura=io.altura,
                        descricao_customizada=io.descricao_customizada,
                        subtotal=io.subtotal,
                    )
                )

            ItemPedido.objects.bulk_create(itens_para_criar)

            # Atualiza status do orçamento e recalcula total do pedido
            orcamento.status = 'Aprovado'
            orcamento.save(update_fields=['status'])

            if hasattr(novo_pedido, 'recalcular_total'):
                novo_pedido.recalcular_total()

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
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['cliente__nome', 'id']

class ItemPedidoViewSet(viewsets.ModelViewSet):
    queryset = ItemPedido.objects.all()
    serializer_class = ItemPedidoSerializer


class DespesaViewSet(viewsets.ModelViewSet):
    queryset = Despesa.objects.all().order_by('-data')
    serializer_class = DespesaSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    search_fields = ['descricao', 'categoria']

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
    


class RelatorioFaturamentoView(APIView):
    """
    View para gerar e retornar um relatório de faturamento em PDF.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        data_inicio_str = request.query_params.get('data_inicio')
        data_fim_str = request.query_params.get('data_fim')

        if not data_inicio_str or not data_fim_str:
            return Response(
                {'error': 'As datas de início e fim são obrigatórias.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        data_inicio = datetime.datetime.strptime(data_inicio_str, '%Y-%m-%d').date()
        data_fim = datetime.datetime.strptime(data_fim_str, '%Y-%m-%d').date()

        # Busca os pedidos pagos dentro do período especificado
        pedidos = Pedido.objects.filter(
            data_criacao__date__range=[data_inicio, data_fim],
            status_pagamento='PAGO'
        ).order_by('data_criacao')

        # Calcula o total
        total_faturado = pedidos.aggregate(total=Sum('valor_total'))['total'] or 0

        # Prepara o contexto para o template HTML
        context = {
            'pedidos': pedidos,
            'total_faturado': total_faturado,
            'data_inicio': data_inicio.strftime('%d/%m/%Y'),
            'data_fim': data_fim.strftime('%d/%m/%Y'),
        }

        # Renderiza o template HTML como uma string
        html_string = render_to_string('relatorios/faturamento.html', context)
        
        # Gera o PDF a partir do HTML
        pdf = HTML(string=html_string).write_pdf()

        # Cria a resposta HTTP com o conteúdo do PDF
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="relatorio_faturamento_{data_inicio_str}_a_{data_fim_str}.pdf"'
        
        return response
    

class OrcamentoPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        orcamento = get_object_or_404(Orcamento, pk=pk)
        empresa = Empresa.objects.first()

        logo_url = None
        if empresa and empresa.logo_orcamento_pdf:
            logo_url = request.build_absolute_uri(empresa.logo_orcamento_pdf.url)
        
        # --- A LÓGICA DE CÁLCULO ESTÁ AQUI ---
        itens = orcamento.itens.all()
        for item in itens:
            # Calcula o valor unitário em Python e o anexa ao objeto do item
            if item.quantidade > 0:
                item.valor_unitario = item.subtotal / item.quantidade
            else:
                item.valor_unitario = 0
        
        context = {
            'orcamento': orcamento,
            'itens': itens, # Passa a lista de itens já modificada para o template
            'empresa': empresa, # Adiciona os dados da empresa ao contexto
            'logo_url': logo_url
        }
        
        html_string = render_to_string('documentos/orcamento_pdf.html', context)
        pdf = HTML(string=html_string).write_pdf()
        
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="orcamento_{pk}.pdf"'
        return response

class PedidoPDFView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, *args, **kwargs):
        pedido = get_object_or_404(Pedido, pk=pk)
        empresa = Empresa.objects.first()

        logo_url = None
        if empresa and empresa.logo_orcamento_pdf:
            logo_url = request.build_absolute_uri(empresa.logo_orcamento_pdf.url)

        # --- A LÓGICA DE CÁLCULO ESTÁ AQUI ---
        itens = pedido.itens.all()
        for item in itens:
            if item.quantidade > 0:
                item.valor_unitario = item.subtotal / item.quantidade
            else:
                item.valor_unitario = 0

        context = {
            'pedido': pedido,
            'itens': itens,
            'empresa': empresa,
            'logo_url': logo_url
        }

        html_string = render_to_string('documentos/pedido_os_pdf.html', context)
        pdf = HTML(string=html_string).write_pdf()
        
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="pedido_os_{pk}.pdf"'
        return response
    

class EmpresaSettingsView(APIView):
    """
    View para buscar e atualizar as configurações da empresa (Singleton).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # Tenta pegar a primeira (e única) instância, ou cria uma se não existir
        empresa, created = Empresa.objects.get_or_create(pk=1)
        serializer = EmpresaSerializer(empresa)
        return Response(serializer.data)

    def put(self, request, *args, **kwargs):
        empresa, created = Empresa.objects.get_or_create(pk=1)
        serializer = EmpresaSerializer(empresa, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

class UserProfileView(APIView):
    """
    View para o usuário logado ver e atualizar seu próprio perfil.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # 'request.user' é o usuário logado (graças ao token)
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    def put(self, request, *args, **kwargs):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class ChangePasswordView(APIView):
    """
    View para o usuário logado alterar sua senha.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = ChangePasswordSerializer(data=request.data)
        if serializer.is_valid():
            user = request.user
            old_password = serializer.validated_data['old_password']
            new_password = serializer.validated_data['new_password']

            if not user.check_password(old_password):
                return Response({"old_password": ["Senha antiga está incorreta."]}, status=status.HTTP_400_BAD_REQUEST)
            
            user.set_password(new_password)
            user.save()
            return Response({"status": "senha alterada com sucesso"}, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

class EmpresaPublicaView(APIView):
    """
    View PÚBLICA (sem autenticação) para buscar dados básicos da empresa,
    como a logo para a tela de login.
    """
    permission_classes = [AllowAny] # Permite o acesso sem token

    def get(self, request, *args, **kwargs):
        empresa, created = Empresa.objects.get_or_create(pk=1)
        serializer = EmpresaPublicaSerializer(empresa)
        return Response(serializer.data)
    

class EvolucaoVendasView(APIView):
    """
    Retorna a receita dos últimos 6 meses para o gráfico de evolução.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        seis_meses_atras = now().date().replace(day=1) - datetime.timedelta(days=30*5)
        
        vendas = Pedido.objects.filter(
            data_criacao__gte=seis_meses_atras,
            status_pagamento='PAGO'
        ).annotate(
            mes=TruncMonth('data_criacao') # Agrupa por mês
        ).values('mes').annotate(
            total=Sum('valor_total') # Soma o total para cada mês
        ).order_by('mes')
        
        # Formata os dados para o gráfico
        data_formatada = [
            {"name": item['mes'].strftime('%b/%y'), "Receita": item['total']}
            for item in vendas
        ]
        return Response(data_formatada)

class PedidosPorStatusView(APIView):
    """
    Retorna a contagem de pedidos agrupados por status de produção.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        status_counts = Pedido.objects.values('status_producao').annotate(
            value=Count('id')
        ).order_by('-value') # Ordena pelos status mais comuns
        
        # Renomeia a chave para o gráfico
        data_formatada = [
            {"name": item['status_producao'], "value": item['value']}
            for item in status_counts
        ]
        return Response(data_formatada)
    

class ProdutosMaisVendidosView(APIView):
    """
    Retorna os 5 produtos mais vendidos (em quantidade) do mês atual.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        today = datetime.date.today()
        start_of_month = today.replace(day=1)

        # Agrupa os itens de PEDIDOS por produto, soma as quantidades
        # e ordena pela maior quantidade
        produtos = ItemPedido.objects.filter(pedido__data_criacao__gte=start_of_month)\
            .values('produto__nome')\
            .annotate(total_vendido=Sum('quantidade'))\
            .order_by('-total_vendido')[:5] # Pega os Top 5

        # Formata os dados para o gráfico de barras
        data_formatada = [
            {"name": item['produto__nome'], "value": item['total_vendido']}
            for item in produtos
        ]
        return Response(data_formatada)

class ClientesMaisAtivosView(APIView):
    """
    Retorna os 5 clientes que mais geraram faturamento (valor total em pedidos).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # Agrupa os PEDIDOS por cliente, soma o valor total de cada cliente
        # e ordena pelo maior valor
        clientes = Pedido.objects.values('cliente__nome')\
            .annotate(
                total_gasto=Sum('valor_total'),
                total_pedidos=Count('id')
            )\
            .order_by('-total_gasto')[:5] # Pega os Top 5

        # Formata os dados para a lista
        data_formatada = [
            {
                "name": item['cliente__nome'],
                "total_pedidos": item['total_pedidos'],
                "total_gasto": item['total_gasto']
            }
            for item in clientes
        ]
        return Response(data_formatada)
    

class RelatorioClientesView(APIView):
    """
    View para fornecer dados agregados para a aba de relatórios de clientes.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        hoje = timezone.now().date()
        data_30_dias_atras = hoje - datetime.timedelta(days=30)
        data_90_dias_atras = hoje - datetime.timedelta(days=90)

        # 1. Total de Clientes
        total_clientes = Cliente.objects.count()

        # 2. Novos Clientes (cadastrados nos últimos 30 dias)
        novos_clientes_30d = Cliente.objects.filter(data_cadastro__gte=data_30_dias_atras).count()

        # 3. Clientes Ativos (com pedidos nos últimos 90 dias)
        clientes_ativos_ids = Pedido.objects.filter(
            data_criacao__gte=data_90_dias_atras
        ).values_list('cliente_id', flat=True).distinct()
        clientes_ativos_90d = len(clientes_ativos_ids)
        
        # 4. Clientes Inativos (sem pedidos nos últimos 90 dias)
        clientes_inativos = Cliente.objects.exclude(id__in=clientes_ativos_ids).annotate(
            total_gasto=Coalesce(Sum('pedidos__valor_total'), 0.0, output_field=DecimalField()),
            ultimo_pedido=Max('pedidos__data_criacao__date'),
            dias_inativo=ExpressionWrapper(
                hoje - F('ultimo_pedido'),
                output_field=fields.IntegerField()
            )
        ).order_by('-total_gasto')

        # Serializa a lista de inativos
        inativos_serializer = RelatorioClienteSerializer(clientes_inativos, many=True)

        # Monta o objeto de resposta final
        data = {
            'total_clientes': total_clientes,
            'novos_clientes_30d': novos_clientes_30d,
            'clientes_ativos_90d': clientes_ativos_90d,
            'clientes_inativos_90d': clientes_inativos.count(),
            'lista_inativos': inativos_serializer.data
        }
        
        return Response(data)
    

class RelatorioPedidosView(APIView):
    """
    Fornece todos os dados agregados para a aba de relatórios de pedidos.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        hoje = timezone.now().date()
        
        # 1. Total de Pedidos
        total_pedidos = Pedido.objects.count()

        # 2. Pedidos Atrasados (count e lista)
        pedidos_atrasados_query = Pedido.objects.filter(
            previsto_entrega__lt=hoje,
            status_producao__in=['Aguardando', 'Aguardando Arte', 'Em Produção']
        ).annotate(
            dias_atraso=ExpressionWrapper(
                hoje - F('previsto_entrega'),
                output_field=fields.DurationField()
            )
        )
        pedidos_atrasados_count = pedidos_atrasados_query.count()
        lista_atrasados = RelatorioPedidosAtrasadosSerializer(pedidos_atrasados_query, many=True).data

        # 3. Lucro Médio por Pedido
        lucro_medio = Pedido.objects.filter(status_pagamento='PAGO').aggregate(
            lucro_avg=Avg(F('valor_total') - F('custo_producao'))
        )['lucro_avg'] or 0

        # 4. Tempo Médio de Produção (calcula de 'criado' até 'finalizado')
        pedidos_finalizados = Pedido.objects.filter(status_producao='Finalizado')
        tempo_medio = pedidos_finalizados.annotate(
            tempo_producao=ExpressionWrapper(F('data_producao') - F('data_criacao'), output_field=fields.DurationField())
        ).aggregate(
            avg_tempo=Avg('tempo_producao')
        )['avg_tempo']
        
        # 5. Pedidos por Forma de Pagamento (CONTAGEM de pagamentos)
        pedidos_por_pagamento = Pagamento.objects.values('forma_pagamento').annotate(
            value=Count('id')
        ).order_by('-value')
        pedidos_por_pagamento_data = FormaPagamentoAgrupadoSerializer(pedidos_por_pagamento, many=True).data

        # Monta o objeto de resposta final
        data = {
            'total_pedidos': total_pedidos,
            'pedidos_atrasados_count': pedidos_atrasados_count,
            'lucro_medio_pedido': lucro_medio,
            'tempo_medio_producao_dias': tempo_medio.days if tempo_medio else 0,
            'lista_pedidos_atrasados': lista_atrasados,
            'pedidos_por_forma_pagamento': pedidos_por_pagamento_data,
        }
        
        return Response(data)


class RelatorioOrcamentosView(APIView):
    """
    Fornece todos os dados agregados para a aba de relatórios de orçamentos.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        orcamentos = Orcamento.objects.all()
        
        # --- 1. Cálculos para os Cards ---
        total_orcamentos = orcamentos.count()
        aprovados = orcamentos.filter(status='Aprovado').count()
        recusados = orcamentos.filter(status='Rejeitado').count()
        pendentes = orcamentos.filter(status='Em Aberto').count()
        
        taxa_conversao = (aprovados / total_orcamentos * 100) if total_orcamentos > 0 else 0
        
        valor_total_orcado = orcamentos.aggregate(total=Sum('valor_total'))['total'] or 0
        valor_total_aprovado = orcamentos.filter(status='Aprovado').aggregate(total=Sum('valor_total'))['total'] or 0
        
        # --- 2. Dados para o Gráfico de Pizza (Status) ---
        status_data = orcamentos.values('status').annotate(value=Count('id'))
        status_serializer = StatusOrcamentoAgrupadoSerializer(status_data, many=True)

        # --- 3. Dados para o Gráfico de Barras (Top Produtos Orçados) ---
        produtos_data = ItemOrcamento.objects.values('produto__nome').annotate(value=Count('id')).order_by('-value')[:5]
        produtos_serializer = ProdutosOrcadosAgrupadoSerializer(produtos_data, many=True)
        
        # --- 4. Dados para a Tabela (Orçamentos Recentes) ---
        recentes_data = orcamentos.order_by('-data_criacao')[:6]
        recentes_serializer = RelatorioOrcamentoRecenteSerializer(recentes_data, many=True)
        
        # Monta o objeto de resposta final
        data = {
            'cards': {
                'total_orcamentos': total_orcamentos,
                'taxa_conversao': taxa_conversao,
                'tempo_medio_resposta': "1.8 dias", # Valor estático por enquanto
                'valor_total_orcado': valor_total_orcado,
                'valor_total_aprovado': valor_total_aprovado,
                'aprovados_count': aprovados,
                'recusados_count': recusados,
            },
            'grafico_status': status_serializer.data,
            'grafico_produtos': produtos_serializer.data,
            'tabela_recentes': recentes_serializer.data,
        }
        
        return Response(data)
    

class RelatorioProdutosView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request, *args, **kwargs):
        hoje = timezone.now().date()
        data_60_dias_atras = hoje - datetime.timedelta(days=60)
        start_of_month = hoje.replace(day=1)

        agregados_produto = Produto.objects.aggregate(
            total_produtos=Count('id'),
            custo_medio=Avg('custo'),
            preco_medio=Avg('preco')
        )
        alertas_estoque = Produto.objects.filter(
            estoque_atual__isnull=False, 
            estoque_minimo__gt=0, 
            estoque_atual__lt=F('estoque_minimo')
        ).count()
        cards_data = {
            "total_produtos": agregados_produto['total_produtos'] or 0,
            "custo_medio": agregados_produto['custo_medio'] or 0,
            "preco_medio_venda": agregados_produto['preco_medio'] or 0,
            "alertas_estoque": alertas_estoque,
        }

        produtos_vendidos = ItemPedido.objects.filter(pedido__data_criacao__gte=start_of_month)\
            .values('produto__nome')\
            .annotate(total_vendido=Sum('quantidade'))\
            .order_by('-total_vendido')[:5]
        grafico_vendidos_serializer = RelatorioProdutoVendidoSerializer(produtos_vendidos, many=True)

        produtos_lucrativos = ItemPedido.objects.filter(produto__custo__gt=0, produto__preco__gt=0)\
            .values('produto__nome')\
            .annotate(
                total_lucro=Sum(F('subtotal') - (F('produto__custo') * F('quantidade'))),
                receita_total=Sum('subtotal'),
                custo_total=Sum(F('produto__custo') * F('quantidade'))
            )\
            .annotate(
                # AQUI ESTÁ A CORREÇÃO:
                # Dizemos ao Coalesce para usar um DecimalField com valor 0.0
                margem=Case(
                    When(receita_total=0, then=Value(0.0, output_field=DecimalField())),
                    default=ExpressionWrapper(
                        (F('receita_total') - F('custo_total')) * 100.0 / F('receita_total'),
                        output_field=DecimalField()
                    )
                )
            )\
            .order_by('-total_lucro')[:6]
        lucrativos_serializer = RelatorioProdutoLucrativoSerializer(produtos_lucrativos, many=True)
        
        produtos_baixa_demanda = Produto.objects.annotate(
            ultima_venda=Max('itempedido__pedido__data_criacao__date')
        ).filter(
            Q(ultima_venda__lt=data_60_dias_atras) | Q(ultima_venda__isnull=True)
        ).annotate(
            dias_sem_venda=ExpressionWrapper(
                hoje - F('ultima_venda'),
                output_field=fields.DurationField()
            )
        ).order_by('ultima_venda')[:6]
        baixa_demanda_serializer = RelatorioProdutoBaixaDemandaSerializer(produtos_baixa_demanda, many=True)

        data = {
            'cards': cards_data,
            'grafico_mais_vendidos': grafico_vendidos_serializer.data,
            'lista_mais_lucrativos': lucrativos_serializer.data,
            'tabela_baixa_demanda': baixa_demanda_serializer.data,
        }
        return Response(data)