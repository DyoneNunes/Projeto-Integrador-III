🌐 MaaS - Manual do Desenvolvedor (v1.0)
Quilombus Network - High Performance Infrastructure
O Memory as a Service (MaaS) é uma plataforma de infraestrutura que permite alocar e gerenciar memória RAM compartilhada via rede, eliminando o gargalo de disco e latência de APIs tradicionais.

🛠️ 1. O Conceito: Como o MaaS funciona?
Imagine que seu servidor tem uma "mesa" (Memória RAM) gigante. O MaaS é o gerente que reserva um pedaço dessa mesa para você.

Diferente de um banco de dados (onde você salva e busca), no MaaS você anexa seu programa diretamente a esse pedaço de mesa. O dado não viaja; ele simplesmente está lá.

🚀 2. O Fluxo de Utilização (3 Passos)
Passo A: Solicitação (Handshake)
O seu aplicativo pede permissão para usar a memória. Isso é feito via gRPC (Porta 50051) ou via Dashboard:
🌐 **Dashboard:** [http://100.114.106.28:3002/](http://100.114.106.28:3002/)

Entrada: tenant_id e size_bytes.

Saída: Uma shm_key (Ex: /maas_xyz). Essa chave é o endereço físico do seu segmento na RAM do Linux.

Passo B: Conexão (Attach)
Com a chave em mãos, seu código deve "espelhar" esse segmento de memória no seu processo local. No Python, usamos a biblioteca posix_ipc e mmap.

Passo C: Operação (Read/Write)
Agora você escreve e lê bytes diretamente.

Nota: Como o acesso é direto ao hardware, a velocidade é limitada apenas pelo barramento da sua memória RAM (GB/s), não pela sua placa de rede.

💻 3. Exemplo Prático (Python)
Aqui está o "Hello World" para o seu cliente:

Python
import grpc
import mmap
import posix_ipc
import maas_pb2, maas_pb2_grpc

# 1. SOLICITAR (Via gRPC)
channel = grpc.insecure_channel('100.114.106.28:50051')
stub = maas_pb2_grpc.MemoryServiceStub(channel)

request = maas_pb2.AllocateRequest(tenant_id="Quilombus_App", size_bytes=1048576) # 1MB
response = stub.Allocate(request)

print(f"Memória reservada! Chave: {response.shm_key}")

# 2. CONECTAR E USAR (Via POSIX SHM)
memory = posix_ipc.SharedMemory(response.shm_key)
map_file = mmap.mmap(memory.fd, memory.size)

# Escrevendo dados
map_file.write(b"MaaS: Latencia zero para a Quilombus!")
map_file.seek(0)
print(f"Conteudo lido da RAM: {map_file.read(36).decode()}")
⚠️ 4. Regras de Ouro
Persistência: Se o servidor MaaS reiniciar, a memória (RAM) é limpa. Use para dados voláteis e de alta velocidade.

Segurança: Nunca compartilhe sua shm_key com outros Tenants.

Liberação: Sempre chame o DEALLOCATE ao terminar para devolver a RAM ao sistema e não causar "Memory Leak" no servidor de 6GB.