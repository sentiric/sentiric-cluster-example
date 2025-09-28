import socket
import os
import requests
import threading
import time
import logging
import random
from flask import Flask, jsonify

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SIP_GATEWAY")

latency_data = {}
latency_lock = threading.Lock()

def find_signaling_nodes():
    nodes = {}
    try:
        # Host modunda olduğumuz için localhost üzerinden Consul'e erişiyoruz
        consul_url = "http://127.0.0.1:8500/v1/health/service/sip-signaling?passing"
        response = requests.get(consul_url, timeout=2)
        response.raise_for_status()
        service_instances = response.json()
        for instance in service_instances:
            node_name = instance['Node']['Node']
            addr = instance['Node']['Address']
            port = instance['Service']['Port']
            nodes[node_name] = (addr, port)
    except Exception as e:
        logger.error(f"Error querying Consul: {e}")
    return nodes

def latency_prober():
    probe_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe_sock.settimeout(1)
    
    # Kümenin kurulması için başlangıçta biraz bekle
    time.sleep(15) 
    logger.info("Latency prober thread started.")

    while True:
        nodes_to_probe = find_signaling_nodes()
        for node_name, (host, port) in nodes_to_probe.items():
            try:
                message = b"LATENCY_PROBE"
                start_time = time.monotonic()
                probe_sock.sendto(message, (host, port))
                probe_sock.recvfrom(1024)
                end_time = time.monotonic()
                rtt = (end_time - start_time) * 1000
                
                with latency_lock:
                    latency_data[node_name] = {'rtt': rtt, 'addr': (host, port)}
                logger.info(f"Latency probe to {node_name} ({host}:{port}): {rtt:.2f} ms")
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
    
    client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    while True:
        try:
            data, addr = server_sock.recvfrom(1024)
            logger.info(f"Received SIP message from {addr}: {data.decode(errors='ignore')}")

            with latency_lock:
                if not latency_data:
                    logger.warning("No healthy/fast signaling services available to forward message.")
                    continue
                fastest_node = min(latency_data, key=lambda n: latency_data[n]['rtt'])
                chosen_target = latency_data[fastest_node]['addr']
            
            logger.info(f"Forwarding message to fastest signaler '{fastest_node}' at {chosen_target}")
            
            forward_data = f"{addr[0]}:{addr[1]}|".encode() + data
            client_sock.sendto(forward_data, chosen_target)
        except Exception as e:
            logger.error(f"Error in gateway UDP loop: {e}")

app = Flask(__name__)

@app.route('/targets')
def get_targets():
    with latency_lock:
        sorted_targets = sorted(latency_data.items(), key=lambda item: item[1]['rtt'])
    return jsonify({"fastest_targets_by_latency": sorted_targets})

if __name__ == '__main__':
    prober_thread = threading.Thread(target=latency_prober)
    prober_thread.daemon = True
    prober_thread.start()

    gateway_thread = threading.Thread(target=start_gateway_server, args=('0.0.0.0', 5060))
    gateway_thread.daemon = True
    gateway_thread.start()

    logger.info("Starting Flask API server on port 5061")
    app.run(host='0.0.0.0', port=5061, debug=False)