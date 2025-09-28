# Sentiric Cluster: Docker Compose ile Dağıtık Servis Keşfi (Modüler Yapı)

Bu repo, `sentiric-discovery` (Consul) imajını kullanarak, birden fazla sunucuya yayılmış yüksek erişilebilir (HA) bir servis kümesinin nasıl kurulacağını gösteren modüler ve bakımı kolay bir başlangıç şablonudur.

## Kurulum Adımları

### Adım 1: Repoyu Klonlama ve Ortam Değişkenlerini Ayarlama

1.  Bu repoyu **her sunucuya** klonlayın:
    ```bash
    git clone https://github.com/sentiric/sentiric-cluster-example.git
    cd sentiric-cluster-example
    ```
2.  Kök dizindeki `.env.example` dosyasını `.env` olarak kopyalayın:
    ```bash
    cp .env.example .env
    ```
3.  `.env` dosyasını açın ve **sadece o sunucuya ait** olan `CURRENT_NODE_NAME` ve `CURRENT_NODE_IP` değişkenlerini doldurun. Diğer `NODE_*` değişkenlerinin doğru olduğundan emin olun.

    **Örnek olarak Sunucu A (GCP) için `.env` dosyasının üst kısmı:**
    ```dotenv
    CURRENT_NODE_NAME=node-a-gcp
    CURRENT_NODE_IP=100.107.221.60
    ```

### Adım 2: Düğümleri Başlatma

Aşağıdaki komutları ilgili sunucularda çalıştırın. `docker-compose` komutları artık belirli bir düğüm klasöründen değil, **projenin kök dizininden** çalıştırılacak ve hangi `docker-compose.yml` dosyasının kullanılacağı `-f` parametresi ile belirtilecektir.

**Node A (GCP) üzerinde:**
```bash
docker-compose -f node-a/docker-compose.yml up -d --build
```

**Node B (Antalya Prod) üzerinde:**
```bash
docker-compose -f node-b/docker-compose.yml up -d --build
```

**Node C (Antalya Core) üzerinde:**
```bash
docker-compose -f node-c/docker-compose.yml up -d --build
```

### Adım 3: Doğrulama

Herhangi bir sunucunun IP adresinden Consul arayüzüne erişin: `http://<sunucu_ip>:8500`
Kümenizin sağlıklı bir şekilde çalıştığını doğrulayın.
