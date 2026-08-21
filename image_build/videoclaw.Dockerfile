FROM ubuntu-document-bench:24.04-linuxarm64-optimized-py3123

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg git curl ca-certificates build-essential \
    libsndfile1 libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /opt/videoclaw

COPY VideoClaw-1324b36020570c279cd9560794a8f5508bf7bb70/video-claw/video-claw/backend/ /opt/videoclaw/backend/
COPY VideoClaw-1324b36020570c279cd9560794a8f5508bf7bb70/video-claw/SKILL.md /opt/videoclaw/SKILL.md
COPY VideoClaw-1324b36020570c279cd9560794a8f5508bf7bb70/video-claw/references/ /opt/videoclaw/references/
COPY video_bench/image_build/videoclaw-entrypoint.sh /opt/videoclaw/entrypoint.sh
RUN chmod +x /opt/videoclaw/entrypoint.sh

RUN cd /opt/videoclaw/backend && \
    sed -i '/playwright/d' requirements.txt && \
    pip3 install --no-cache-dir -r requirements.txt

RUN cd /opt/videoclaw/backend && \
    cp config.yaml.example config.yaml && \
    sed -i 's/host: 127.0.0.1/host: 0.0.0.0/' config.yaml

RUN ln -sf /opt/openclaw/bin/openclaw /usr/local/bin/openclaw 2>/dev/null || true

ENV PYTHONPATH=/opt/videoclaw/backend
ENV VIDEOCLAW_REPO=/opt/videoclaw

EXPOSE 8000

HEALTHCHECK --interval=5s --timeout=3s --retries=3 \
    CMD curl -sf http://localhost:8000/api/health || exit 1

CMD ["/opt/videoclaw/entrypoint.sh"]
