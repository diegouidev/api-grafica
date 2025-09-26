from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
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
    queryset = Cliente.objects.all().order_by('nome')
    serializer_class = ClienteSerializer

# --- Adicione o código abaixo ---

class ProdutoViewSet(viewsets.ModelViewSet):
    """
    Endpoint da API que permite aos produtos serem visualizados ou editados.
    """
    queryset = Produto.objects.all().order_by('nome')
    serializer_class = ProdutoSerializer


class OrcamentoViewSet(viewsets.ModelViewSet):
    queryset = Orcamento.objects.all()
    serializer_class = OrcamentoSerializer

    # --- Adicione o método abaixo ---
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