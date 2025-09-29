from rest_framework import serializers
# Importe os novos modelos
from .models import Cliente, Produto, Orcamento, ItemOrcamento, Pedido, ItemPedido

class ClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = [
            'id', 'nome', 'email', 'telefone', 'cpf_cnpj', 
            'observacao', 'cep', 'endereco', 'numero', 'bairro', 'cidade', 'estado',
            'data_cadastro'
        ]
        read_only_fields = ['data_cadastro']

    def validate_cpf_cnpj(self, value):
        """
        Verifica se o CPF/CNPJ já existe no banco de dados,
        ignorando o próprio objeto em caso de atualização.
        """
        # Se o valor for vazio ou nulo, não fazemos a validação
        if not value:
            return value

        # Checa se existe outro cliente com o mesmo cpf_cnpj
        query = Cliente.objects.filter(cpf_cnpj=value)

        # Se estivermos atualizando um cliente (self.instance existe),
        # excluímos o próprio cliente da busca para permitir salvar sem alterar o cpf_cnpj.
        if self.instance:
            query = query.exclude(pk=self.instance.pk)

        if query.exists():
            raise serializers.ValidationError("Já existe um cliente cadastrado com este CPF/CNPJ.")

        return value

class ProdutoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Produto
        fields = ['id', 'nome', 'tipo_precificacao', 'preco']

# --- Adicione o código abaixo ---

class ItemOrcamentoSerializer(serializers.ModelSerializer):
    """
    Serializer para um item dentro de um orçamento.
    """
    class Meta:
        model = ItemOrcamento
        fields = [
            'id',
            'orcamento',
            'produto',
            'quantidade',
            'largura',
            'altura',
            'subtotal'
        ]
        # O subtotal não deve ser enviado pelo usuário, será calculado no back-end.
        read_only_fields = ['subtotal']

class OrcamentoSerializer(serializers.ModelSerializer):
    """
    Serializer para o Orçamento, que incluirá uma lista dos seus itens.
    """
    # Usamos o 'ItemOrcamentoSerializer' para exibir os itens de forma aninhada.
    # 'many=True' indica que pode haver múltiplos itens.
    # 'read_only=True' significa que não criaremos itens por aqui, apenas os exibiremos.
    itens = ItemOrcamentoSerializer(many=True, read_only=True)

    class Meta:
        model = Orcamento
        fields = [
            'id',
            'cliente',
            'data_criacao',
            'valor_total',
            'status',
            'itens' # Adicionamos o campo aninhado aqui
        ]
        # O valor_total também será calculado automaticamente.
        read_only_fields = ['valor_total']


class ItemPedidoSerializer(serializers.ModelSerializer):
    """ Serializer para um item dentro de um pedido. """
    class Meta:
        model = ItemPedido
        fields = [
            'id',
            'produto',
            'quantidade',
            'largura',
            'altura',
            'subtotal'
        ]

class PedidoSerializer(serializers.ModelSerializer):
    """ Serializer para o Pedido, que incluirá uma lista dos seus itens. """
    itens = ItemPedidoSerializer(many=True, read_only=True)

    class Meta:
        model = Pedido
        fields = [
            'id',
            'cliente',
            'orcamento_origem',
            'data_criacao',
            'valor_total',
            'status_producao',
            'status_pagamento',
            'itens'
        ]
