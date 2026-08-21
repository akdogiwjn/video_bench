FROM ubuntu-document-bench:24.04-linuxarm64-optimized-py3123

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg git curl wget unzip ca-certificates build-essential \
    libsndfile1 libgl1 libglib2.0-0 \
    libsm6 libxext6 libxrender1 libxkbcommon0 \
    fonts-dejavu fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /opt/openstoryline

COPY FireRed-OpenStoryline-main/ /opt/openstoryline/

RUN pip3 install --no-cache-dir --no-deps torch torchaudio 2>&1 || \
    pip3 install --no-cache-dir torch torchaudio 2>&1 || true

RUN pip3 install --no-cache-dir numpy typing-extensions sympy networkx jinja2 fsspec filelock

RUN cd /opt/openstoryline && \
    pip3 install --no-cache-dir -r requirements.txt 2>&1 || \
    pip3 install --no-cache-dir \
    fastapi uvicorn langchain langchain-core langchain-openai langchain-community \
    langchain-huggingface langchain-mcp-adapters mcp colorlog librosa \
    transnetv2_pytorch moviepy av ffmpeg-python aiofiles skillkit \
    sentence-transformers faiss-cpu openai emoji tomli

RUN cd /opt/openstoryline && \
    if [ ! -f .storyline/models/transnetv2-pytorch-weights.pth ]; then \
        bash download.sh || echo "[WARN] download.sh failed, weights need manual download"; \
    fi

RUN mkdir -p /opt/video-tools

RUN ln -sf /opt/openclaw/bin/openclaw /usr/local/bin/openclaw 2>/dev/null || true

ENV PYTHONPATH=/opt/openstoryline:/opt/openstoryline/src
ENV OPENSTORYLINE_REPO=/opt/openstoryline
ENV ADAPTER_DIR=/opt/video-tools

WORKDIR /workspace

CMD ["python3", "-c", "print('OpenStoryline image ready')"]
