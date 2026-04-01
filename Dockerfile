FROM node:20-bookworm-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    ffmpeg \
    zsh \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set up the Python virtual environment
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python package dependencies
RUN pip install google-api-python-client google-auth google-auth-httplib2 google-auth-oauthlib requests

# Install n8n globally (the slim image has full npm support)
RUN npm install -g n8n --no-fund --no-audit && npm cache clean --force

# In the docker-compose file it sets 'user: root', so we remain root
# and start the n8n process automatically
CMD ["n8n", "start"]
