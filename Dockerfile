FROM python:3.12-slim
ARG VERSION=1.2.0
LABEL org.opencontainers.image.title="podcast-rss" \
      org.opencontainers.image.version="${VERSION}"
WORKDIR /app
COPY server.py Razorcakepodcast.jpg ./
CMD ["python3", "server.py"]
