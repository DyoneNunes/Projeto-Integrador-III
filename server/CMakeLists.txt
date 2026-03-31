cmake_minimum_required(VERSION 3.20)
project(maas-core
    VERSION   0.1.0
    LANGUAGES CXX
)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# =============================================================================
# Flags de compilação orientadas a performance
# =============================================================================
add_compile_options(
    -Wall -Wextra -Wpedantic
    -O2
    -march=native
    -fno-omit-frame-pointer   # Facilita profiling com perf
)

# =============================================================================
# Dependências: gRPC, Protobuf, libpq (PostgreSQL), Threads
# =============================================================================
find_package(Threads REQUIRED)
find_package(PkgConfig REQUIRED)
find_package(Protobuf REQUIRED)

pkg_check_modules(GRPC REQUIRED grpc++ grpc)
pkg_check_modules(LIBPQ REQUIRED libpq)

# =============================================================================
# Geração de código Protobuf + gRPC a partir de maas.proto
# =============================================================================
set(PROTO_SRC_DIR "${CMAKE_SOURCE_DIR}/../proto")
set(PROTO_FILE    "${PROTO_SRC_DIR}/maas.proto")
set(PROTO_GEN_DIR "${CMAKE_BINARY_DIR}/generated")
file(MAKE_DIRECTORY ${PROTO_GEN_DIR})

# Localiza os plugins
find_program(GRPC_CPP_PLUGIN grpc_cpp_plugin)

# Comando customizado para gerar .pb.cc/.pb.h e .grpc.pb.cc/.grpc.pb.h
add_custom_command(
    OUTPUT
        "${PROTO_GEN_DIR}/maas.pb.cc"
        "${PROTO_GEN_DIR}/maas.pb.h"
        "${PROTO_GEN_DIR}/maas.grpc.pb.cc"
        "${PROTO_GEN_DIR}/maas.grpc.pb.h"
    COMMAND protobuf::protoc
        --proto_path=${PROTO_SRC_DIR}
        --cpp_out=${PROTO_GEN_DIR}
        --grpc_out=${PROTO_GEN_DIR}
        --plugin=protoc-gen-grpc=${GRPC_CPP_PLUGIN}
        ${PROTO_FILE}
    DEPENDS ${PROTO_FILE}
    COMMENT "Gerando stubs C++ a partir de maas.proto"
)

# =============================================================================
# Executável principal
# =============================================================================
add_executable(maas-core
    main.cpp
    ${PROTO_GEN_DIR}/maas.pb.cc
    ${PROTO_GEN_DIR}/maas.grpc.pb.cc
)

target_include_directories(maas-core PRIVATE
    ${PROTO_GEN_DIR}
    ${GRPC_INCLUDE_DIRS}
    ${Protobuf_INCLUDE_DIRS}
    ${LIBPQ_INCLUDE_DIRS}
)

target_link_libraries(maas-core PRIVATE
    ${GRPC_LIBRARIES}
    ${Protobuf_LIBRARIES}
    ${LIBPQ_LIBRARIES}
    Threads::Threads
    rt      # POSIX shared memory (shm_open, shm_unlink)
)

target_link_directories(maas-core PRIVATE
    ${GRPC_LIBRARY_DIRS}
    ${LIBPQ_LIBRARY_DIRS}
)
