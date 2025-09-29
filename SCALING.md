# Ölçeklendirme ve Yüksek Erişilebilirlik (Scaling & High Availability)

Bu proje, dağıtık bir sistemin temellerini atsa da, üretim ortamında karşılaşılabilecek bazı tekil hata noktalarına (Single Point of Failure - SPOF) sahiptir. Bu doküman, bu noktaları nasıl gidereceğimizi ve sistemi nasıl daha ölçeklenebilir hale getireceğimizi açıklamaktadır.

## Sorun: `sip-gateway` Tekil Hata Noktasıdır

Mevcut mimaride, tüm gelen SIP trafiği tek bir public IP adresine sahip olan `Node A`'daki `sip-gateway` servisine yönlendirilmektedir. Eğer `Node A` veya üzerindeki `sip-gateway` konteyneri çökerse, tüm sistem çağrı alamaz hale gelir.

## Çözüm: Tek Public IP ile Yüksek Erişilebilirlik (Keepalived ile Sanal IP)

Eğer elinizde sadece tek bir public IP adresi varsa, en etkili çözüm **Keepalived** kullanarak bir Sanal IP (Virtual IP - VIP) adresi oluşturmaktır.

### Nasıl Çalışır?

**Keepalived**, VRRP (Virtual Router Redundancy Protocol) protokolünü kullanarak çalışır.

1.  **Kurulum:** En az iki sunucuyu `sip-gateway` olarak yapılandırırsınız (örneğin Node A ve yeni bir Node D). Her ikisine de `Keepalived` kurulur.
2.  **Roller:**
    *   Bir sunucu `MASTER` rolünü üstlenir. Public IP adresi (VIP) bu sunucunun ağ arayüzüne atanır. Gelen tüm trafik bu sunucu tarafından işlenir.
    *   Diğer sunucu (veya sunucular) `BACKUP` rolündedir. Sürekli olarak `MASTER` sunucuyu dinlerler.
3.  **Yük Devretme (Failover):** Eğer `BACKUP` sunucu, belirli bir süre boyunca `MASTER`'dan "hayattayım" sinyali (VRRP advertisement) alamazsa, `MASTER`'ın çöktüğünü varsayar.
4.  **Devralma:** `BACKUP` sunucu, kendini `MASTER` olarak ilan eder ve Sanal IP'yi (VIP) kendi ağ arayüzüne atar. Bu işlem genellikle 1-2 saniye içinde tamamlanır.
5.  **Sonuç:** Dış dünyadan gelen trafik, kesintisiz bir şekilde yeni `MASTER` sunucuya akmaya devam eder.

### Uygulama Adımları

1.  **İki Gateway Sunucusu Hazırlayın:** İki node'u da `docker-compose.node.a.yml` gibi bir `sip-gateway` içeren yapılandırma ile ayağa kaldırın.
2.  **Keepalived Kurulumu:** Her iki sunucuya da `keepalived` kurun:
    ```bash
    sudo apt-get update && sudo apt-get install keepalived -y
    ```
3.  **Çekirdek Ayarı:** Her iki sunucuda da root olmayan process'lerin, sunucuya ait olmayan bir IP'yi (yani VIP'yi) dinleyebilmesi için şu ayarı yapın:
    ```bash
    echo "net.ipv4.ip_nonlocal_bind=1" | sudo tee -a /etc/sysctl.conf
    sudo sysctl -p
    ```
4.  **Keepalived Yapılandırması:**

    **MASTER Sunucu (`/etc/keepalived/keepalived.conf`):**
    ```
    vrrp_instance VI_1 {
        state MASTER
        interface eth0  # Public ağ arayüzünüzü yazın
        virtual_router_id 51
        priority 101    # MASTER'ın önceliği daha yüksek olmalı
        advert_int 1
        authentication {
            auth_type PASS
            auth_pass 1111
        }
        virtual_ipaddress {
            <YOUR_SINGLE_PUBLIC_IP>/24  # Örneğin: 34.122.40.122/24
        }
    }
    ```

    **BACKUP Sunucu (`/etc/keepalived/keepalived.conf`):**
    ```
    vrrp_instance VI_1 {
        state BACKUP
        interface eth0  # Public ağ arayüzünüzü yazın
        virtual_router_id 51
        priority 100    # BACKUP'ın önceliği daha düşük olmalı
        advert_int 1
        authentication {
            auth_type PASS
            auth_pass 1111
        }
        virtual_ipaddress {
            <YOUR_SINGLE_PUBLIC_IP>/24  # Örneğin: 34.122.40.122/24
        }
    }
    ```

5.  **Servisi Başlatın:** Her iki sunucuda da `keepalived` servisini başlatın ve etkinleştirin:
    ```bash
    sudo systemctl enable keepalived
    sudo systemctl start keepalived
    ```

Bu yapılandırma ile `sip-gateway` katmanınız artık yüksek erişilebilir hale gelmiştir.