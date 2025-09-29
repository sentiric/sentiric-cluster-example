# Sentiric Cluster: Dağıtık ve Yüksek Erişilebilir SIP Yönlendirme Platformu

Bu proje, **HashiCorp Consul** ile servis keşfi ve **dinamik latency tabanlı yönlendirme** konularını bir araya getirerek, coğrafi olarak dağıtık bir SIP altyapısının nasıl kurulacağını gösteren profesyonel bir referans uygulamasıdır.

Mimari, kafa karışıklığını ortadan kaldırmak için en modern ve güvenli yöntemler üzerine kurulmuştur: **Overlay Network (Tailscale)** ve **İzole Docker Ağları**.

## Nihai Mimari

- **Ağ Omurgası (Overlay Network):** Tüm sunucular (Node A, B, C), [Tailscale](https://tailscale.com/) aracılığıyla sanal bir özel ağa (VPN) bağlanır. Bu sayede her sunucu, `100.x.x.x` formatında sabit ve güvenli bir IP adresine sahip olur. Sunucular arası tüm cluster iletişimi bu şifreli tünel üzerinden yapılır.
- **Uygulama İzolasyonu (Docker Network):** Her sunucuda, `docker-compose` kendi özel ağını oluşturur. Konteynerler bu ağ içinde birbirleriyle servis isimleri (`consul-server`, `sip-gateway`) üzerinden haberleşir. Dış dünyaya sadece gerekli portlar açılır.

**Sistem Bileşenleri:**
- **Node A (GCP):** `sip-gateway` + `consul-server`. Gelen tüm SIP çağrılarını karşılar.
- **Node B (On-Premise Prod):** `sip-signaling` + `consul-server`. Çağrı işleme sunucusu.
- **Node C (On-Premise Core):** `sip-signaling` + `consul-server`. Yedek çağrı işleme sunucusu.

**İş Akışı:** `sip-gateway`, Consul'den sağlıklı `sip-signaling` sunucularının listesini alır, her birine periyodik olarak latency testi yapar ve gelen SIP çağrısını **en düşük gecikmeye sahip sunucuya** anlık olarak yönlendirir.

---

## Kurulum Adımları

Aşağıdaki adımları kümedeki **her bir sunucuda** sırasıyla uygulayın.

### Adım 1: Ön Gereksinimler

1.  **Docker & Docker Compose Kurulumu:**
    ```bash
    # En güncel Docker ve eklentilerini kurmak için resmi betiği kullanın.
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    # Docker'ı sudo'suz kullanmak için kullanıcınızı gruba ekleyin.
    sudo usermod -aG docker $USER
    # Değişikliğin aktif olması için sunucudan çıkıp tekrar bağlanın!
    exit
    ```

2.  **Tailscale Kurulumu ve Yapılandırması:**
    ```bash
    # Tailscale'i kurun
    curl -fsSL https://tailscale.com/install.sh | sh
    # Sunucuyu Tailscale ağınıza dahil edin
    sudo tailscale up
    ```
    Bu komut size bir URL verecektir. Bu URL'yi tarayıcınızda açarak sunucuyu Tailscale hesabınıza kaydedin. Bu işlemi **her üç sunucuda da** yapın.
    
    Tüm sunucuları ekledikten sonra, Tailscale Admin Panel'den veya aşağıdaki komutla her sunucunun `100.x.x.x` IP'sini öğrenin:
    ```bash
    tailscale ip -4
    ```

### Adım 2: Projeyi Klonlama ve Yapılandırma

1.  Proje dosyalarını sunucunuza klonlayın:
    ```bash
    git clone https://github.com/sentiric/sentiric-cluster-example.git
    cd sentiric-cluster-example
    ```
2.  Yapılandırma şablonunu kopyalayın:
    ```bash
    cp .env.example .env
    ```
3.  `.env` dosyasını düzenleyin ve **tüm sunucuların Tailscale IP adreslerini** ve **içinde bulunduğunuz sunucunun** bilgilerini girin:
    ```bash
    nano .env
    ```
    **Örnek olarak Sunucu A (GCP) için `.env` dosyası:**
    ```dotenv
    DATACENTER_NAME="sentiric"

    # --- BÖLGE TANIMLARI (Tüm Platformun Fiziksel Haritası) ---

    # Bölge A
    ZONE_A_HOSTNAME="node-a" 
    ZONE_A_BACKBONE_IP="100.107.221.60"
    ZONE_A_PUBLIC_IP="34.122.40.122"

    # Bölge B
    ZONE_B_HOSTNAME="nobe-b"
    ZONE_B_BACKBONE_IP="100.93.43.53"

    # Bölge C
    ZONE_C_HOSTNAME="node-c"
    ZONE_C_BACKBONE_IP="100.122.101.101"
    ```
    > Bu `.env` dosyasını **tüm sunucularda aynı olacak şekilde** hazırlayabilir ve sadece `CURRENT_NODE_*` kısımlarını her sunucuda o sunucuya özel olacak şekilde değiştirebilirsiniz.

### Adım 3: Düğümleri Başlatma

Komutları projenin kök dizininden, **ilgili sunucularda** çalıştırın.

**Node A üzerinde:**
```bash
docker compose --env-file .env -f docker-compose.node.a.yml up -d --build
docker compose --env-file .env -f docker-compose.node.a.yml logs -f 
```

**Node B üzerinde:**
```bash
docker compose --env-file .env -f docker-compose.node.b.yml up -d --build
docker compose --env-file .env -f docker-compose.node.b.yml logs -f 
```

**Node C üzerinde:**
```bash
docker compose --env-file .env -f docker-compose.node.c.yml up -d --build
docker compose --env-file .env -f docker-compose.node.c.yml logs -f 
```

### Adım 4: Doğrulama ve Yönetim

#### Küme Durumunu Kontrol Etme
Herhangi bir sunucunun **PUBLIC IP** adresinden veya **TAILSCALE IP** adresinden Consul arayüzüne erişin: `http://<sunucu_ip>:8500`

-   Arayüzde 3 düğümün de (`zone-a`, `zone-b`, `zone-c`) sağlıklı (`alive`) olduğunu görmelisiniz.
-   "Services" sekmesinde 1 adet `sip-gateway` ve 2 adet `sip-signaling` servisi yeşil (`passing`) olarak görünmelidir.

#### Gerçek Zamanlı Test
1.  **Logları İzleyin:**
    - **Node A'da (Gateway):** `docker logs -f sentiric-cluster-example-sip-gateway-1`
    - **Node B'de (Signaler):** `docker logs -f sentiric-cluster-example-sip-signaling-1`
    - **Node C'de (Signaler):** `docker logs -f sentiric-cluster-example-sip-signaling-1`

2.  **SIP Çağrısı Gönderin:** Kendi bilgisayarınızdan veya başka bir sunucudan `netcat` ile Node A'nın **PUBLIC IP** adresine bir SIP mesajı gönderin:
    ```bash
    # <NODE_A_PUBLIC_IP> yerine Node A'nın genel internet IP'sini yazın.
    echo "REGISTER sip:test@sentiric.cloud SIP/2.0" | nc -u -w1 <NODE_A_PUBLIC_IP> 5060
    ```
3.  **Sonuçları Gözlemleyin:**
    - **Gateway Logları:** Çağrının geldiğini ve en düşük RTT'ye sahip `signaler`'a yönlendirildiğini göreceksiniz.
    - **Signaler Logları:** Yönlendirmenin yapıldığı sunucuda (`node-b` veya `node-c`) mesajın işlendiğini göreceksiniz.
    - **Cevabı Alın:** Komutu çalıştırdığınız terminalde `SIP/2.0 200 OK...` yanıtını göreceksiniz.

#### Sistemi Durdurma
İlgili sunucudaki servisleri durdurmak için:
```bash
# Örnek: Node C'daki servisleri durdurma
docker compose -f docker-compose.node.c.yml down
```