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

# 1. Pacotes leves (rápido, nunca falha)
RUN pip install --no-cache-dir --timeout=120 \
    python-dotenv==1.0.1 \
    grpcio==1.62.0 \
    grpcio-tools==1.62.0 \
    psycopg2-binary==2.9.9 \
    requests==2.31.0 \
    posix_ipc==1.1.1 \
    fastapi==0.111.0 \
    uvicorn==0.30.1

# 2. Pacotes ML (LightGBM ~2MB, leve e rápido)
RUN pip install --no-cache-dir --timeout=120 \
    numpy==1.26.4 \
    scikit-learn==1.4.2 \
    lightgbm==4.3.0

# Copiar o restante do código fonte do projeto
COPY . .

# Gerar stubs gRPC Python a partir do proto (montado em /app/proto via volume)
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "src/ingestor.py"]
