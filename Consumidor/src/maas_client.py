import grpc
import os
import sys

# Importa stubs gRPC
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import maas_pb2
import maas_pb2_grpc

class MaaSMemory:
    """
    Abstração para acesso à memória MaaS via rede (gRPC).
    Implementa uma interface similar ao mmap para facilitar a migração.
    """
    def __init__(self, stub, allocation_id, size):
        self.stub = stub
        self.allocation_id = allocation_id
        self.size = size
        self.pos = 0

    def seek(self, offset):
        if offset < 0 or offset >= self.size:
            raise ValueError("Offset fora dos limites da memória alocada.")
        self.pos = offset

    def write(self, data):
        """Escreve bytes na memória remota via gRPC WriteMemory."""
        if self.pos + len(data) > self.size:
            raise ValueError("Tentativa de escrita além dos limites da memória.")
        
        request = maas_pb2.WriteRequest(
            allocation_id=self.allocation_id,
            offset=self.pos,
            data=data
        )
        # Chamada bloqueante para garantir ordem de escrita
        self.stub.WriteMemory(request)
        self.pos += len(data)

    def read(self, size_bytes):
        """Lê bytes da memória remota via gRPC ReadMemory."""
        if self.pos + size_bytes > self.size:
            size_bytes = self.size - self.pos # Lê até o final
        
        if size_bytes <= 0:
            return b""

        request = maas_pb2.ReadRequest(
            allocation_id=self.allocation_id,
            offset=self.pos,
            size_bytes=size_bytes
        )
        response = self.stub.ReadMemory(request)
        self.pos += len(response.data)
        return response.data

    def close(self):
        pass # gRPC não requer fechar o descriptor de arquivo
