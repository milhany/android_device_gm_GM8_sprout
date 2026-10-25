FROM ubuntu:24.04
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ca-certificates git python3 make gcc g++ clang-18 lld-18 llvm-18 \
    gcc-aarch64-linux-gnu gcc-arm-linux-gnueabihf \
    bison flex bc cpio perl openssl pkg-config libssl-dev libelf-dev zlib1g-dev \
    device-tree-compiler xz-utils \
    && rm -rf /var/lib/apt/lists/*
ENV PATH="/usr/lib/llvm-18/bin:${PATH}"
WORKDIR /work
ENTRYPOINT ["python3", "/port/tools/kernel419.py"]
