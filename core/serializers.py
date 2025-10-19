from rest_framework import serializers
# Importe os novos modelos
from .models import Cliente, Produto, Orcamento, ItemOrcamento, Pedido, ItemPedido, Pagamento, Despesa, Empresa
from django.db.models import Sum

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


class ProdutoResumidoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Produto
        fields = ['id', 'nome']


class ItemOrcamentoSerializer(serializers.ModelSerializer):

    produto = ProdutoResumidoSerializer(read_only=True)
    class Meta:
        model = ItemOrcamento
        fields = ['id', 'produto', 'quantidade', 'largura', 'altura', 'subtotal']


class ClienteResumidoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = ['id', 'nome']

class ItemOrcamentoWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemOrcamento
        fields = ['produto', 'quantidade', 'largura', 'altura']

class OrcamentoSerializer(serializers.ModelSerializer):
    cliente = ClienteResumidoSerializer(read_only=True)
    itens = ItemOrcamentoSerializer(many=True, read_only=True)
    
    itens_write = ItemOrcamentoWriteSerializer(many=True, write_only=True, source='itens', required=False)
    cliente_id = serializers.PrimaryKeyRelatedField(
        queryset=Cliente.objects.all(), source='cliente', write_only=True
    )

    class Meta:
        model = Orcamento
        fields = [
            'id', 'cliente', 'data_criacao', 'valor_total', 'status', 'itens',
            'cliente_id', 'itens_write'
        ]
        read_only_fields = ['valor_total']
    
    def create(self, validated_data):
        itens_data = validated_data.pop('itens')
        orcamento = Orcamento.objects.create(**validated_data)
        for item_data in itens_data:
            ItemOrcamento.objects.create(orcamento=orcamento, **item_data)
        orcamento.recalcular_total()
        return orcamento

    # --- A NOVA LÓGICA ESTÁ AQUI ---
    def update(self, instance, validated_data):
        itens_data = validated_data.pop('itens', None)

        # Atualiza os campos simples do Orçamento
        instance.status = validated_data.get('status', instance.status)
        if 'cliente' in validated_data:
            instance.cliente = validated_data.get('cliente', instance.cliente)
        instance.save()

        # Se o front-end enviou uma nova lista de itens, apaga os antigos e recria
        if itens_data is not None:
            instance.itens.all().delete()
            for item_data in itens_data:
                ItemOrcamento.objects.create(orcamento=instance, **item_data)
        
        # Sempre recalcula o total ao final da atualização
        instance.recalcular_total()

        return instance
    

class ItemPedidoSerializer(serializers.ModelSerializer):
    produto = ProdutoResumidoSerializer(read_only=True)
    class Meta:
        model = ItemPedido
        fields = ['id', 'produto', 'quantidade', 'largura', 'altura', 'subtotal']

class ItemPedidoWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemPedido
        fields = ['produto', 'quantidade', 'largura', 'altura']


class PagamentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pagamento
        fields = ['id', 'pedido', 'valor', 'data', 'forma_pagamento']

class PedidoSerializer(serializers.ModelSerializer):
    cliente = ClienteResumidoSerializer(read_only=True)
    itens = ItemPedidoSerializer(many=True, read_only=True)
    pagamentos = PagamentoSerializer(many=True, read_only=True)
    valor_pago = serializers.SerializerMethodField()
    valor_a_receber = serializers.SerializerMethodField()
    
    itens_write = ItemPedidoWriteSerializer(many=True, write_only=True, source='itens', required=False)
    cliente_id = serializers.PrimaryKeyRelatedField(
        queryset=Cliente.objects.all(), source='cliente', write_only=True, required=False
    )

    class Meta:
        model = Pedido
        fields = [
            'id', 'cliente', 'data_criacao', 'valor_total', 'status_producao', 'status_pagamento',
            'orcamento_origem', 'itens', 'pagamentos', 'custo_producao', 'valor_pago', 'valor_a_receber',
            'previsto_entrega', 'data_producao', 'forma_envio', 'codigo_rastreio', 'link_fornecedor',
            'itens_write', 'cliente_id'
        ]
        read_only_fields = ['valor_total']

    def get_valor_pago(self, obj):
        total_pago = obj.pagamentos.aggregate(total=Sum('valor'))['total']
        return total_pago or 0

    def get_valor_a_receber(self, obj):
        valor_pago = self.get_valor_pago(obj)
        return obj.valor_total - valor_pago
    
    # --- MÉTODO UPDATE CORRIGIDO E FINAL ---
    def update(self, instance, validated_data):
        """
        Método customizado que atualiza o Pedido e seus Itens.
        """
        itens_data = validated_data.pop('itens', None)

        # Atualiza todos os campos simples do Pedido (status, custo, etc.)
        # Esta abordagem é robusta e escala automaticamente com novos campos.
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Se o front-end enviou uma nova lista de itens...
        if itens_data is not None:
            instance.itens.all().delete() # Apaga os itens antigos
            for item_data in itens_data:
                ItemPedido.objects.create(pedido=instance, **item_data) # Recria com os novos
        
        # Sempre recalcula o valor total ao final, garantindo consistência
        instance.recalcular_total()

        return instance
    

class DespesaSerializer(serializers.ModelSerializer):
    """
    Serializer para o modelo de Despesas Gerais.
    """
    class Meta:
        model = Despesa
        fields = ['id', 'descricao', 'valor', 'data', 'categoria']


class DespesaConsolidadaSerializer(serializers.Serializer):
    """
    Este é um serializer que não está ligado a um modelo.
    Ele apenas define a estrutura dos dados que nossa view customizada irá retornar.
    """
    id = serializers.CharField(read_only=True)
    descricao = serializers.CharField()
    valor = serializers.DecimalField(max_digits=10, decimal_places=2)
    data = serializers.DateField()
    categoria = serializers.CharField(allow_null=True)
    tipo = serializers.CharField()


class EmpresaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Empresa
        fields = '__all__' # Inclui todos os campos do modelo