import socket
import os
import requests
import threading
import time
import logging
import signal
from collections import OrderedDict
from flask import Flask, jsonify

# --- Flask loglarını tamamen sustur ---
app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.disabled = True
app.logger.disabled = True

# --- Temel yapılandırma ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SIP_GATEWAY")

SIP_GATEWAY_UDP_PORT = int(os.getenv("SIP_GATEWAY_UDP_PORT", 5060))
SIP_GATEWAY_HTTP_PORT = int(os.getenv("SIP_GATEWAY_HTTP_PORT", 13010))
DISCOVERY_SERVICE_HTTP_ADDRESS = os.getenv("DISCOVERY_SERVICE_HTTP_ADDRESS", "http://discovery-service:8500")

# --- Global Değişkenler ve Kontrol Mekanizmaları ---
latency_data = {}
latency_lock = threading.Lock()
shutdown_event = threading.Event()

# İstemci -> Sinyal Sunucusu yönlendirme tablosu
# (client_addr) -> { 'signaler_addr': addr, 'timestamp': time }
forwarding_table = OrderedDict()
FORWARDING_TABLE_MAX_SIZE = 10000
FORWARDING_TABLE_TTL = 30  # saniye

# --- Consul ile Servis Keşfi ---
def find_signaling_nodes():
    nodes = {}
    try:
        service_url = f"{DISCOVERY_SERVICE_HTTP_ADDRESS}/v1/health/service/sip-signaling?passing"
        response = requests.get(service_url, timeout=2)
        response.raise_for_status()
        
        for instance in response.json():
            node_name = instance['Node']['Node']
            # Consul, Docker network içindeki IP'yi değil, node'un kendi IP'sini dönebilir.
            # -advertise ile belirtilen IP'yi (Backbone IP) kullanmak en sağlıklısı.
            addr = instance['Node']['Address']
            port = instance['Service']['Port']
            nodes[node_name] = (addr, port)
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Error querying Consul: {e}")
    return nodes

# --- Latency Test Mekanizması ---
def latency_prober():
    probe_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe_sock.settimeout(1)
    
    time.sleep(15) 
    logger.info("Latency prober thread started.")

    while not shutdown_event.is_set():
        nodes_to_probe = find_signaling_nodes()
        
        with latency_lock:
            # --- SAĞLAMLAŞTIRMA: Consul'de artık olmayan nodeları latency_data'dan temizle ---
            current_healthy_nodes = set(nodes_to_probe.keys())
            known_nodes = set(latency_data.keys())
            stale_nodes = known_nodes - current_healthy_nodes
            if stale_nodes:
                for node in stale_nodes:
                    logger.warning(f"Removing stale node from latency data: {node}")
                    del latency_data[node]
            # --- SAĞLAMLAŞTIRMA SONU ---

            if not nodes_to_probe:
                logger.warning("No healthy signaling nodes found from Consul. Clearing latency data.")
                latency_data.clear()

        for node_name, (host, port) in nodes_to_probe.items():
            try:
                message = b"LATENCY_PROBE"
                start_time = time.monotonic()
                probe_sock.sendto(message, (host, port))
                probe_sock.recvfrom(1024)
                end_time = time.monotonic()
                rtt = (end_time - start_time) * 1000
                
                with latency_lock:
                    latency_data[node_name] = {'rtt': rtt, 'addr': (host, port), 'last_seen': time.time()}
                logger.debug(f"Latency to {node_name} ({host}:{port}): {rtt:.2f} ms")
            except socket.timeout:
                logger.warning(f"Latency probe to {node_name} ({host}:{port}) timed out.")
                with latency_lock:
                    if node_name in latency_data:
                        del latency_data[node_name]
            except Exception as e:
                logger.error(f"Error probing {node_name}: {e}")
        
        # Döngüyü 10 saniye boyunca veya kapanma sinyali gelene kadar beklet
        shutdown_event.wait(10)
    
    probe_sock.close()
    logger.info("Latency prober thread gracefully stopped.")

