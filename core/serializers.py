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
    # Serializers para LEITURA (quando enviamos dados para o front-end)
    cliente = ClienteResumidoSerializer(read_only=True)
    itens = ItemOrcamentoSerializer(many=True, read_only=True)
    
    # Serializer para ESCRITA (quando recebemos dados do front-end)
    # Usamos 'source' para ligar este campo ao relacionamento 'itens' do modelo
    itens_write = ItemOrcamentoWriteSerializer(many=True, write_only=True, source='itens')
    # O front-end envia apenas o ID do cliente, então usamos PrimaryKeyRelatedField para escrita
    cliente_id = serializers.PrimaryKeyRelatedField(
        queryset=Cliente.objects.all(), source='cliente', write_only=True
    )

    class Meta:
        model = Orcamento
        fields = [
            'id', 'cliente', 'data_criacao', 'valor_total', 'status', 'itens',
            'cliente_id', 'itens_write' # Adicionamos os campos de escrita
        ]
    
    def create(self, validated_data):
        """
        Método customizado para criar um Orçamento e seus Itens de uma só vez.
        """
        # 1. Remove os dados dos itens do dicionário principal.
        itens_data = validated_data.pop('itens')
        
        # 2. Cria a instância principal do Orçamento com os dados restantes.
        orcamento = Orcamento.objects.create(**validated_data)
        
        # 3. Itera sobre cada item recebido e o cria, ligando-o ao orçamento recém-criado.
        for item_data in itens_data:
            ItemOrcamento.objects.create(orcamento=orcamento, **item_data)
            
        return orcamento
    

class ItemPedidoSerializer(serializers.ModelSerializer):
    produto = ProdutoResumidoSerializer(read_only=True)
    class Meta:
        model = ItemPedido
        fields = ['id', 'produto', 'quantidade', 'largura', 'altura', 'subtotal']

class ItemPedidoWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = ItemPedido
        fields = ['produto', 'quantidade', 'largura', 'altura']

class PedidoSerializer(serializers.ModelSerializer):
    cliente = ClienteResumidoSerializer(read_only=True)
    itens = ItemPedidoSerializer(many=True, read_only=True)
    
    itens_write = ItemPedidoWriteSerializer(many=True, write_only=True, source='itens', required=False)
    cliente_id = serializers.PrimaryKeyRelatedField(
        queryset=Cliente.objects.all(), source='cliente', write_only=True, required=False
    )

    class Meta:
        model = Pedido
        fields = [
            'id', 'cliente', 'data_criacao', 'valor_total', 
            'status_producao', 'status_pagamento', 'orcamento_origem',
            'itens', 'itens_write', 'cliente_id'
        ]
        # A CORREÇÃO ESTÁ AQUI: Dizemos ao serializer para não esperar o 'valor_total' na entrada.
        read_only_fields = ['valor_total']
    
    def update(self, instance, validated_data):
        itens_data = validated_data.pop('itens', None)

        instance.status_producao = validated_data.get('status_producao', instance.status_producao)
        instance.status_pagamento = validated_data.get('status_pagamento', instance.status_pagamento)
        
        if 'cliente' in validated_data:
            instance.cliente = validated_data.get('cliente', instance.cliente)

        instance.save()

        if itens_data is not None:
            instance.itens.all().delete()
            for item_data in itens_data:
                ItemPedido.objects.create(pedido=instance, **item_data)
        
        instance.recalcular_total() # Recalcula o total com base nos novos itens

        return instance