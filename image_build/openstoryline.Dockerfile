FROM ubuntu-document-bench:24.04-linuxarm64-optimized-py3123

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg git curl wget unzip ca-certificates build-essential \
    libsndfile1 libgl1 libglib2.0-0 \
    libsm6 libxext6 libxrender1 libxkbcommon0 \
    fonts-dejavu fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /opt/openstoryline

# Copy from local frozen snapshot (commit tracked via SHA256 in source_manifest.json)
COPY FireRed-OpenStoryline-main/ /opt/openstoryline/

# Install pinned requirements
RUN cd /opt/openstoryline && \
    pip3 install --no-cache-dir -r requirements.txt

# Install torch CPU-only — pinned, NO fallback (#10 fix)
RUN pip3 install --no-cache-dir --no-deps torch==2.13.0 torchaudio==2.13.0
RUN pip3 install --no-cache-dir numpy typing-extensions sympy networkx jinja2 fsspec filelock

# Download model weights — FAIL if download fails (no warning bypass)
RUN cd /opt/openstoryline && \
    if [ ! -f .storyline/models/transnetv2-pytorch-weights.pth ]; then \
        bash download.sh; \
    fi && \
    test -f .storyline/models/transnetv2-pytorch-weights.pth || \
    (echo "[ERROR] TransNetV2 weights missing" && exit 1)

# COPY adapters into image (#13 fix)
COPY video_bench/adapters/openstoryline/ /opt/video-tools/
RUN chmod +x /opt/video-tools/*.py

# OpenClaw symlink (mounted at runtime)
RUN ln -sf /opt/openclaw/bin/openclaw /usr/local/bin/openclaw 2>/dev/null || true

ENV PYTHONPATH=/opt/openstoryline:/opt/openstoryline/src
ENV OPENSTORYLINE_REPO=/opt/openstoryline
ENV ADAPTER_DIR=/opt/video-tools

WORKDIR /workspace

CMD ["python3", "-c", "print('OpenStoryline image ready')"]
