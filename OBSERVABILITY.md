# Gözlemlenebilirlik (Observability)

Bir sistemin sadece çalışması yeterli değildir; nasıl çalıştığını, ne zaman zorlandığını ve hataların nerede meydana geldiğini anlamak da kritik öneme sahiptir. Gözlemlenebilirlik, bir sistemin iç durumunu dış çıktılarından (loglar, metrikler, izler) anlama yeteneğidir.

Bu proje için temel bir gözlemlenebilirlik yığını aşağıdaki bileşenlerden oluşabilir:

### 1. Merkezi Log Yönetimi (Logging)

**Sorun:** Her sunucuya tek tek `ssh` ile bağlanıp `docker logs` komutunu çalıştırmak, özellikle node sayısı arttıkça imkansız hale gelir.

**Çözüm:** Logları merkezi bir yerde toplamak.
*   **Mimarisi:** Her Docker host'una bir log toplayıcı ajan (örn: **Fluentd**, **Promtail**) kurulur. Bu ajan, tüm konteyner loglarını okur, etiketler (örn: `service=sip-gateway`, `node=node-a`) ve merkezi bir log depolama sistemine gönderir.
*   **Araçlar:**
    *   **Depolama/Sorgulama:** **Loki** (Grafana ile entegre, hafif) veya **Elasticsearch** (daha güçlü, daha karmaşık).
    *   **Görselleştirme:** **Grafana** (Loki için) veya **Kibana** (Elasticsearch için).

### 2. Metrikler ve Alarmlar (Metrics & Alerting)

**Sorun:** Sistemin performansını (gecikme süreleri, işlenen çağrı sayısı, CPU kullanımı) anlık olarak nasıl takip edebiliriz? Anormal bir durumda (örn: bir node'un RTT'sinin aniden 500ms'ye fırlaması) nasıl haberimiz olur?

**Çözüm:** Zaman serisi metrikleri toplamak ve bu metrikler üzerinden alarmlar kurmak.

*   **Mimarisi:**
    1.  Uygulamalar (`sip-gateway`, `sip-signaling`) `/metrics` endpoint'i üzerinden Prometheus formatında metrikler yayınlar (örn: `sip_calls_processed_total`, `signaler_rtt_milliseconds`). Projemizde bu portlar (`13012`, `13022`) zaten ayrılmıştır, sadece kodun metrikleri yayınlaması gerekir.
    2.  **Prometheus** sunucusu, düzenli aralıklarla bu `/metrics` endpoint'lerini sorgulayarak (scraping) verileri toplar ve kendi zaman serisi veritabanında saklar.
    3.  **Grafana**, Prometheus'u bir veri kaynağı olarak kullanarak bu metrikleri görselleştiren dashboard'lar oluşturmanızı sağlar.
    4.  **Alertmanager**, Prometheus'a entegre çalışır. Prometheus'ta tanımlanan kurallar (örn: `RTT > 200ms for 1 minute`) tetiklendiğinde, Alertmanager e-posta, Slack veya PagerDuty gibi kanallar üzerinden bildirim gönderir.

### 3. Dağıtık İzleme (Distributed Tracing)

**Sorun:** Bir SIP çağrısı `sip-gateway`'e geldi, `sip-signaling`'e yönlendirildi ve bir yanıt döndü. Bu sürecin hangi aşaması ne kadar sürdü? Eğer bir yavaşlık varsa, bu yavaşlık gateway'de mi yoksa signaling servisinde mi?

**Çözüm:** Her bir isteğe benzersiz bir "Trace ID" atamak ve bu isteğin sistemdeki yolculuğunu takip etmek.
*   **Mimarisi:**
    1.  `sip-gateway`, gelen her isteğe bir `trace_id` atar ve bu ID'yi `sip-signaling`'e gönderdiği paketin içine ekler.
    2.  Her servis (`gateway` ve `signaling`), kendi yaptığı işleme dair bilgileri (span) bu `trace_id` ile birlikte bir Tracing Backend'e gönderir (örn: **Jaeger**, **Zipkin**).
    3.  Jaeger veya Zipkin arayüzü üzerinden bir `trace_id` ile arama yaparak, bir isteğin tüm yaşam döngüsünü, hangi serviste ne kadar zaman harcadığını şelale (waterfall) grafiği şeklinde görebilirsiniz.