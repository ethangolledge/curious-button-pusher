# SAM 3D Objects and SAM 3D Body, for one Cloud Run GPU job (README.md). Code only: the weights
# are in a private bucket, mounted at run time. Everything that comes from outside is pinned:
# base images by digest, Python packages by hash (requirements.lock), source by commit, a patch
# file by checksum (sources.sha256). No secret is used to build it, and none is in it.

# The CUDA the authors built against (12.1); L4 GPUs (compute capability 8.9) run it.
ARG CUDA_DEVEL=nvidia/cuda:12.1.1-devel-ubuntu22.04@sha256:7012e535a47883527d402da998384c30b936140c05e2537158c80b8143ee7425
ARG CUDA_RUNTIME=nvidia/cuda:12.1.1-runtime-ubuntu22.04@sha256:8bbc6e304b193e84327fa30d93eea70ec0213b808239a46602a919a479a73b12
ARG UV=ghcr.io/astral-sh/uv:0.11.3@sha256:90bbb3c16635e9627f49eec6539f956d70746c409209041800a0280b93152823

FROM ${UV} AS uv

# ---- build: compile the CUDA extensions and fill one virtual environment ----
FROM ${CUDA_DEVEL} AS build
ARG TORCH_CUDA_ARCH_LIST="8.9"
ENV TORCH_CUDA_ARCH_LIST=${TORCH_CUDA_ARCH_LIST} FORCE_CUDA=1 MAX_JOBS=4 \
    UV_PYTHON_INSTALL_DIR=/opt/python UV_NO_CACHE=1 UV_COMPILE_BYTECODE=1 UV_HTTP_RETRIES=8 \
    VIRTUAL_ENV=/opt/venv PATH=/opt/venv/bin:$PATH
RUN apt-get update && apt-get install -y --no-install-recommends git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=uv /uv /usr/local/bin/uv
RUN uv python install 3.11.15 && uv venv --python 3.11.15 /opt/venv

COPY requirements.lock /tmp/requirements.lock
RUN uv pip sync --require-hashes --index-strategy unsafe-best-match /tmp/requirements.lock

# From git, each at the commit sam-3d-objects names; their dependencies are in the lock.
RUN uv pip install --no-deps --no-build-isolation \
      "git+https://github.com/facebookresearch/pytorch3d.git@75ebeeaea0908c5527e7b1e305fbc7681382db47" \
      "git+https://github.com/nerfstudio-project/gsplat.git@2323de5905d5e90e035f792fe65bad0fedd413e7" \
      "git+https://github.com/microsoft/MoGe.git@a8c37341bc0325ca99b9d57981cc3bb2bd3e255b" \
      "git+https://github.com/EasternJournalist/utils3d.git@3913c65d81e05e47b9f367250cf8c0f7462a0900"

# The models' own code, the two backbones they load through torch.hub, and the fix to hydra that
# sam-3d-objects applies (its patching/hydra): each at a fixed commit, checked by hash before
# use. Only code is kept from the archives, not their demo pictures.
COPY sources.sha256 /tmp/sources.sha256
RUN <<EOF
set -eu
gh=https://github.com/facebookresearch
get() { curl -fsSL --retry 5 --retry-all-errors -o "/tmp/$1" "$2"; }
get objects.tar.gz $gh/sam-3d-objects/archive/f91db411c50efee93d8db7aeb323885650f6f722.tar.gz
get body.tar.gz $gh/sam-3d-body/archive/b5c765a0d89d789985e186d396315e7590887b94.tar.gz
get dinov2.tar.gz $gh/dinov2/archive/7764ea0f912e53c92e82eb78a2a1631e92725fc8.tar.gz
get dinov3.tar.gz $gh/dinov3/archive/6876159a11b4df116f30f667f8c9888617df0751.tar.gz
get hydra-utils.py https://raw.githubusercontent.com/gleize/hydra/78f00766b5f37672aa7232ebbf01bdd74246bd60/hydra/core/utils.py
cd /tmp && sha256sum --check --strict sources.sha256
mkdir -p /opt/src/objects /opt/src/body /opt/hub/dinov2 /opt/hub/dinov3
tar -xzf objects.tar.gz -C /opt/src/objects --strip-components 1 --wildcards '*/sam3d_objects'
tar -xzf body.tar.gz -C /opt/src/body --strip-components 1 --wildcards '*/sam_3d_body'
tar -xzf dinov2.tar.gz -C /opt/hub/dinov2 --strip-components 1
tar -xzf dinov3.tar.gz -C /opt/hub/dinov3 --strip-components 1
cp hydra-utils.py /opt/venv/lib/python3.11/site-packages/hydra/core/utils.py
rm /tmp/*.tar.gz /tmp/hydra-utils.py
EOF

# ---- runtime: no compilers, no git, no package manager caches ----
FROM ${CUDA_RUNTIME}
# open3d needs OpenGL and OpenMP's libraries to import, even with no display.
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin sam3d
COPY --from=build /opt/python /opt/python
COPY --from=build /opt/venv /opt/venv
COPY --from=build /opt/src /opt/src
COPY --from=build /opt/hub /opt/hub
COPY models.json /opt/app/models.json
COPY sam3d /opt/app/sam3d

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/opt/app:/opt/src/objects:/opt/src/body \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    HF_HUB_CACHE=/weights/hf HF_HUB_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 \
    TORCH_HOME=/weights/torch \
    LIDRA_SKIP_INIT=true MOMENTUM_ENABLED=0 \
    HOME=/tmp
RUN python -m sam3d check
USER 10001:10001
ENTRYPOINT ["python", "-m", "sam3d"]
