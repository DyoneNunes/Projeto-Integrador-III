# Roteiro de Apresentação — MVP Final: MaaS & Sentinela Ambiental 🎥

Este documento contém o roteiro estruturado para a gravação do seu vídeo de apresentação do produto final (MVP) para o professor Howard Cruz Roatti (FAESA - PI-III).

---

## ⏱️ Visão Geral e Tempo Estimado

*   **Tempo Total Sugerido:** 8 a 10 minutos.
*   **Divisão:**
    *   **Parte 1:** Introdução e Conceitos (MaaS) — ~2 min
    *   **Parte 2:** Engenharia do MaaS Core e Dashboard — ~3 min
    *   **Parte 3:** Sentinela Ambiental (Consumidor) e Pipeline de IA — ~3 min
    *   **Parte 4:** Documentação, Testes e Fechamento — ~1.5 min

---

## 🎬 Tabela de Cenas e Script

| Tempo | O que Mostrar na Tela (Vídeo) | O que Falar (Áudio/Narração) | Notas Técnicas / Ação |
| :--- | :--- | :--- | :--- |
| **00:00 - 01:00** | **Slide 1 / Título do Projeto**<br>Mostre o repositório principal no VS Code com o `README.md` aberto ou um slide com seu nome (Dyone Nunes), o nome do projeto (MaaS) e a FAESA. | "Olá, professor Howard e membros da banca. Meu nome é Dyone Nunes de Andrade, sou estudante de Análise e Desenvolvimento de Sistemas na FAESA. Hoje, apresento o MVP final do meu Projeto Integrador III. O tema deste projeto é o **MaaS — Memory as a Service**, uma infraestrutura de **Software-Defined Memory (SDM)** em nuvem, e o **Sentinela Ambiental**, uma aplicação de processamento de dados térmicos que atua como o consumidor secundário desse serviço de memória descentralizada." | Mantenha um tom profissional e seguro. Mostre seu rosto por webcam no canto se possível. |
| **01:00 - 02:00** | **Diagrama de Arquitetura**<br>Abra o `README.md` e mostre o diagrama Mermaid de arquitetura do MaaS e do Sentinela. | "O objetivo do MaaS é resolver o gargalo de memória de servidores tradicionais através do desacoplamento e desagregação de hardware, o conceito de *Memory Disaggregation*. Em termos práticos, um cliente 'aluga' buffers de memória física (RAM) rodando em um servidor remoto potente e escreve ou lê dados diretamente nessa memória compartilhada como se fosse local, liberando a CPU local do cliente para focar apenas na lógica da aplicação. A arquitetura se divide em dois planos: o **Data Plane**, composto pelo núcleo de performance em C++, e o **Control Plane**, composto por um painel web em Next.js e banco de dados PostgreSQL para gestão, faturamento e cotas." | Passe o cursor sobre o fluxo do diagrama para guiar a explicação do professor. |
| **02:00 - 03:15** | **Código Fonte C++ no VS Code**<br>Abra o arquivo `server/main.cpp` e mostre as funções que lidam com `shm_open`, `mmap`, `mlock` e `madvise`. | "No coração do Data Plane está o **MaaS Core**, desenvolvido em **C++20**. Ele expõe um servidor **gRPC síncrono** na porta `50051`. Quando o cliente requisita memória, o Core usa chamadas de sistema POSIX. Ele aloca um bloco usando `shm_open` (gerando um arquivo em `/dev/shm`), expande o bloco com `ftruncate` e projeta-o em memória virtual via `mmap`. Para garantir latência próxima à de barramento local, aplicamos duas otimizações críticas: o `mlock`, que impede o sistema operacional de enviar essas páginas para a área de swap, e o `madvise` com a flag `MADV_HUGEPAGE`, instruindo o kernel Linux a usar páginas de memória maiores (Huge Pages) para acelerar a tradução de endereços físicos." | Destaque as linhas de código com o mouse enquanto fala dessas chamadas específicas do Kernel Linux. |
| **03:15 - 04:30** | **Navegador: Dashboard do MaaS (`localhost:3002`)**<br>Abra o dashboard Next.js. Mostre os gráficos (Top Consumers), os KPIs de RAM física em tempo real, as alocações ativas e a aba de tenants. | "Para gerenciar esses recursos físicos, temos o **Control Plane**. Esse dashboard foi construído com **Next.js 14**, **Prisma ORM** e **TailwindCSS**. Aqui podemos monitorar o consumo ativo da RAM, visualizar a saúde dos nós de cluster e cadastrar Tenants (clientes). Cada alocação gera metadados que são persistidos em um banco **PostgreSQL 15**. Também temos um faturamento atômico configurado para cobrar por byte-segundo consumido, além de podermos emitir relatórios completos de auditoria em PDF ou CSV com a biblioteca `jspdf`, demonstrando a viabilidade de comercializar a RAM em modelo PaaS." | Execute uma ação real: clique para criar ou visualizar um Tenant, ou abra o modal e clique para gerar um relatório em PDF de consumo. |
| **04:30 - 05:45** | **VS Code: `proto/maas.proto` e `maas_client.py`**<br>Mostre o arquivo de contrato gRPC (`maas.proto`) e o cliente em Python `maas_client.py`. | "Para demonstrar o MaaS na prática, desenvolvemos o **Sentinela Ambiental**, uma aplicação Python stateless focada em processamento rápido de anomalias térmicas globais obtidas da API NASA FIRMS. A integração entre o cliente Python e o servidor C++ é regida por este contrato gRPC definido em Protobuf (`maas.proto`). O serviço expõe RPCs de `Allocate`, `Deallocate`, fluxo contínuo de telemetria com `ReportMetrics` e operações de I/O de baixa latência em rede usando `WriteMemory` e `ReadMemory`. O cliente consome esses métodos através de uma abstração em Python que implementa a interface clássica de *file-like stream*, facilitando o fluxo de gravação e leitura." | Mostre a classe `MaaSMemory` no arquivo `maas_client.py`, chamando `WriteMemory` e `ReadMemory`. |
| **05:45 - 07:15** | **VS Code: Código do Pipeline (`ingestor.py` / `data_processor.py` / `ai_processor.py`)**<br>Transicione para a explicação dos 3 estágios. Mostre a formatação binary struct (`=ddddiii`). | "O pipeline de dados do Sentinela funciona de forma puramente stateless, estruturado em três estágios desacoplados operando com buffers do MaaS:<br>**1. Ingestor**: Aloca um buffer de 100MB no MaaS e grava dados brutos de satélites no formato binário de baixo nível através de uma struct estrita de 44 bytes.<br>**2. Data Processor**: Lê o buffer, filtra anomalias críticas (como temperaturas acima de 330 Kelvin), calcula métricas espaciais e escreve no Buffer B (50MB).<br>**3. AI Processor**: Consome as features e executa uma classificação de urgência usando o modelo preditivo **LightGBM** (ou uma heurística inteligente caso offline), salvando o risco final no Buffer C de 20MB. O PostgreSQL só recebe dados consolidados para relatórios, eliminando qualquer gargalo de escrita em disco durante o processamento." | Destaque a variável `STRUCT_FORMAT = '=ddddiii'` no ingestor para mostrar como os dados são serializados compactados em memória. |
| **07:15 - 08:30** | **Navegador: Globo 3D do Sentinela (`localhost:8000`)**<br>Abra o painel interativo do Sentinela Ambiental com o Globo 3D gerado pelo Globe.gl. | "E este é o resultado final visto pelo usuário. Temos uma interface interativa rica usando **Three.js** e **Globe.gl**. O sistema ingere focos térmicos de satélites em tempo real. Cada hexágono representa um foco de calor ou frio agregado espacialmente, onde a altura representa a intensidade energética (FRP - Fire Radiative Power) e as cores indicam a severidade determinada pela IA: vermelho para críticas, azul para informações e verde para riscos baixos. Podemos filtrar por janela de tempo (ex. 6h a 72h), por continente ou país, e extrair um relatório detalhado com os 100 maiores focos térmicos ativos." | Manipule o globo na tela: rotacione, dê zoom em uma área (ex. Brasil ou África), altere o filtro de tempo ou de severidade e mostre os dados mudando em tempo real. |
| **08:30 - 09:15** | **Navegador / Terminal: Documentação e Testes**<br>Mostre o site estático gerado pelo MkDocs rodando no navegador ou mostre a pasta `testes_consumidor/`. | "A qualidade e confiabilidade do software foram priorizadas. Toda a documentação técnica foi estruturada com **MkDocs Material**, detalhando esquemas de banco, guias de usuário e manuais do desenvolvedor. Além disso, criamos uma suíte completa de **testes automatizados com Pytest**, cobrindo 12 módulos e mais de 730 linhas de código. Testamos desde o comportamento das structs binárias em memória compartilhada até o pipeline de inferência da IA e as rotas HTTP da API, garantindo robustez contínua." | Se preferir, abra um terminal e rode `pytest` ou mostre as saídas verdes de testes bem-sucedidos. |
| **09:15 - 10:00** | **Encerramento / Webcam**<br>Volte para o slide inicial ou webcam cheia. | "Em suma, o ecossistema provou que a tecnologia de desagregação de memória do MaaS, acoplada a linguagens de alta performance como C++ no Data Plane e Python no processamento analítico, oferece uma solução robusta, scalável e de latência extremamente baixa para problemas de processamento de dados massivos em tempo real, como o monitoramento ambiental. Agradeço imensamente ao professor Howard Cruz Roatti pela orientação e feedback ao longo desse semestre e fico à disposição para as perguntas da banca. Muito obrigado." | Finalize com um sorriso e um agradecimento formal. |

