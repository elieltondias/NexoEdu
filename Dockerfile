FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git git-lfs && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY . .
EXPOSE 8501
CMD ["python", "-m", "streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
