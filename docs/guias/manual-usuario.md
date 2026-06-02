# Manual do Usuário

O MaaS **não é um banco de dados**: é uma extensão da RAM do servidor disponível pela rede. Usá-lo envolve três fases.

## 1. O Contrato (solicitação)

Peça um bloco de memória ao servidor — via **gRPC** (porta `50051`) ou pelo **Dashboard** (<http://localhost:3002>).

- **Entrada:** `tenant_id` e `size_bytes`.
- **Saída:** uma `shm_key` (ex.: `/maas_7f6cfca9`) — o "crachá" de acesso ao seu segmento na RAM.

## 2. O Vínculo (attach)

Com a chave, seu programa mapeia esse segmento no próprio espaço de endereçamento. No Python, usa-se `posix_ipc` + `mmap`:

```python
import mmap, posix_ipc

memory = posix_ipc.SharedMemory("/maas_7f6cfca9")
map_file = mmap.mmap(memory.fd, memory.size)
```

!!! tip "Local vs. remoto"
    O *attach* via `posix_ipc` só funciona se você está na **mesma máquina** do Core. Se for um cliente **remoto**, use as RPCs `WriteMemory` / `ReadMemory` (veja o [Contrato gRPC](../api-grpc.md)).

## 3. A Operação (leitura e escrita)

Agora você escreve e lê bytes diretamente — sem `send`/`recv`, sem disco:

```python
map_file.write(b"MaaS: latencia zero!")
map_file.seek(0)
print(map_file.read(20).decode())
```

A velocidade é limitada pelo **barramento de RAM** (GB/s), não pela rede.

## Exemplo completo (gRPC + attach local)

```python
import grpc, mmap, posix_ipc, maas_pb2, maas_pb2_grpc

# 1) Solicitar
channel = grpc.insecure_channel("localhost:50051")
stub = maas_pb2_grpc.MemoryServiceStub(channel)
resp = stub.Allocate(maas_pb2.AllocateRequest(tenant_id="meu-app", size_bytes=1048576))
print("Chave:", resp.shm_key)

# 2) Conectar
memory = posix_ipc.SharedMemory(resp.shm_key)
map_file = mmap.mmap(memory.fd, memory.size)

# 3) Usar
map_file.write(b"Ola, MaaS!")

# 4) Liberar (sempre!)
stub.Deallocate(maas_pb2.DeallocateRequest(
    tenant_id="meu-app", allocation_id=resp.allocation_id))
```

## Regras de ouro

!!! danger "Persistência"
    A memória é **volátil**. Se o Core reiniciar, o conteúdo é perdido. Use o MaaS para dados de **alta velocidade e curta duração**.

!!! warning "Segurança"
    Nunca compartilhe sua `shm_key` com outros tenants. As RPCs `Write/Read` validam o `tenant_id`.

!!! note "Liberação"
    Sempre chame `Deallocate` ao terminar — isso devolve a RAM ao sistema e evita *memory leak* no servidor.
