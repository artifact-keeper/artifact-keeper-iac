FROM ghcr.io/actions/actions-runner:latest

USER root

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential pkg-config libssl-dev curl git jq zip unzip \
    protobuf-compiler ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Rust stable with clippy and rustfmt
ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH=/usr/local/cargo/bin:$PATH
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | \
    sh -s -- -y --default-toolchain stable --component clippy,rustfmt --profile minimal && \
    rustup --version && rustc --version && cargo --version

# Install sccache
RUN cargo install sccache --locked && sccache --version

# Install cargo-llvm-cov for coverage
RUN curl -LsSf https://github.com/taiki-e/cargo-llvm-cov/releases/latest/download/cargo-llvm-cov-x86_64-unknown-linux-gnu.tar.gz | \
    tar xzf - -C /usr/local/cargo/bin

# Install cargo-audit for security scanning
RUN curl -LsSf https://github.com/rustsec/rustsec/releases/latest/download/cargo-audit-x86_64-unknown-linux-gnu-v0.21.2.tgz | \
    tar xzf - -C /usr/local/cargo/bin 2>/dev/null || cargo install cargo-audit --locked

# Install Docker Compose plugin
RUN mkdir -p /usr/local/lib/docker/cli-plugins && \
    curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
    -o /usr/local/lib/docker/cli-plugins/docker-compose && \
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Pre-seed the cargo registry sparse index
RUN cargo search --limit 1 serde 2>/dev/null || true

# Clean up cargo install artifacts to reduce image size
RUN rm -rf /usr/local/cargo/registry/cache /usr/local/cargo/registry/src /tmp/*

USER runner
