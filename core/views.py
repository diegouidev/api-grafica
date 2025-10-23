from rest_framework import viewsets, status, filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Q, Value, CharField
from .models import Pedido, Despesa
import datetime
from django.http import HttpResponse
from django.template.loader import render_to_string
from weasyprint import HTML, CSS
from django.shortcuts import get_object_or_404
from rest_framework.permissions import AllowAny

from .models import (
    Cliente, Produto, Orcamento, ItemOrcamento, Pedido, ItemPedido, Pagamento, Empresa
)
from .serializers import (
    ClienteSerializer, ProdutoSerializer, OrcamentoSerializer,
    ItemOrcamentoSerializer, PedidoSerializer, ItemPedidoSerializer, PagamentoSerializer, DespesaConsolidadaSerializer, 
    DespesaSerializer, EmpresaSerializer, UserSerializer, ChangePasswordSerializer, EmpresaPublicaSerializer
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