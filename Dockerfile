# ./Dockerfile
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install system libraries and tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl \
        wget \
        gpg \
        gnupg \
        ca-certificates \
        unzip \
        libx11-xcb1 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libasound2 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdbus-1-3 \
        libgdk-pixbuf2.0-0 \
        libgtk-3-0 \
        libnspr4 \
        libnss3 \
        libxss1 \
        libxtst6 \
        x11-xserver-utils \
        x11-utils \
        dbus-x11 \
        python3 \
        python3-pip \
        python3-venv && \
    ln -s /usr/bin/python3 /usr/bin/python && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN apt-get update && apt-get install -y --no-install-recommends xvfb

RUN apt-get update && apt-get install -y --no-install-recommends \
    xauth \
    xfonts-base

# Install Node.js 18.x and npm
RUN curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /usr/share/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/nodesource.gpg] https://deb.nodesource.com/node_18.x nodistro main" > /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && apt-get install -y nodejs

# Install full VS Code GUI Desktop manually
RUN wget -O vscode.deb https://update.code.visualstudio.com/latest/linux-deb-x64/stable && \
    apt-get update && apt-get install -y ./vscode.deb && \
    rm vscode.deb

RUN printf '%s\n' \
    '#!/usr/bin/env bash' \
    'export NO_AT_BRIDGE=1' \
    'export DBUS_SESSION_BUS_ADDRESS=/dev/null' \
    'export DBUS_SYSTEM_BUS_ADDRESS=/dev/null' \
    '' \
    '# Run VS Code under Xvfb and drop only the DBus chatter' \
    'exec xvfb-run -a /usr/share/code/code --no-sandbox "$@" \\' \
    '     2> >(grep -v "Failed to connect to the bus")' \
    > /usr/local/bin/code-gui && chmod +x /usr/local/bin/code-gui
    
# Set working directory
WORKDIR /Final\ Project

# Copy your application files
COPY CreateMutants/ ./CreateMutants/
COPY Extension/airflow-vscode-extension-main ./Extension/airflow-vscode-extension-main
COPY Extension/airflow-snippets-main ./Extension/airflow-snippets-main
COPY ExtensionFuzzerCommunication/ ./ExtensionFuzzerCommunication/
COPY FilterMutants/ ./FilterMutants/
COPY FuzzingHarness/ ./FuzzingHarness/
COPY Guidance/ ./Guidance/
COPY SnippetFuzzer/ ./SnippetFuzzer/
COPY extensionMutationFuzzer.py ./
COPY Logging/createLogsAndBackups.py ./Logging/
COPY requirements.txt .
COPY CustomExtension/  ./CustomExtension/

# Clean up any __pycache__ dirs
RUN find . -type d -name '__pycache__' -exec rm -rf {} +

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose Flask or app port
EXPOSE 5000

# Launch interactive shell
CMD ["/bin/bash"]
