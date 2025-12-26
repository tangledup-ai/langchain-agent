FROM condaforge/mambaforge:latest

ARG MAMBA_DOCKERFILE_ACTIVATE=1

WORKDIR /app

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Install dependencies in micromamba base env
RUN mamba install -y -c conda-forge \
    python=3.12 \
    pip \
    curl \
    unzip \
    c-compiler \
    cxx-compiler \
    ca-certificates \
    vim \
    && mamba clean -a -y

COPY pyproject.toml ./
COPY lang_agent/ ./lang_agent/
COPY fastapi_server/ ./fastapi_server/



# Install Python dependencies inside micromamba env
RUN python -m pip install --upgrade pip \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    --default-timeout=300 && \
    python -m pip install --no-cache-dir -e . \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    --default-timeout=300

EXPOSE 8588

# Create entrypoint script that initializes conda/mamba and runs the command
RUN echo '#!/bin/bash\n\
set -e\n\
# Initialize conda (mamba uses conda under the hood)\n\
eval "$(conda shell.bash hook)"\n\
conda activate base\n\
# Execute the command\n\
exec "$@"' > /entrypoint.sh && chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["python", "fastapi_server/server_dashscope.py"]