# --- Ana Gateway Sunucusu ---
def start_gateway_server(host, port):
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_sock.bind((host, port))
    server_sock.settimeout(1.0) # Bloklamayı engellemek için timeout
    logger.info(f"SIP Gateway UDP server listening on {host}:{port}")

    while not shutdown_event.is_set():
        try:
            data, addr = server_sock.recvfrom(2048)
            
            # --- MİMARİ GÜNCELLEMESİ: Gelen paket istemciden mi yoksa sinyal sunucusundan mı? ---
            # Eğer paket bir sinyal sunucusundan geliyorsa, bu bir yanıttır.
            source_is_signaler = False
            with latency_lock:
                for node_info in latency_data.values():
                    if node_info['addr'] == addr:
                        source_is_signaler = True
                        break

            if source_is_signaler:
                # Bu bir yanıt, orijinal istemciye geri yönlendir.
                # Yönlendirme tablosunda istemciyi bul (tersten arama)
                original_client_addr = None
                # Not: Bu yaklaşım büyük trafik altında yavaş olabilir. Üretim ortamında daha
                # verimli bir yapı (örn: (signaler_addr -> client_addr) map) düşünülebilir.
                for client, mapping_info in list(forwarding_table.items()):
                    if mapping_info['signaler_addr'] == addr:
                         original_client_addr = client
                         break
                
                if original_client_addr:
                    server_sock.sendto(data, original_client_addr)
                    logger.info(f"Forwarded response from {addr} back to original client {original_client_addr}")
                else:
                    logger.warning(f"Received response from signaler {addr}, but no matching client found in forwarding table.")
            else:
                # Bu yeni bir istek, en hızlı sinyal sunucusuna yönlendir.
                with latency_lock:
                    if not latency_data:
                        logger.error("NO SIGNALING SERVICE AVAILABLE. Cannot forward SIP message.")
                        continue
                    
                    fastest_node = min(latency_data, key=lambda n: latency_data[n]['rtt'])
                    chosen_target = latency_data[fastest_node]['addr']
                
                logger.info(f"Forwarding SIP request from {addr} to fastest node '{fastest_node}' at {chosen_target}")
                
                # İstemci bilgisini paketin başına ekle.
                forward_data = f"{addr[0]}:{addr[1]}|".encode() + data
                server_sock.sendto(forward_data, chosen_target)
                
                # Yönlendirme tablosunu güncelle.
                forwarding_table[addr] = { 'signaler_addr': chosen_target, 'timestamp': time.time() }
                # Tablo boyutunu kontrol et
                if len(forwarding_table) > FORWARDING_TABLE_MAX_SIZE:
                    forwarding_table.popitem(last=False)

        except socket.timeout:
            continue # Timeout normal, döngüye devam et.
        except Exception as e:
            logger.error(f"Error in gateway UDP loop: {e}")

    server_sock.close()
    logger.info("Gateway UDP server gracefully stopped.")

# --- API ve Yardımcı Fonksiyonlar ---
@app.route('/targets')
def get_targets():
    with latency_lock:
        data_copy = dict(latency_data)
    return jsonify({"available_targets": data_copy})

@app.route('/health')
def health_check():
    return jsonify({"status": "healthy"}), 200

# --- ZARİF KAPANMA (Graceful Shutdown) ---
def shutdown_handler(signum, frame):
    logger.warning("Shutdown signal received. Stopping services...")
    shutdown_event.set()

# --- Ana Çalıştırma Bloğu ---
if __name__ == '__main__':
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    prober_thread = threading.Thread(target=latency_prober, daemon=False)
    gateway_thread = threading.Thread(target=start_gateway_server, args=('0.0.0.0', SIP_GATEWAY_UDP_PORT), daemon=False)
    
    prober_thread.start()
    gateway_thread.start()
    
    logger.info(f"Starting Flask API server on port {SIP_GATEWAY_HTTP_PORT}")
    # Flask'i ayrı bir thread'de çalıştırmak yerine ana thread'de çalıştırıyoruz,
    # ancak kapanma sinyali geldiğinde diğer thread'lerin bitmesini bekleyeceğiz.
    # Flask'in kendi başına graceful shutdown'ı yoktur, bu yüzden bu en basit yaklaşım.
    app.run(host='0.0.0.0', port=SIP_GATEWAY_HTTP_PORT)
    
    gateway_thread.join()
    prober_thread.join()
    logger.info("Application has been shut down.")