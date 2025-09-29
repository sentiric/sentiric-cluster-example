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

# --- .env dosyasından gelen yapılandırmayı oku ---
SIP_GATEWAY_UDP_PORT = int(os.getenv("SIP_GATEWAY_UDP_PORT", 5060))
SIP_GATEWAY_HTTP_PORT = int(os.getenv("SIP_GATEWAY_HTTP_PORT", 13010))
SIP_SIGNALING_UDP_PORT = int(os.getenv("SIP_SIGNALING_UDP_PORT", 13024))
DISCOVERY_SERVICE_HTTP_ADDRESS = os.getenv("DISCOVERY_SERVICE_HTTP_ADDRESS")
DISCOVERY_METHOD = os.getenv("DISCOVERY_METHOD", "HTTP").upper()

# YENİ: Datacenter ve DNS adı değişkenlerini okuyoruz
DISCOVERY_DATACENTER_NAME = os.getenv("DISCOVERY_DATACENTER_NAME")
SIP_SIGNALING_DNS_NAME = os.getenv("SIP_SIGNALING_DNS_NAME", "sip-signaling")

# --- Global Değişkenler ---
latency_data = {}
latency_lock = threading.Lock()
shutdown_event = threading.Event()
forwarding_table = OrderedDict()
FORWARDING_TABLE_MAX_SIZE = 10000
FORWARDING_TABLE_TTL = 30

# --- Servis Keşif Fonksiyonları ---

def find_signaling_nodes_http():
    """Consul HTTP API kullanarak servisleri keşfeder."""
    nodes = {}
    if not DISCOVERY_SERVICE_HTTP_ADDRESS or not DISCOVERY_DATACENTER_NAME:
        logger.error("[HTTP Discovery] DISCOVERY_SERVICE_HTTP_ADDRESS or DISCOVERY_DATACENTER_NAME is not set in environment.")
        return nodes
    
    try:
        # DEĞİŞİKLİK: Sorguyu datacenter'a özel hale getirdik. Bu, daha doğru ve sağlam bir yöntemdir.
        service_url = f"{DISCOVERY_SERVICE_HTTP_ADDRESS}/v1/health/service/sip-signaling?passing&dc={DISCOVERY_DATACENTER_NAME}"
        
        response = requests.get(service_url, timeout=2)
        response.raise_for_status()
        
        for instance in response.json():
            node_name = instance['Node']['Node']
            addr = instance['Node']['Address']
            port = instance['Service']['Port']
            nodes[node_name] = (addr, port)
            
    except requests.exceptions.RequestException as e:
        logger.error(f"[HTTP Discovery] Error querying Consul: {e}")
    return nodes

def find_signaling_nodes_dns():
    """Consul DNS kullanarak servisleri keşfeder."""
    nodes = {}
    try:
        addr_info = socket.getaddrinfo(SIP_SIGNALING_DNS_NAME, None)
        ips = list(set(info[4][0] for info in addr_info))

        for ip in ips:
            node_key = ip 
            nodes[node_key] = (ip, SIP_SIGNALING_UDP_PORT)

    except socket.gaierror:
        logger.warning(f"[DNS Discovery] Could not resolve '{SIP_SIGNALING_DNS_NAME}'. No healthy instances found?")
    except Exception as e:
        logger.error(f"[DNS Discovery] An unexpected error occurred: {e}")
    return nodes

def find_nodes():
    """Yapılandırmaya göre uygun keşif yöntemini seçer ve çalıştırır."""
    if DISCOVERY_METHOD == "DNS":
        logger.debug("Using DNS for service discovery.")
        return find_signaling_nodes_dns()
    else: # Varsayılan HTTP
        logger.debug("Using HTTP API for service discovery.")
        return find_signaling_nodes_http()

# --- Latency Test, Gateway Sunucusu ve diğer fonksiyonlar ---
# BU KISIMDA HİÇBİR DEĞİŞİKLİK GEREKMEZ, ÇÜNKÜ find_nodes() FONKSİYONU ZATEN DOĞRU
# VERİ YAPISINI (nodes dictionary) DÖNMEKTEDİR. ÖNCEKİ VERSİYONLA AYNIDIR.

