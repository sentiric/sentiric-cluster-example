import socket
import os
import requests
import threading
import time
import logging
from flask import Flask, jsonify

# NİHAİ DÜZELTME: Flask loglarını tamamen sustur
app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.disabled = True
app.logger.disabled = True

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SIP_GATEWAY")

SIP_GATEWAY_UDP_PORT = int(os.getenv("SIP_GATEWAY_UDP_PORT", 5060))
SIP_GATEWAY_HTTP_PORT = int(os.getenv("SIP_GATEWAY_HTTP_PORT", 13010))
DISCOVERY_SERVICE_HTTP_ADDRESS = os.getenv("DISCOVERY_SERVICE_HTTP_ADDRESS", "http://127.0.0.1:8500")

latency_data = {}
latency_lock = threading.Lock()

def find_signaling_nodes():
    nodes = {}
    try:
        service_url = f"{DISCOVERY_SERVICE_HTTP_ADDRESS}/v1/health/service/sip-signaling?passing"
        response = requests.get(service_url, timeout=2)
        response.raise_for_status()
        
        for instance in response.json():
            node_name = instance['Node']['Node']
            addr = instance['Service']['Address'] or instance['Node']['Address']
            port = instance['Service']['Port']
            nodes[node_name] = (addr, port)
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Error querying Consul: {e}")
    return nodes

def latency_prober():
    probe_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe_sock.settimeout(1)
    
    time.sleep(15) 
    logger.info("Latency prober thread started.")

    while True:
        nodes_to_probe = find_signaling_nodes()
        if not nodes_to_probe:
            logger.warning("No signaling nodes found from Consul. Retrying in 10s...")
            with latency_lock:
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
        
        time.sleep(10)

def start_gateway_server(host, port):
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_sock.bind((host, port))
    logger.info(f"SIP Gateway UDP server listening on {host}:{port}")

    while True:
        try:
            data, addr = server_sock.recvfrom(1024)
            logger.info(f"Received SIP message from {addr}")

            with latency_lock:
                if not latency_data:
                    logger.error("NO SIGNALING SERVICE AVAILABLE. Cannot forward SIP message.")
                    continue
                
                fastest_node = min(latency_data, key=lambda n: latency_data[n]['rtt'])
                chosen_target = latency_data[fastest_node]['addr']
            
            logger.info(f"Forwarding to fastest node '{fastest_node}' at {chosen_target}")
            
            forward_data = f"{addr[0]}:{addr[1]}|".encode() + data
            server_sock.sendto(forward_data, chosen_target)
        except Exception as e:
            logger.error(f"Error in gateway UDP loop: {e}")

@app.route('/targets')
def get_targets():
    with latency_lock:
        data_copy = dict(latency_data)
    return jsonify({"available_targets": data_copy})

@app.route('/health')
def health_check():
    return jsonify({"status": "healthy"}), 200

if __name__ == '__main__':
    prober_thread = threading.Thread(target=latency_prober, daemon=True)
    prober_thread.start()

    gateway_thread = threading.Thread(target=start_gateway_server, args=('0.0.0.0', SIP_GATEWAY_UDP_PORT), daemon=True)
    gateway_thread.start()

    logger.info(f"Starting Flask API server on port {SIP_GATEWAY_HTTP_PORT}")
    app.run(host='0.0.0.0', port=SIP_GATEWAY_HTTP_PORT)