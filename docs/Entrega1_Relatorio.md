# Entregas - Projeto Integrador III (PI-III)

**Alunos/Equipe:** Dyone Andrade (Matrícula a preencher)  
**Curso:** Tecnologia em Análise e Desenvolvimento de Sistemas (TADS)  
**Professor Responsável:** Howard Cruz  
**Data da Entrega 1:** 23/03 a 27/03  

---

## Entrega 1: Relatório Detalhado do Projeto

### 1. Escopo do Projeto e Justificativa do Tema
O **MaaS (Memory as a Service) - Sentinela Ambiental** é um ecossistema projetado para atuar no monitoramento térmico de anomalias radiativas (focos de incêndio e calor extremo) na superfície, utilizando arquiteturas de alta resiliência e baixíssima latência (Software-Defined Memory).

**Justificativa:** 
A identificação rápida de focos de incêndio florestal ou urbano é crítica para a mitigação de danos ambientais graves e de impactos diretos na saúde da população. Escolhemos o monitoramento ambiental no **Estado do Espírito Santo** como tema núcleo devido à crescente incidência de estresse térmico observada nos dados abertos. Ao dissociar a alocação de RAM (MaaS) dos clientes de ingestão (Consumidor), garantimos que o volume massivo de dados térmicos possa ser engolido, serializado e analisado em tempo real sem interrupções por falta de memória local.

### 2. Sociedade Impactada
A sociedade impactada diretamente pelo projeto inclui:
- **Órgãos de Defesa Civil do Espírito Santo e Corpo de Bombeiros Militar:** Beneficiam-se enormemente da latência zero na detecção de alertas críticos geo-referenciados em seus municípios de atuação, permitindo despacho ágil de equipes.
- **Secretarias de Meio Ambiente e Gestores Urbanos:** Têm acesso aos dashboards interativos (Painel Sentinela) que consolidam estatísticas temporais de áreas com recorrência térmica para formulação de políticas públicas.
- **População em Geral:** Salvos da inalação indevida de fumaça e de riscos diretos dos desastres relacionados ao fogo que se aproximam das zonas urbanizadas.

### 3. Ciência de Dados Aplicada
Em cumprimento ao edital do PI-III, a extração de valor ("insights") a partir do grande volume de dados simulados (ou oriundos de fontes como *NASA FIRMS*) é realizada no módulo **Python Ingestor/Data Processor**.  

A metodologia aplicada, dada a natureza do perfil do curso (TADS), consiste em um modelo analítico de *Data Mining* via **Thresholding (Limiarização) Contínua** no *stream* de dados da Shared Memory (MaaS). 
Ao invés de adotar modelos preditivos baseados em redes neurais complexas, utilizamos a técnica apropriada para "real-time anomaly detection streaming":
* Aplicamos as restrições logicas iterativas `temp >= 330 K` e `confidence >= 80%`.
* A filtragem elimina mais de 98% de dados normais do clima (separação de sinal vs ruído), catalogando no Banco Relacional (PostgreSQL) apenas amostras estatisticamente consideradas "Anomalias Térmicas Críticas".
* Esse processamento garante agilidade na decisão, que é o coração da resposta ambiental.

### 4. Metodologia e Funcionalidades do Sistema (Protótipo/MVP)
Este trabalho adere totalmente à exigência de desenvolvimento de um *Sistema Web para apoio à tomada de decisão* estabelecido para o curso TADS. A solução apresenta:
1. **Painel / Dashboard Ambiental (Streamlit):** Interface focada no mapeamento geográfico e relatórios imediatos (exibindo mapas Folium, gráficos de tendência temporais interativos via *Plotly*, listas de ocorrências mais recentes).
2. **Dashboard de Resiliência (Next.js):** Focado na estabilidade da gestão do projeto, gerenciando a infraestrutura "MaaS" por trás das análises e indicando o estado geral da alocação de memória do cluster C++ em uma visão RESTful e visualmente atrativa.
3. **Plano de versão:** Todo o código é versionado via GitHub, utilizando Docker para orquestração modular, o que facilita o deploy contínuo em instâncias em Nuvem ou infraestruturas Acadêmicas.

### 5. Plano de Trabalho de Entregas e Métricas
Para auferir o impacto da inovação desenvolvida neste projeto, trabalharemos com as seguintes métricas claras:
1. **Volume de Ruído Reduzido (Métrica Analítica):** A proporção entre leituras térmicas gerais da região e o volume de alertas finais persistidos. (Confirma o papel do algoritmo em mitigar o *cansaço de alerta*).
2. **Tempo de Processamento/Latência (Métrica de Engenharia):** Medir o custo-tempo entre a inserção de um ponto sintético na mmap e o momento em que a anomalia apita no Streamlit (objetivando uma latência sob milissegundos devido a nossa implementação de Shared Memory Linux ao invés de redes via Socket tradicionais nos dataloaders).

As próximas fases (*Entrega 2 - 04/05* e *Entrega 3 - 08/06*) abrangerão a expansão visual dos portais Web e o polimento da integração dos filtros geográficos diretamente ao banco de dados com uma massa realista de testes térmicos.
