FROM python:3.9-slim
WORKDIR /app

# 1. Önce bağımlılıkları kopyala ve root olarak kur. Bu katman sadece
#    requirements.txt değiştiğinde yeniden çalışır, bu da build'leri hızlandırır.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. Ayrıcalıksız kullanıcıyı oluştur.
RUN groupadd -r appgroup && useradd --no-log-init -r -g appgroup appuser

# 3. Uygulama kodunu kopyala ve sahipliğini yeni kullanıcıya ver.
#    COPY --chown komutu, ek bir RUN chown katmanını engeller.
COPY --chown=appuser:appgroup app.py .

# 4. Artık tüm kurulum bittiğine göre, güvenli kullanıcıya geçiş yap.
USER appuser

# 5. Uygulamayı çalıştır.
CMD ["python", "app.py"]