from rest_framework import serializers
from django.db.models import Sum
from django.contrib.auth.models import User
from .models import Cliente, Produto, Orcamento, ItemOrcamento, Pedido, ItemPedido, Pagamento, Despesa, Empresa

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
        read_only_fields = ['id', 'username']

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)

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
        if not value:
            return value
        query = Cliente.objects.filter(cpf_cnpj=value)
        if self.instance:
            query = query.exclude(pk=self.instance.pk)
        if query.exists():
            raise serializers.ValidationError("Já existe um cliente cadastrado com este CPF/CNPJ.")
        return value

class ProdutoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Produto
        fields = ['id', 'nome', 'tipo_precificacao', 'preco', 'custo', 'estoque_atual', 'estoque_minimo']

class ProdutoResumidoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Produto
        fields = ['id', 'nome']

# ---------- ITENS DE ORÇAMENTO ----------
class ItemOrcamentoSerializer(serializers.ModelSerializer):
    produto = ProdutoResumidoSerializer(read_only=True)
    nome_exibido = serializers.SerializerMethodField()

    class Meta:
        model = ItemOrcamento
        fields = ['id', 'produto', 'quantidade', 'largura', 'altura', 'descricao_customizada', 'subtotal', 'nome_exibido']

    def get_nome_exibido(self, obj):
        return obj.descricao_customizada or (obj.produto.nome if obj.produto else 'Item')

class ItemOrcamentoWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemOrcamento
        fields = ['produto', 'quantidade', 'largura', 'altura', 'descricao_customizada', 'subtotal']
        extra_kwargs = {'subtotal': {'required': False}}

    produto = serializers.PrimaryKeyRelatedField(
        queryset=Produto.objects.all(),
        required=False,
        allow_null=True   
    )

# ---------- ORÇAMENTO ----------
class ClienteResumidoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = ['id', 'nome']

class OrcamentoSerializer(serializers.ModelSerializer):
    cliente = ClienteResumidoSerializer(read_only=True)
    itens = ItemOrcamentoSerializer(many=True, read_only=True)

    itens_write = ItemOrcamentoWriteSerializer(many=True, write_only=True, source='itens', required=False)
    cliente_id = serializers.PrimaryKeyRelatedField(queryset=Cliente.objects.all(), source='cliente', write_only=True)

    class Meta:
        model = Orcamento
        fields = ['id', 'cliente', 'data_criacao', 'valor_total', 'status', 'itens', 'cliente_id', 'itens_write']
        read_only_fields = ['valor_total', 'data_criacao']

    def create(self, validated_data):
        itens_data = validated_data.pop('itens', [])
        orcamento = Orcamento.objects.create(**validated_data)
        for item in itens_data:
            ItemOrcamento.objects.create(orcamento=orcamento, **item)
        orcamento.recalcular_total()
        return orcamento

    def update(self, instance, validated_data):
        itens_data = validated_data.pop('itens', None)
        # campos simples
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        # substitui itens
        if itens_data is not None:
            instance.itens.all().delete()
            for item in itens_data:
                ItemOrcamento.objects.create(orcamento=instance, **item)
        instance.recalcular_total()
        return instance

# ---------- ITENS DE PEDIDO ----------
class ItemPedidoSerializer(serializers.ModelSerializer):
    produto = ProdutoResumidoSerializer(read_only=True)
    nome_exibido = serializers.SerializerMethodField()

    class Meta:
        model = ItemPedido
        fields = ['id', 'produto', 'quantidade', 'largura', 'altura', 'descricao_customizada', 'subtotal', 'nome_exibido']

    def get_nome_exibido(self, obj):
        return obj.descricao_customizada or (obj.produto.nome if obj.produto else 'Item')

class ItemPedidoWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemPedido
        fields = ['produto', 'quantidade', 'largura', 'altura', 'descricao_customizada', 'subtotal']
        extra_kwargs = {'subtotal': {'required': False}}

# ---------- PAGAMENTO ----------
class PagamentoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Pagamento
        fields = ['id', 'pedido', 'valor', 'data', 'forma_pagamento']

# ---------- PEDIDO ----------
class PedidoSerializer(serializers.ModelSerializer):
    cliente = ClienteResumidoSerializer(read_only=True)
    itens = ItemPedidoSerializer(many=True, read_only=True)
    pagamentos = PagamentoSerializer(many=True, read_only=True)
    valor_pago = serializers.SerializerMethodField()
    valor_a_receber = serializers.SerializerMethodField()

    itens_write = ItemPedidoWriteSerializer(many=True, write_only=True, source='itens', required=False)
    cliente_id = serializers.PrimaryKeyRelatedField(queryset=Cliente.objects.all(), source='cliente', write_only=True, required=False)

    class Meta:
        model = Pedido
        fields = [
            'id', 'cliente', 'data_criacao', 'valor_total', 'status_producao', 'status_pagamento',
            'orcamento_origem', 'itens', 'pagamentos', 'custo_producao', 'valor_pago', 'valor_a_receber',
            'previsto_entrega', 'data_producao', 'forma_envio', 'codigo_rastreio', 'link_fornecedor',
            'itens_write', 'cliente_id'
        ]
        read_only_fields = ['valor_total', 'data_criacao', 'orcamento_origem']

    def get_valor_pago(self, obj):
        total_pago = obj.pagamentos.aggregate(total=Sum('valor'))['total']
        return total_pago or 0

    def get_valor_a_receber(self, obj):
        valor_pago = self.get_valor_pago(obj)
        return (obj.valor_total or 0) - (valor_pago or 0)

    def create(self, validated_data):
        itens_data = validated_data.pop('itens', [])
        pedido = Pedido.objects.create(**validated_data)
        for item in itens_data:
            ItemPedido.objects.create(pedido=pedido, **item)
        pedido.recalcular_total()
        return pedido

    def update(self, instance, validated_data):
        itens_data = validated_data.pop('itens', None)
        # atualiza campos simples
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # substitui itens se enviados
        if itens_data is not None:
            instance.itens.all().delete()
            for item in itens_data:
                # >>> AQUI GARANTIMOS QUE A DESCRIÇÃO CUSTOMIZADA DO ORÇAMENTO É MANTIDA
                ItemPedido.objects.create(pedido=instance, **item)

        instance.recalcular_total()
        return instance


