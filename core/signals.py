# core/signals.py

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import ItemOrcamento

# O decorator @receiver conecta nossa função aos sinais do Django.
# Esta função será chamada sempre que um ItemOrcamento for salvo ou deletado.
@receiver([post_save, post_delete], sender=ItemOrcamento)
def atualizar_total_orcamento(sender, instance, **kwargs):
    """
    Gatilho para recalcular o valor total de um orçamento sempre que
    um de seus itens for salvo ou deletado.
    """
    # 'instance' é o objeto ItemOrcamento que disparou o sinal.
    # A partir dele, acessamos o orçamento pai e chamamos o método de recálculo.
    instance.orcamento.recalcular_total()