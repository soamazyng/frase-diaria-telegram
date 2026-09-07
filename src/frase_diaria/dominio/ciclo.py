from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Ciclo:
    """As frases consumidas desde o último reinício da seleção.

    Guarda três coisas distintas, e a diferença entre elas é o que faz o sorteio
    sem repetição funcionar:

    - **consumidas** — já entregues neste ciclo, não voltam até o próximo;
    - **reservadas** — presas a um pedido em andamento, ainda não entregues;
    - **última entregue** — usada só na virada, para o ciclo seguinte não começar
      repetindo a frase que acabou de sair.

    O conjunto de frases ativas nunca é guardado aqui: ele vem da fonte a cada
    consulta. É isso que faz uma inserção entrar no ciclo atual e uma exclusão
    sumir das elegíveis, sem que o ciclo precise saber que a coleção mudou.
    """

    numero: int
    consumidas: frozenset[str]
    reservadas: frozenset[str]
    consumidas_com_ressalva: frozenset[str]
    ultima_entregue: str | None
    entregas_neste_ciclo: int

    @staticmethod
    def primeiro() -> "Ciclo":
        return Ciclo(
            numero=1,
            consumidas=frozenset(),
            reservadas=frozenset(),
            consumidas_com_ressalva=frozenset(),
            ultima_entregue=None,
            entregas_neste_ciclo=0,
        )

    # --- consulta ------------------------------------------------------------

    def elegiveis(self, ativas: tuple[str, ...]) -> tuple[str, ...]:
        """Frases ativas que ainda não foram consumidas nem estão reservadas."""
        indisponiveis = self.consumidas | self.reservadas
        return tuple(f for f in ativas if f not in indisponiveis)

    def foi_consumida(self, frase: str) -> bool:
        return frase in self.consumidas

    def esgotado(self, ativas: tuple[str, ...]) -> bool:
        """Todas as ativas consumidas e nenhuma reserva pendente.

        A ausência de reservas importa: reiniciar com um pedido em andamento
        poria a mesma frase em dois ciclos ao mesmo tempo.
        """
        return not self.elegiveis(ativas) and not self.reservadas

    def candidatas_a_primeira(self, ativas: tuple[str, ...]) -> tuple[str, ...]:
        """Quem pode ser a primeira entrega deste ciclo.

        Com duas ou mais frases ativas, a última entregue no ciclo anterior fica
        de fora. Com apenas uma, a repetição é inevitável e permitida; com zero,
        não há candidata (AC05).

        Depois da primeira entrega, a regra deixa de valer e todas as elegíveis
        voltam a concorrer.
        """
        elegiveis = self.elegiveis(ativas)
        if self.entregas_neste_ciclo > 0 or self.ultima_entregue is None:
            return elegiveis
        if len(elegiveis) <= 1:
            return elegiveis
        return tuple(f for f in elegiveis if f != self.ultima_entregue)

    # --- transições ----------------------------------------------------------

    def reservar(self, frase: str) -> "Ciclo":
        if frase in self.consumidas:
            raise ValueError(f"frase {frase} já consumida neste ciclo")
        if frase in self.reservadas:
            raise ValueError(f"frase {frase} já reservada")
        return replace(self, reservadas=self.reservadas | {frase})

    def liberar(self, frase: str) -> "Ciclo":
        """Devolve uma reserva às elegíveis, sem marcar consumo.

        É o desfecho de uma falha comprovada sem nenhum envio: a frase não chegou
        à usuária, então não foi gasta.
        """
        return replace(self, reservadas=self.reservadas - {frase})

    def consumir(self, frase: str, com_ressalva: bool = False) -> "Ciclo":
        """Marca a frase como gasta neste ciclo.

        `com_ressalva` registra que a entrega foi parcial ou incerta: a frase
        conta como usada — para não reenviar automaticamente algo que já pode ter
        chegado — mas o histórico preserva a dúvida.
        """
        if frase not in self.reservadas:
            raise ValueError(f"frase {frase} não está reservada neste ciclo")
        ressalvas = (
            self.consumidas_com_ressalva | {frase} if com_ressalva else self.consumidas_com_ressalva
        )
        return replace(
            self,
            reservadas=self.reservadas - {frase},
            consumidas=self.consumidas | {frase},
            consumidas_com_ressalva=ressalvas,
            ultima_entregue=frase,
            entregas_neste_ciclo=self.entregas_neste_ciclo + 1,
        )

    def reiniciar(self) -> "Ciclo":
        """Abre o ciclo seguinte, carregando apenas a última frase entregue."""
        return Ciclo(
            numero=self.numero + 1,
            consumidas=frozenset(),
            reservadas=frozenset(),
            consumidas_com_ressalva=frozenset(),
            ultima_entregue=self.ultima_entregue,
            entregas_neste_ciclo=0,
        )
