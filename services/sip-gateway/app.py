import socket
import os
import requests
import threading
import random
from flask import Flask, jsonify

# --- Consul'den servis bulmak için yardımcı fonksiyon ---
def find_signaling_services():
    services = []
    try:
        consul_url = "http://127.0.0.1:8500/v1/health/service/sip-signaling?passing"
        response = requests.get(consul_url, timeout=2)
        response.raise_for_status()
        service_instances = response.json()
        for instance in service_instances:
            addr = instance['Service']['Address'] or instance['Node']['Address']
            port = instance['Service']['Port']
            services.append((addr, port))
    except Exception as e:
        print(f"Error querying Consul: {e}")
    return services

# --- Gateway UDP Sunucusu (Gelen çağrıları yönlendirir) ---
def start_gateway_server(host, port):
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_sock.bind((host, port))
    print(f"SIP Gateway UDP server listening on {host}:{port}")
    
    # Giden mesajlar için ayrı, geçici bir soket kullanacağız.
    client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    while True:
        try:
            data, addr = server_sock.recvfrom(1024)
            # Sadece dışarıdan gelen (diğer sunuculardan gelmeyen) mesajları işle
            if addr[0] not in [s[0] for s in find_signaling_services()]:
                print(f"Received external SIP message from {addr}: {data.decode(errors='ignore')}")

                targets = find_signaling_services()
                if not targets:
                    print("No healthy signaling services found.")
                    continue

                chosen_target = random.choice(targets)
                print(f"Forwarding message to randomly chosen signaler: {chosen_target}")
                client_sock.sendto(data, chosen_target)
            else:
                # Bu, bir signaling sunucusundan gelen bir cevaptır, logla ve görmezden gel.
                print(f"Received internal response from {addr}, ignoring.")

        except Exception as e:
            print(f"Error in gateway UDP loop: {e}")

# --- Flask Web Sunucusu (API için) ---
app = Flask(__name__)

@app.route('/targets')
def get_targets():
    """Consul'den şu anki sağlıklı hedefleri gösterir."""
    targets = find_signaling_services()
    return jsonify({"healthy_signaling_services": [f"{h}:{p}" for h, p in targets]})

if __name__ == '__main__':
    udp_port = 5060
    gateway_thread = threading.Thread(target=start_gateway_server, args=('0.0.0.0', udp_port))
    gateway_thread.daemon = True
    gateway_thread.start()

    http_port = 5061
    app.run(host='0.0.0.0', port=http_port)