from django.db import models
from django.utils import timezone
from django.db.models import Sum

# ----------------------------
# Modelos de Entidades Base
# ----------------------------

class Cliente(models.Model):
    nome = models.CharField(max_length=200)  # Pode ser Nome ou Razão Social
    email = models.EmailField(blank=True, null=True)
    telefone = models.CharField(max_length=20, blank=True, null=True)
    cpf_cnpj = models.CharField(max_length=18, blank=True, null=True, default=None)
    data_cadastro = models.DateTimeField(auto_now_add=True, null=True)

    # --- NOVOS CAMPOS (Exemplo) ---
    observacao = models.TextField(blank=True, null=True)
    cep = models.CharField(max_length=10, blank=True, null=True)
    endereco = models.CharField(max_length=255, blank=True, null=True)
    numero = models.CharField(max_length=10, blank=True, null=True)
    bairro = models.CharField(max_length=100, blank=True, null=True)
    cidade = models.CharField(max_length=100, blank=True, null=True)
    estado = models.CharField(max_length=2, blank=True, null=True)

    def __str__(self):
        return self.nome

    class Meta:
        verbose_name = "Cliente"
        verbose_name_plural = "Clientes"


class Produto(models.Model):
    """Representa um produto ou serviço oferecido pela gráfica."""
    class TipoPrecificacao(models.TextChoices):
        UNICO = 'UNICO', 'Preço por Unidade'
        METRO_QUADRADO = 'M2', 'Preço por Metro Quadrado'

    nome = models.CharField(max_length=100, help_text="Nome do produto (ex: Banner em Lona)")
    tipo_precificacao = models.CharField(
        max_length=5,
        choices=TipoPrecificacao.choices,
        default=TipoPrecificacao.UNICO,
        help_text="Define como o preço do produto é calculado"
    )
    preco = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Preço por unidade ou por metro quadrado"
    )

    custo = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        default=0, 
        help_text="Custo de PRODUÇÃO por unidade ou por metro quadrado"
    )
    estoque_atual = models.IntegerField(
        default=0, 
        null=True, 
        blank=True, 
        help_text="Quantidade atual em estoque. Nulo para serviços."
    )
    estoque_minimo = models.IntegerField(
        default=0, 
        null=True, 
        blank=True, 
        help_text="Nível de alerta para o estoque"
    )

    def __str__(self):
        return f'{self.nome} ({self.get_tipo_precificacao_display()})'

    class Meta:
        verbose_name = "Produto"
        verbose_name_plural = "Produtos"


# -------------------------------------
# Modelos de Transações e Fluxo de Trabalho
# -------------------------------------

class Orcamento(models.Model):
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="orcamentos")
    data_criacao = models.DateTimeField(default=timezone.now)
    valor_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=50, default='Em Aberto', help_text="Ex: Em Aberto, Aprovado, Rejeitado")

    def recalcular_total(self):
        total = self.itens.all().aggregate(
            total_calculado=models.Sum('subtotal')
        )['total_calculado']
        self.valor_total = total if total is not None else 0
        self.save(update_fields=['valor_total'])

    def __str__(self):
        return f'Orçamento #{self.id} - {self.cliente.nome}'

    class Meta:
        verbose_name = "Orçamento"
        verbose_name_plural = "Orçamentos"

    # >>> NOVO: helper para gerar pedido a partir do orçamento
    def gerar_pedido(self):
        """
        Cria um Pedido com base neste orçamento, copiando os itens
        (incluindo descricao_customizada e subtotal).
        Retorna o Pedido criado.
        """
        pedido = Pedido.objects.create(
            cliente=self.cliente,
            orcamento_origem=self,
            valor_total=0,  # recalculado abaixo
            status_producao='Aguardando',
            status_pagamento=Pedido.StatusPagamento.PENDENTE,
            data_criacao=timezone.now()
        )
        # Copia os itens do orçamento
        itens_orc = list(self.itens.all())
        for io in itens_orc:
            ItemPedido.objects.create(
                pedido=pedido,
                produto=io.produto if io.produto_id else None,  # ✅ segurança extra
                quantidade=io.quantidade,
                largura=io.largura,
                altura=io.altura,
                descricao_customizada=io.descricao_customizada,
                subtotal=io.subtotal
            )
        pedido.recalcular_total()
        return pedido