def latency_prober():
    probe_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe_sock.settimeout(1)
    
    time.sleep(15) 
    logger.info(f"Latency prober thread started. Discovery method: {DISCOVERY_METHOD}")

    while not shutdown_event.is_set():
        nodes_to_probe = find_nodes()
        
        with latency_lock:
            current_healthy_nodes = set(nodes_to_probe.keys())
            known_nodes = set(latency_data.keys())
            stale_nodes = known_nodes - current_healthy_nodes
            if stale_nodes:
                for node in stale_nodes:
                    logger.warning(f"Removing stale node from latency data: {node}")
                    del latency_data[node]
            
            if not nodes_to_probe:
                logger.warning("No healthy signaling nodes found from Consul. Clearing latency data.")
                latency_data.clear()

        for node_key, (host, port) in nodes_to_probe.items():
            try:
                message = b"LATENCY_PROBE"
                start_time = time.monotonic()
                probe_sock.sendto(message, (host, port))
                probe_sock.recvfrom(1024)
                end_time = time.monotonic()
                rtt = (end_time - start_time) * 1000
                
                with latency_lock:
                    latency_data[node_key] = {'rtt': rtt, 'addr': (host, port), 'last_seen': time.time()}
                logger.debug(f"Latency to {node_key} ({host}:{port}): {rtt:.2f} ms")
            except socket.timeout:
                logger.warning(f"Latency probe to {node_key} ({host}:{port}) timed out.")
                with latency_lock:
                    if node_key in latency_data:
                        del latency_data[node_key]
            except Exception as e:
                logger.error(f"Error probing {node_key}: {e}")
        
        shutdown_event.wait(10)
    
    probe_sock.close()
    logger.info("Latency prober thread gracefully stopped.")

def start_gateway_server(host, port):
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_sock.bind((host, port))
    server_sock.settimeout(1.0) 
    logger.info(f"SIP Gateway UDP server listening on {host}:{port}")

    while not shutdown_event.is_set():
        try:
            data, addr = server_sock.recvfrom(2048)
            
            source_is_signaler = False
            with latency_lock:
                for node_info in latency_data.values():
                    if node_info['addr'] == addr:
                        source_is_signaler = True
                        break

            if source_is_signaler:
                original_client_addr = None
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
                with latency_lock:
                    if not latency_data:
                        logger.error("NO SIGNALING SERVICE AVAILABLE. Cannot forward SIP message.")
                        continue
                    
                    fastest_node_key = min(latency_data, key=lambda n: latency_data[n]['rtt'])
                    chosen_target = latency_data[fastest_node_key]['addr']
                
                logger.info(f"Forwarding SIP request from {addr} to fastest node '{fastest_node_key}' at {chosen_target}")
                
                forward_data = f"{addr[0]}:{addr[1]}|".encode() + data
                server_sock.sendto(forward_data, chosen_target)
                
                forwarding_table[addr] = { 'signaler_addr': chosen_target, 'timestamp': time.time() }
                if len(forwarding_table) > FORWARDING_TABLE_MAX_SIZE:
                    forwarding_table.popitem(last=False)

        except socket.timeout:
            continue
        except Exception as e:
            logger.error(f"Error in gateway UDP loop: {e}")

    server_sock.close()
    logger.info("Gateway UDP server gracefully stopped.")

@app.route('/targets')
def get_targets():
    with latency_lock:
        data_copy = dict(latency_data)
    return jsonify({"available_targets": data_copy})

@app.route('/health')
def health_check():
    return jsonify({"status": "healthy"}), 200

def shutdown_handler(signum, frame):
    logger.warning("Shutdown signal received. Stopping services...")
    shutdown_event.set()

if __name__ == '__main__':
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    prober_thread = threading.Thread(target=latency_prober, daemon=False)
    gateway_thread = threading.Thread(target=start_gateway_server, args=('0.0.0.0', SIP_GATEWAY_UDP_PORT), daemon=False)
    
    prober_thread.start()
    gateway_thread.start()
    
    logger.info(f"Starting Flask API server on port {SIP_GATEWAY_HTTP_PORT}")
    app.run(host='0.0.0.0', port=SIP_GATEWAY_HTTP_PORT)
    
    gateway_thread.join()
    prober_thread.join()
    logger.info("Application has been shut down.")