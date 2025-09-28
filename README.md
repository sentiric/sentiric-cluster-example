# Sentiric Cluster: Docker Compose ile Dağıtık Servis Keşfi (Modüler Yapı)

Bu repo, `sentiric-discovery` (Consul) imajını kullanarak, birden fazla sunucuya (node) yayılmış yüksek erişilebilir (HA) bir servis kümesinin nasıl kurulacağını gösteren modüler ve bakımı kolay bir başlangıç şablonudur.

Bu yapı, "Kendini Tekrar Etme" (DRY) prensibine uygun olarak tasarlanmıştır. Tüm servis tanımları merkezi bir yerde tutulurken, her düğüm sadece kendi yapılandırmasını çalıştırır.

## Mimari

- **Düğüm A (GCP):** `sip-gateway` + `sentiric-discovery`
- **Düğüm B (Antalya Üretim):** `sip-signaling` + `sentiric-discovery`
- **Düğüm C (Antalya Core):** `sip-signaling` + `sentiric-discovery`

Yapılandırma, `.env` dosyaları aracılığıyla yönetilir, bu da IP adreslerini değiştirmeyi kolaylaştırır.

---

## Kurulum Adımları

Aşağıdaki adımları kümedeki **her bir sunucuda** sırasıyla uygulayın.

### Adım 1: Gerekli Yazılımların Kurulumu

Bu adım, `git`, `docker` ve `docker compose`'un (v2) sunucunuzda kurulu olmasını sağlar.

```bash
# Sistem paketlerini güncelle
sudo apt-get update

# Git'i kur
sudo apt-get install git -y

# Docker ve Docker Compose Plugin'ini kurmak için Docker'ın resmi kurulum betiğini kullanın.
# Bu en güvenilir yöntemdir.
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Docker'ı sudo olmadan kullanabilmek için mevcut kullanıcıyı docker grubuna ekleyin.
sudo usermod -aG docker $USER

# Yaptığınız değişikliğin aktif olması için yeni bir shell'e geçin veya sunucuya yeniden bağlanın.
# Örnek:
# newgrp docker
# VEYA sunucudan çıkıp tekrar SSH ile bağlanın.
```
> **Önemli:** `usermod` komutundan sonra değişikliğin etkili olması için terminali kapatıp yeniden açmanız veya sunucuya yeniden bağlanmanız **gereklidir**.

> **Ortak Docker Ağını Oluşturun:**
    ```bash
    docker network create --driver=bridge --subnet=100.64.0.0/16 --gateway=100.64.0.1 sentiric_backbone
    ```

### Adım 2: Repoyu Klonlama ve Yapılandırma

1.  Proje dosyalarını sunucunuza klonlayın:
    ```bash
    git clone https://github.com/sentiric/sentiric-cluster-example.git
    cd sentiric-cluster-example
    ```
2.  Yapılandırma şablonunu kopyalayarak kendi yapılandırma dosyanızı oluşturun:
    ```bash
    cp .env.example .env
    ```
3.  `.env` dosyasını bir metin editörü ile açın ve **sadece o sunucuya ait** olan `CURRENT_NODE_NAME` ve `CURRENT_NODE_IP` değişkenlerini doldurun. Diğer `NODE_*` değişkenlerinin doğru olduğundan emin olun.
    ```bash
    nano .env
    ```

    **Örnek olarak Sunucu A (GCP) için `.env` dosyasının üst kısmı:**
    ```dotenv
    CURRENT_NODE_NAME=node-a-gcp
    CURRENT_NODE_IP=100.107.221.60
    ```

### Adım 3: Düğümleri Başlatma

Aşağıdaki komutları **ilgili sunucularda** çalıştırın. Komutlar projenin kök dizininden çalıştırılmalıdır.

**Node A (GCP) üzerinde:**
```bash
docker compose --env-file .env -f node-a/docker-compose.yml up -d --build 
```

**Node B (Antalya Prod) üzerinde:**
```bash
docker compose --env-file .env -f node-b/docker-compose.yml up -d --build
```

**Node C (Antalya Core) üzerinde:**
```bash
docker compose --env-file .env -f node-c/docker-compose.yml up -d --build
```

### Adım 4: Doğrulama ve Yönetim

#### Küme Durumunu Kontrol Etme
Herhangi bir sunucunun PUBLIC IP adresinden (veya VPN üzerinden BACKBONE IP'sinden) Consul arayüzüne erişin: `http://<sunucu_ip>:8500`

- "Nodes" sekmesinde 3 düğümü de (`node-a-gcp`, `node-b-ant-prod`, `node-c-ant-core`) görmelisiniz.
- "Services" sekmesinde 1 `sip-gateway` ve 2 `sip-signaling` servisi görmelisiniz.

#### Servis Loglarını İzleme
İlgili sunucuda, çalışan servislerin loglarını görmek için:
```bash
docker compose --env-file .env -f node-a/docker-compose.yml logs -f
docker compose --env-file .env -f node-b/docker-compose.yml logs -f
docker compose --env-file .env -f node-c/docker-compose.yml logs -f
```

#### Sistemi Durdurma
İlgili sunucudaki servisleri durdurmak için:
```bash
# Örnek: Node A'daki servisleri durdurma
docker compose -f node-a/docker-compose.yml down
```
---

## Profesyonel Test ve Doğrulama

1.  **Üç terminal açın:**
    - **Terminal 1 (Gateway):** `node-a`'ya bağlanın ve `docker compose -f node-a/docker-compose.yml logs -f` komutunu çalıştırın.
    - **Terminal 2 (Signaler 1):** `node-b`'ye bağlanın ve `docker compose -f node-b/docker-compose.yml logs -f sip-signaling` komutunu çalıştırın.
    - **Terminal 3 (Signaler 2):** `node-c`'ye bağlanın ve `docker compose -f node-c/docker-compose.yml logs -f sip-signaling` komutunu çalıştırın.

2.  **Dördüncü bir terminalden SIP çağrısını gönderin:**
    `nc -u -w 2 -p 5080 <NODE_A_PUBLIC_IP> 5060`
    Komutu yazdıktan sonra SIP mesajınızı girin ve Enter'a basın:
    `REGISTER sip:test@sentiric.cloud SIP/2.0`

3.  **Sonuçları Gözlemleyin:**
    - **Gateway Logları:** Çağrının geldiğini ve en hızlı `signaler`'a yönlendirildiğini göreceksiniz.
    - **Signaler Logları:** Çağrının gittiği sunucuda, mesajın işlendiğini ve cevabın gönderildiğini göreceksiniz.
    - **Çağrı Yapan Terminal:** `SIP/2.0 200 OK...` cevabını alacaksınız.
    - **Consul UI:** `http://<NODE_A_PUBLIC_IP>:8500` adresinde tüm servisler yeşil görünecek.


Bu `README` dosyası artık çok daha eksiksiz ve kullanıcı dostu. Sıfırdan bir sunucuya kurulum yapacak birinin bile sorun yaşama ihtimalini en aza indirir.