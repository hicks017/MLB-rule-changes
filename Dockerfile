# -------- Dockerfile for MLB-rule-changes project --------

# Define versions
ARG R_VERSION=4.4.3

FROM rocker/r-ver:${R_VERSION}

# Redefine build args after FROM for Docker compatibility
ARG QUARTO_VERSION=1.7.32

# Suppress prompts and update system
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update -qq && \
    apt-get upgrade -y -qq && \
    apt-get install -y -qq \
        sudo curl wget git python3 python3-pip python3-venv \
        libcurl4-openssl-dev libssl-dev libxml2-dev libgit2-dev \
        libharfbuzz-dev libfribidi-dev libfreetype6-dev \
        libpng-dev libtiff5-dev libjpeg-dev gdebi-core && \
    rm -rf /var/lib/apt/lists/*

# Set up Python virtual environment and install dependencies
COPY requirements.txt ./
RUN python3 -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# Install Quarto CLI
RUN wget -q https://github.com/quarto-dev/quarto-cli/releases/download/v${QUARTO_VERSION}/quarto-${QUARTO_VERSION}-linux-amd64.deb \
    && sudo gdebi -n quarto-${QUARTO_VERSION}-linux-amd64.deb \
    && rm quarto-${QUARTO_VERSION}-linux-amd64.deb

# Ensure the venv is on PATH for all users
ENV PATH="/opt/venv/bin:$PATH"

# Install R packages used in the project
RUN Rscript -e "install.packages(c('languageserver', 'readr', 'dplyr', 'skimr', 'ggplot2', 'broom', 'gtsummary', 'tidyr', 'lubridate', 'tibble', 'ggsignif'))"

# Set up non-root user for development
RUN useradd -ms /bin/bash devuser
USER devuser
WORKDIR /workspaces/mlb-rule-changes

# Set default command
CMD ["bash"]
