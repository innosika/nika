FROM ubuntu:noble AS base

ENV CCACHE_DIR=/ccache
USER root

COPY scripts /nika/scripts
COPY conanfile.py /nika/conanfile.py
COPY CMakePresets.json /nika/CMakePresets.json
COPY CMakeLists.txt /nika/CMakeLists.txt
COPY requirements.txt /nika/requirements.txt

# tini is an init system to forward interrupt signals properly
RUN apt update && apt install -y --no-install-recommends sudo tini curl ccache python3 python3-pip pipx cmake build-essential ninja-build

# Install Conan
RUN pipx install conan && \
    pipx ensurepath

FROM base AS devdeps
WORKDIR /nika

SHELL ["/bin/bash", "-c"]
RUN python3 -m venv /nika/.venv && \
    source /nika/.venv/bin/activate && \
    pip3 install -r /nika/requirements.txt

ENV PATH="/root/.local/bin:$PATH"

# Where sc-machine and scl-machine come from at build time:
#   release (default) - the GitHub release archives unpacked into install/ below. The C++
#                       modules are compiled and run against the very same binaries, and
#                       the build does not depend on conan.ostis.net at all (that server is
#                       unreachable since September 2026).
#   conan             - the ostis-ai Conan remote, as upstream does. Add
#                       CONAN_INSECURE_REMOTE=1 if its TLS certificate is expired again.
ARG OSTIS_DEPS=release
ARG CONAN_INSECURE_REMOTE=0
ENV NIKA_OSTIS_DEPS=${OSTIS_DEPS}

# Versions must match the sc-machine/scl-machine requirements in conanfile.py.
ARG SC_MACHINE_VERSION=0.10.4
ARG SCL_MACHINE_VERSION=0.3.1

# Install sc-machine binaries (headers and CMake package are kept: the modules build against them)
RUN curl -fLO https://github.com/ostis-ai/sc-machine/releases/download/${SC_MACHINE_VERSION}/sc-machine-${SC_MACHINE_VERSION}-Linux.tar.gz && \
    mkdir -p install/sc-machine && tar -xzf sc-machine-${SC_MACHINE_VERSION}-Linux.tar.gz -C install/sc-machine --strip-components 1 && \
    rm -f sc-machine-${SC_MACHINE_VERSION}-Linux.tar.gz

# Install scl-machine libraries
RUN curl -fLO https://github.com/ostis-ai/scl-machine/releases/download/${SCL_MACHINE_VERSION}/scl-machine-${SCL_MACHINE_VERSION}-Linux.tar.gz && \
    mkdir -p install/scl-machine && tar -xzf scl-machine-${SCL_MACHINE_VERSION}-Linux.tar.gz -C install/scl-machine --strip-components 1 && \
    rm -f scl-machine-${SCL_MACHINE_VERSION}-Linux.tar.gz

RUN conan profile detect && \
    if [ "$OSTIS_DEPS" = "conan" ]; then \
        if [ "$CONAN_INSECURE_REMOTE" = "1" ]; then INSECURE_FLAG="--insecure"; fi; \
        conan remote add ostis-ai https://conan.ostis.net/artifactory/api/conan/ostis-ai-library $INSECURE_FLAG; \
    fi && \
    conan install . --build=missing

FROM devdeps AS devcontainer
RUN apt install -y --no-install-recommends cppcheck valgrind gdb bash-completion ninja-build curl
ENTRYPOINT ["/bin/bash"]

FROM devdeps AS builder
COPY . .
RUN --mount=type=cache,target=/ccache/ \
    if [ "$NIKA_OSTIS_DEPS" = "release" ]; then PREFIX_ARG="-DCMAKE_PREFIX_PATH=/nika/install/sc-machine;/nika/install/scl-machine"; fi && \
    cmake --preset release-conan ${PREFIX_ARG:+"$PREFIX_ARG"} && cmake --build --preset release

# Gathering all artifacts together
FROM devdeps AS final

COPY --from=builder /nika/scripts /nika/scripts
COPY --from=builder /nika/install /nika/install
COPY --from=builder /nika/build/Release /nika/build/Release
COPY --from=builder /nika/.venv /nika/.venv

WORKDIR /nika

EXPOSE 8090

ENTRYPOINT ["/usr/bin/tini", "--", "/nika/scripts/docker_entrypoint.sh"]
