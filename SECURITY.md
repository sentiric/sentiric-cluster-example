# Güvenlik Sağlamlaştırma Notları

Bu proje, bir referans uygulaması olduğu için bazı güvenlik adımları basitleştirilmiştir. Üretim ortamına geçerken aşağıdaki adımların uygulanması şiddetle tavsiye edilir.

## 1. Consul ACL (Access Control Lists) Sistemini Aktifleştirme

Mevcut durumda, Consul kümesine erişen herhangi bir servis veya kullanıcı, tüm verileri okuyabilir, yazabilir ve silebilir. ACL sistemi, bu erişimi kısıtlayarak "en az ayrıcalık" (least privilege) prensibini uygular.

### Adımlar:

1.  **ACL'leri Aktifleştir:** Her Consul sunucusunun yapılandırmasına (`discovery/config/zone_*/agent.json`) aşağıdaki bloğu ekleyin:
    ```json
    {
      "enable_local_script_checks": true,
      "acl": {
        "enabled": true,
        "default_policy": "deny",
        "enable_token_persistence": true
      }
    }
    ```
    *   `default_policy: "deny"`: Geçerli bir token olmadan yapılan tüm işlemleri reddeder.

2.  **Bootstrap ACL Sistemi:** Kümedeki sunuculardan birinde aşağıdaki komutu çalıştırarak ilk yönetim (management) token'ını oluşturun:
    ```bash
    docker exec <consul_container_id> consul acl bootstrap
    ```
    Bu komut size bir `SecretID` verecektir. Bu, sizin "root" token'ınızdır. **Bunu güvenli bir yerde saklayın!**

3.  **Servisler İçin Token Oluşturma:**
    *   Her servis (`sip-gateway`, `sip-signaling`) için ayrı policy'ler ve bu policy'lere bağlı token'lar oluşturun.
    *   **Örnek `sip-signaling` Policy'si:** Sadece kendi servisini kaydetme ve sağlık kontrolü yapma yetkisi.
    *   **Örnek `sip-gateway` Policy'si:** Sadece `sip-signaling` servisini okuma (`service:read`) yetkisi.

4.  **Token'ları Servislere Tanıtma:** Oluşturulan token'ları `docker-compose` dosyalarında environment variable olarak konteynerlere geçin. Uygulamalarınızın Consul'a bağlanırken bu token'ları kullanmasını sağlayın.

## 2. Gossip Şifrelemesi

Consul node'ları arasındaki cluster iletişimini (gossip) şifrelemek, ağ içindeki olası dinlemelere karşı ek bir koruma katmanı sağlar.

### Adımlar:

1.  **Şifreleme Anahtarı Oluştur:**
    ```bash
    consul keygen
    ```
    Bu komut size 16-byte'lık, Base64 formatında bir anahtar verecektir (`abcdefg...==`).

2.  **Anahtarı Yapılandırmaya Ekle:** Bu anahtarı, kümedeki **tüm Consul sunucularının** `agent.json` dosyasına ekleyin:
    ```json
    {
      "encrypt": "YOUR_GENERATED_KEY_HERE"
    }
    ```
    > **Önemli:** Kümedeki tüm ajanlar aynı şifreleme anahtarını kullanmalıdır.

## 3. Konteynerleri `root` Olmayan Kullanıcı ile Çalıştırma

Bu proje kapsamında `Dockerfile`'lar, `appuser` adında ayrıcalıksız bir kullanıcı ile çalışacak şekilde güncellenmiştir. Bu, "defense-in-depth" (derinlemesine savunma) stratejisinin önemli bir parçasıdır ve konteyner içindeki bir zafiyetin tüm sunucuyu ele geçirmesini zorlaştırır.