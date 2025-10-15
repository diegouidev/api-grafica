# Em seu_app/models.py

from django.db import models
from django.utils import timezone

# ----------------------------
# Modelos de Entidades Base
# ----------------------------

# backend/core/models.py
class Cliente(models.Model):
    nome = models.CharField(max_length=200) # Pode ser Nome ou Razão Social
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
    # etc...

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
    # O valor deste campo será interpretado de acordo com o 'tipo_precificacao'.
    preco = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Preço por unidade ou por metro quadrado"
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
    # ... (campos existentes) ...
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="orcamentos")
    data_criacao = models.DateTimeField(auto_now_add=True)
    valor_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=50, default='Em Aberto', help_text="Ex: Em Aberto, Aprovado, Rejeitado")
    data_criacao = models.DateTimeField(default=timezone.now)

    # --- Adicione o método abaixo ---
    def recalcular_total(self):
        # Soma o subtotal de todos os itens relacionados a este orçamento
        total = self.itens.all().aggregate(
            total_calculado=models.Sum('subtotal')
        )['total_calculado']
        
        self.valor_total = total if total is not None else 0
        self.save()

    def __str__(self):
        return f'Orçamento #{self.id} - {self.cliente.nome}'

    class Meta:
        verbose_name = "Orçamento"
        verbose_name_plural = "Orçamentos"


class ItemOrcamento(models.Model):
    # ... (campos existentes) ...
    orcamento = models.ForeignKey(Orcamento, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey(Produto, on_delete=models.PROTECT)
    quantidade = models.PositiveIntegerField(default=1)
    largura = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    altura = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    # --- Adicione o método save abaixo ---
    def save(self, *args, **kwargs):
        # Lógica de cálculo do subtotal
        if self.produto.tipo_precificacao == 'M2':
            # Validação para garantir que largura e altura foram fornecidas
            if not self.largura or not self.altura:
                raise ValueError("Largura e Altura são obrigatórias para produtos por m²")
            self.subtotal = self.produto.preco * self.largura * self.altura * self.quantidade
        else: # 'UNICO'
            self.subtotal = self.produto.preco * self.quantidade
            
        super().save(*args, **kwargs) # Chama o método save original para salvar no banco

    def __str__(self):
        return f'{self.quantidade}x {self.produto.nome} (Orçamento #{self.orcamento.id})'

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
    data_criacao = models.DateTimeField(auto_now_add=True)
    valor_total = models.DecimalField(max_digits=10, decimal_places=2)
    status_producao = models.CharField(max_length=50, default='Aguardando', help_text="Ex: Aguardando Arte, Em Produção, Finalizado")
    status_pagamento = models.CharField(max_length=10, choices=StatusPagamento.choices, default=StatusPagamento.PENDENTE)
    data_criacao = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f'Pedido #{self.id} - {self.cliente.nome}'

    class Meta:
        verbose_name = "Pedido"
        verbose_name_plural = "Pedidos"


class ItemPedido(models.Model):
    """Representa um item de produto dentro de um pedido."""
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='itens')
    produto = models.ForeignKey(Produto, on_delete=models.PROTECT)
    quantidade = models.PositiveIntegerField(default=1)
    
    # Campos para produtos m². Nulos se o produto for de preço único.
    largura = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    altura = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f'{self.quantidade}x {self.produto.nome} (Pedido #{self.pedido.id})'

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