---

## 🛠️ Passo a Passo para Preparar a Demonstração (Antes de Gravar)

Para garantir que tudo funcione perfeitamente durante a gravação e evitar imprevistos:

1.  **Limpe o ambiente Docker:**
    Certifique-se de iniciar a stack limpa e funcional.
    ```bash
    # Na raiz do projeto:
    docker compose down -v
    docker compose up -d --build
    ```
    *(Verifique se o Dashboard abre em `http://localhost:3002` e se conecta ao Postgres e ao gRPC Core).*

2.  **Inicie o Sentinela Ambiental:**
    ```bash
    cd Consumidor
    docker compose down -v
    docker compose up -d --build
    ```
    *(Verifique se a UI 3D abre em `http://localhost:8000` e se os logs do Ingestor/Processor/AI estão rodando ativamente).*

3.  **Monitore os Logs (dica para o vídeo):**
    Deixe um terminal dividido pronto com `docker compose logs -f` do MaaS e do Sentinela para mostrar a atividade de escrita e leitura de RAM ao vivo, se quiser impressionar o professor com a atividade nos bastidores.

4.  **Verifique a Documentação:**
    Inicie o site de documentação localmente para mostrar na apresentação:
    ```bash
    # Na raiz do projeto
    mkdocs serve
    ```
    *(Abra em `http://127.0.0.1:8000` no seu navegador).*

5.  **Rode os testes em tela (opcional mas altamente recomendado):**
    Rode a suíte de testes do consumidor e mostre o resultado na gravação:
    ```bash
    # Dentro da pasta Consumidor (ou no container do processador)
    pytest -v
    ```
