# Simulador Ferroviário
O Simulador Ferroviário é uma ferramenta que tem por objetivo simular o tráfego de trens em ferrovia com linhas do tipo dupla e singela. O sistema objeto de simulação, por sua vez, é composto por uma ferrovia que tem delimitação entre pontos de unidade de demanda e unidade de suprimento onde os trens irão trafegar em ciclo a partir de uma origem especificada inicialmente.

## Modelo Conceitual
A nível de construção do simulador, a abstração do sistema pode ser exemplificada com base na imagem abaixo: 

![Figura 16_D](https://user-images.githubusercontent.com/38539533/119235663-fede1880-bb09-11eb-9b23-d7fac5672957.png)

A partir disso, as principais premissas e considerações são:
- Cada setor possui um par seções de bloqueio (SBiA, SBiB) e um travessão universal composto de 3 seções de bloqueio (Ti1,Ti2,Ti3)
  - Não há distinção entre as seções de bloqueio em termos de geometria e lógicas de funcionamento e alocação
- Não há distinção entre os trens em quanto a locomotivas e vagões
- Parte-se da premissa que os trens irão trafegar em ciclos dada demanda constante da unidade demandante e capacidade ilimitada da unidade de suprimento 


## Como funciona
O Simulador Ferroviário utiliza a lógica de [simulação eventos discretos](https://pt.wikipedia.org/wiki/Simula%C3%A7%C3%A3o_de_eventos_discretos). Isto é possível devido ao sistema de filas e aos recursos de capacidade limitada instituídos na ferrovia de acordo com a imagem a seguir:

![Figura 18](https://user-images.githubusercontent.com/38539533/119280790-44353f80-bc09-11eb-9731-2beecde2d06e.png)

Para que o progesso da simulação ocorra e as entidades possam deslocar ao longo dessa ferrovia figurada como sistema de filas, há no algoritmo dois processos definidos: o da unidade de controle (UnidadeControle) e do entidade (Trem). Ao passo que a unidade de controle irá gerenciar o tráfego ferroviário para evitar conflito entre os trens além de travamentos e ou bloqueio das linhas, o processo da entidade trem garantirá o deslocamento ao longo da ferrovia. Nesse ponto, a utilização de eventos é fundamental.

Os eventos possibitam a comunicação entre o processo da entidade e da unidade de controle. Especificamente, dado que na simulação coexistem diversas entidades em diferentes estados e posições ao longo da linha cronológica da simulação, o permissionamento para o tráfego seguro de modo a garantir a ausência de bloqueios e ou a de travamentos requer um mecanismo que paralelize o avanço do tempo e considere os dados até a então intercalação dos processos para múltiplas entidades. Isto é, os eventos permitem satisfazer essa demanda da particularidade assíncrona entre as movimentações. Logo, o funcionamento:

![Figura 19](https://user-images.githubusercontent.com/38539533/119281411-05ed4f80-bc0c-11eb-972d-4b2eddafc821.png)


## Como utilizar
Acesse: https://share.streamlit.io/lucascorteletti/simulador_ferroviario/main/main_sim_linha_dupla.py

## Pontos relavantes
A partir desse simulador é possível realizar a experimentação de diversos cenários envolvendo pontos de aleatoriedade entre velocidade do trem e do tipo de trem em circulação. Além disso, é possível avaliar tanto o efeito sobre disposição de linhas do tipo singela entre linhas duplas, reproduzindo indisponibilidades na via, como a quantidade e maneira desse arranjo perante indicadores e tempo médio de trânsito e trem hora parada (THP).