# ---------- DESPESAS ----------
class DespesaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Despesa
        fields = ['id', 'descricao', 'valor', 'data', 'categoria']


class DespesaConsolidadaSerializer(serializers.Serializer):
    id = serializers.CharField(read_only=True)
    descricao = serializers.CharField()
    valor = serializers.DecimalField(max_digits=10, decimal_places=2)
    data = serializers.DateField()
    categoria = serializers.CharField(allow_null=True)
    tipo = serializers.CharField()


class EmpresaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Empresa
        fields = '__all__'


class EmpresaPublicaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Empresa
        fields = ['nome_empresa', 'logo_grande_dashboard']


class RelatorioClienteSerializer(serializers.ModelSerializer):
    total_gasto = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    ultimo_pedido = serializers.DateField(read_only=True)
    
    # CORREÇÃO: Mudado de IntegerField para SerializerMethodField
    dias_inativo = serializers.SerializerMethodField()

    class Meta:
        model = Cliente
        fields = ['id', 'nome', 'telefone', 'cpf_cnpj', 'total_gasto', 'ultimo_pedido', 'dias_inativo']
    
    # Adicionamos o método getter para extrair os dias
    def get_dias_inativo(self, obj):
        if hasattr(obj, 'dias_inativo') and obj.dias_inativo:
            return obj.dias_inativo.days
        return None

class RelatorioPedidosAtrasadosSerializer(serializers.ModelSerializer):
    cliente_nome = serializers.CharField(source='cliente.nome')
    
    # CORREÇÃO: Mudado de IntegerField para SerializerMethodField
    dias_atraso = serializers.SerializerMethodField()

    class Meta:
        model = Pedido
        fields = ['id', 'cliente_nome', 'dias_atraso']

    # Adicionamos o método getter para extrair os dias
    def get_dias_atraso(self, obj):
        if hasattr(obj, 'dias_atraso') and obj.dias_atraso:
            return obj.dias_atraso.days
        return 0

class FormaPagamentoAgrupadoSerializer(serializers.Serializer):
    forma_pagamento = serializers.CharField()
    value = serializers.IntegerField()


class StatusOrcamentoAgrupadoSerializer(serializers.Serializer):
    """ Serializer para o gráfico de pizza de status de orçamentos. """
    status = serializers.CharField()
    value = serializers.IntegerField() # 'value' é o nome que o recharts espera

class ProdutosOrcadosAgrupadoSerializer(serializers.Serializer):
    """ Serializer para o gráfico de barras de produtos mais orçados. """
    produto__nome = serializers.CharField()
    value = serializers.IntegerField()

class RelatorioOrcamentoRecenteSerializer(serializers.ModelSerializer):
    """ Serializer para a tabela de orçamentos recentes. """
    cliente_nome = serializers.CharField(source='cliente.nome')
    produto_principal = serializers.SerializerMethodField()
    # 'tempo_resposta' é complexo, vamos simplificar por agora
    
    class Meta:
        model = Orcamento
        fields = ['id', 'cliente_nome', 'produto_principal', 'valor_total', 'data_criacao', 'status']

    def get_produto_principal(self, obj):
        # Pega o nome do primeiro item do orçamento
        primeiro_item = obj.itens.first()
        if primeiro_item:
            return primeiro_item.nome_exibido
        return "N/A"
    

class RelatorioProdutoVendidoSerializer(serializers.Serializer):
    """
    Serializer para o gráfico de barras "Produtos Mais Vendidos".
    Espera 'produto__nome' e 'total_vendido'.
    """
    name = serializers.CharField(source='produto__nome')
    value = serializers.IntegerField(source='total_vendido')

class RelatorioProdutoLucrativoSerializer(serializers.Serializer):
    """
    Serializer para a lista "Produtos Mais Lucrativos".
    Espera 'produto__nome', 'margem' e 'lucro_total'.
    """
    name = serializers.CharField(source='produto__nome')
    margem = serializers.DecimalField(max_digits=5, decimal_places=2)
    total_lucro = serializers.DecimalField(max_digits=10, decimal_places=2)

class RelatorioProdutoBaixaDemandaSerializer(serializers.ModelSerializer):
    """
    Serializer para a tabela "Produtos em Baixa Demanda".
    Espera uma instância de Produto anotada com 'ultima_venda' e 'dias_sem_venda'.
    """
    ultima_venda = serializers.DateField(read_only=True)
    dias_sem_venda = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Produto
        fields = ['id', 'nome', 'preco', 'ultima_venda', 'dias_sem_venda']