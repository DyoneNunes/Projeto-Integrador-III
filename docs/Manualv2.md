📘 Manual do Usuário: Como utilizar o MaaS
O Memory as a Service (MaaS) não é um banco de dados comum; é uma extensão da memória RAM do seu servidor disponível via rede. Para usar, você segue três fases:

1. O Contrato (Solicitação)
Ninguém acessa a memória sem permissão. O primeiro passo é pedir um "pedaço" de RAM ao servidor MaaS.

O que o usuário faz: Envia uma requisição gRPC (ou via Dashboard) dizendo: "Sou o inquilino (Tenant) X e preciso de Y megabytes".

O que o MaaS devolve: Uma SHM Key (ex: /maas_7f6cfca9). Guarde essa chave, ela é o seu "crachá" de acesso ao hardware.

2. O Vínculo (Attach)
Com a chave em mãos, o seu programa precisa "enxergar" essa memória que está lá no Kernel do Linux.

Como funciona: Você usa uma biblioteca de Shared Memory (como posix_ipc no Python ou shmget em C).

A Mágica: O seu sistema operacional mapeia aquele pedaço de RAM do MaaS diretamente no espaço de endereçamento do seu programa. É como se você tivesse espetado um pente de memória extra via software.

3. A Operação (Leitura e Escrita)
Agora que o vínculo existe, você não usa print ou send. Você usa ponteiros ou memmaps.

Velocidade: Como o dado está na RAM, a leitura é instantânea. Se você escrever "Olá" na posição 0x01, qualquer outro programa autorizado que ler a posição 0x01 verá o "Olá" no mesmo microssegundo, sem passar por cabos de rede ou discos rígidos.

🛠️ Exemplo Prático (O que o usuário digita)
Para o seu manual de entrega (C2), o usuário faria algo assim no Python:

Python
# 1. Solicita (via gRPC)
# "Ei MaaS, me dá 1MB?" -> Recebe "/maas_teste"

# 2. Conecta (via POSIX)
import mmap, posix_ipc
memory = posix_ipc.SharedMemory("/maas_teste")
map_file = mmap.mmap(memory.fd, memory.size)

# 3. Usa!
map_file.write(b"Dados da Quilombus")