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
COPY fastapi_server/requirements.txt ./fastapi_server/
COPY lang_agent/ ./lang_agent/
COPY fastapi_server/ ./fastapi_server/

# RUN curl -o ./.env http://6.6.6.86:8888/download/resources/.env 
    # && \
    # curl -o ./assets.zip http://6.6.6.86:8888/download/resources/assets.zip && \
    # unzip assets.zip && \
    # rm assets.zip

# Install Python dependencies inside micromamba env
RUN python -m pip install --upgrade pip && \
    python -m pip install --no-cache-dir -r fastapi_server/requirements.txt \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    --default-timeout=300 && \
    python -m pip install --no-cache-dir -e . \
    -i https://mirrors.aliyun.com/pypi/simple/ \
    --trusted-host mirrors.aliyun.com \
    --default-timeout=300

EXPOSE 8488

CMD ["micromamba", "run", "-n", "base", "python", "fastapi_server/server_dashscope.py"]