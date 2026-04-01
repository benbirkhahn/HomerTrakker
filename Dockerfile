FROM n8nio/n8n:latest
USER root
RUN apk add --update --no-cache python3 py3-pip ffmpeg zsh
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install google-api-python-client google-auth google-auth-httplib2 google-auth-oauthlib requests
USER node
