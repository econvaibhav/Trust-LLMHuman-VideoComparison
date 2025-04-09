FROM python:3.12-slim
WORKDIR /app
COPY videotrust /app/videotrust
RUN useradd --create-home researcher && mkdir /data && chown researcher:researcher /data
USER researcher
EXPOSE 8000
CMD ["python", "-m", "videotrust", "demo", "--workspace", "/data/demo", "--host", "0.0.0.0", "--port", "8000"]
