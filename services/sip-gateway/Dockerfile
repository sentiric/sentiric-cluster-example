FROM python:3.9-slim
WORKDIR /app

# Güvenlik: Ayrıcalıksız bir kullanıcı oluştur ve kullan
RUN groupadd -r appgroup && useradd --no-log-init -r -g appgroup appuser
USER appuser

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
CMD ["python", "app.py"]