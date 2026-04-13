# Usar a imagem oficial do Python 3.11-slim para manter a leveza
FROM python:3.11-slim

# Evitar que o Python gere arquivos .pyc e garantir que o log seja exibido em tempo real
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Instalar dependências do sistema necessárias para compilação (posix_ipc e psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Definir o diretório de trabalho no container
WORKDIR /app

# Copiar apenas o arquivo de requisitos primeiro para aproveitar o cache do Docker
COPY requirements.txt .

# Instalar as dependências do Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar o restante do código fonte do projeto
COPY . .

# Gerar stubs gRPC Python a partir do proto (montado em /app/proto via volume)
# O script de entrypoint executa a geração em runtime para usar o proto montado
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "src/ingestor.py"]