class ItemOrcamento(models.Model):
    orcamento = models.ForeignKey(Orcamento, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey(Produto, on_delete=models.PROTECT, null=True, blank=True)
    quantidade = models.PositiveIntegerField(default=1)
    largura = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    altura = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    descricao_customizada = models.CharField(max_length=255, blank=True, null=True)

    def save(self, *args, **kwargs):
        # Calcula subtotal se não informado
        if not self.subtotal:
            if self.produto.tipo_precificacao == 'M2':
                if not self.largura or not self.altura:
                    raise ValueError("Largura e Altura são obrigatórias para produtos por m²")
                self.subtotal = self.produto.preco * self.largura * self.altura * self.quantidade
            else:  # 'UNICO'
                self.subtotal = self.produto.preco * self.quantidade
        super().save(*args, **kwargs)

    @property
    def nome_exibido(self):
        return self.descricao_customizada or self.produto.nome

    def __str__(self):
        base = self.descricao_customizada or self.produto.nome
        return f'{self.quantidade}x {base} (Orçamento #{self.orcamento.id})'

    class Meta:
        verbose_name = "Item de Orçamento"
        verbose_name_plural = "Itens de Orçamentos"


class Pedido(models.Model):
    """Representa um pedido confirmado, que pode ter origem de um orçamento."""
    class StatusPagamento(models.TextChoices):
        PENDENTE = 'PENDENTE', 'Pendente'
        PARCIAL = 'PARCIAL', 'Parcial'
        PAGO = 'PAGO', 'Pago'

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="pedidos")
    orcamento_origem = models.OneToOneField(Orcamento, on_delete=models.SET_NULL, null=True, blank=True)
    data_criacao = models.DateTimeField(default=timezone.now)
    valor_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status_producao = models.CharField(max_length=50, default='Aguardando', help_text="Ex: Aguardando Arte, Em Produção, Finalizado")
    status_pagamento = models.CharField(max_length=10, choices=StatusPagamento.choices, default=StatusPagamento.PENDENTE)
    previsto_entrega = models.DateField(blank=True, null=True)
    custo_producao = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    data_producao = models.DateField(blank=True, null=True)
    forma_envio = models.CharField(max_length=100, blank=True, null=True)
    codigo_rastreio = models.CharField(max_length=100, blank=True, null=True)
    link_fornecedor = models.URLField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f'Pedido #{self.id} - {self.cliente.nome}'
    
    def recalcular_total(self):
        # Recalcula cada item conforme tipo de precificação
        for item in self.itens.all():
            item.save()
        total = self.itens.aggregate(total_calculado=Sum('subtotal'))['total_calculado']
        self.valor_total = total if total is not None else 0
        self.save(update_fields=['valor_total'])

    class Meta:
        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"


class ItemPedido(models.Model):
    """Representa um item de produto dentro de um pedido."""
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey(Produto, on_delete=models.PROTECT, null=True, blank=True)  # ✅ Agora opcional
    quantidade = models.PositiveIntegerField(default=1)
    largura = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    altura = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    descricao_customizada = models.CharField(max_length=255, blank=True, null=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        base = self.descricao_customizada or (self.produto.nome if self.produto else "Item Manual")
        return f'{self.quantidade}x {base} (Pedido #{self.pedido.id})'
    
    def save(self, *args, **kwargs):
        # Calcula subtotal apenas se não informado
        if not self.subtotal:
            if self.produto:
                if self.produto.tipo_precificacao == 'M2':
                    if not self.largura or not self.altura:
                        self.subtotal = 0
                    else:
                        self.subtotal = self.produto.preco * self.largura * self.altura * self.quantidade
                else:  # 'UNICO'
                    self.subtotal = self.produto.preco * self.quantidade
            else:
                # Item manual sem produto vinculado
                self.subtotal = 0
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Item de Pedido"
        verbose_name_plural = "Itens de Pedidos"


# ----------------------------
# Modelos Financeiros
# ----------------------------

class Despesa(models.Model):
    """Registra uma despesa da empresa."""
    descricao = models.CharField(max_length=255, help_text="Descrição da despesa (ex: Aluguel)")
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    data = models.DateField(help_text="Data em que a despesa ocorreu ou foi paga")
    categoria = models.CharField(max_length=100, blank=True, null=True, help_text="Ex: Fornecedores, Impostos, Salários")

    def __str__(self):
        return f'{self.descricao} - R$ {self.valor} em {self.data.strftime("%d/%m/%Y")}'
    
    class Meta:
        verbose_name = "Despesa"
        verbose_name_plural = "Despesas"


class Pagamento(models.Model):
    class FormaPagamento(models.TextChoices):
        PIX = 'PIX', 'Pix'
        DINHEIRO = 'DINHEIRO', 'Dinheiro'
        CARTAO = 'CARTAO', 'Cartão'
        BOLETO = 'BOLETO', 'Boleto'

    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='pagamentos')
    valor = models.DecimalField(max_digits=10, decimal_places=2)
    data = models.DateTimeField(default=timezone.now)
    forma_pagamento = models.CharField(max_length=50, choices=FormaPagamento.choices, default=FormaPagamento.PIX)

    def __str__(self):
        return f'Pagamento de R$ {self.valor} ({self.get_forma_pagamento_display()}) para o Pedido #{self.pedido.id}'
    

class Empresa(models.Model):
    nome_empresa = models.CharField(max_length=200, default="Gráfica Cloud Design")
    razao_social = models.CharField(max_length=200, blank=True, null=True)
    cnpj = models.CharField(max_length=18, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    whatsapp = models.CharField(max_length=20, blank=True, null=True)
    instagram = models.CharField(max_length=100, blank=True, null=True)
    site = models.URLField(max_length=255, blank=True, null=True)

    cep = models.CharField(max_length=10, blank=True, null=True)
    endereco = models.CharField(max_length=255, blank=True, null=True)
    numero = models.CharField(max_length=20, blank=True, null=True)
    bairro = models.CharField(max_length=100, blank=True, null=True)
    complemento = models.CharField(max_length=100, blank=True, null=True)
    cidade = models.CharField(max_length=100, blank=True, null=True)
    estado = models.CharField(max_length=2, blank=True, null=True)

    logo_grande_dashboard = models.ImageField(upload_to='logos/', blank=True, null=True)
    logo_pequena_dashboard = models.ImageField(upload_to='logos/', blank=True, null=True)
    logo_orcamento_pdf = models.ImageField(upload_to='logos/', blank=True, null=True)

    def __str__(self):
        return self.nome_empresa or "Configurações da Empresa"

    def save(self, *args, **kwargs):
        self.pk = 1
        super(Empresa, self).save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "Empresa"
