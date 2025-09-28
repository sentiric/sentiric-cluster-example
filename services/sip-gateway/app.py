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
        # Sadece sağlıklı (passing) servisleri al, 2 saniye timeout ile
        consul_url = "http://127.0.0.1:8500/v1/health/service/sip-signaling?passing"
        response = requests.get(consul_url, timeout=2)
        response.raise_for_status()  # HTTP hatası varsa exception fırlat
        service_instances = response.json()
        
        for instance in service_instances:
            # Servisin IP'si boşsa Node'un IP'sini kullan (daha sağlam)
            addr = instance['Service']['Address'] or instance['Node']['Address']
            port = instance['Service']['Port']
            services.append((addr, port))
            
    except requests.exceptions.RequestException as e:
        print(f"Error querying Consul: {e}")
    except Exception as e:
        print(f"An unexpected error occurred in find_signaling_services: {e}")
        
    return services

# --- Gateway UDP Sunucusu (Gelen çağrıları yönlendirir ve sağlık kontrolüne cevap verir) ---
def start_gateway_server(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    print(f"SIP Gateway UDP server listening on {host}:{port}")
    
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            print(f"Received SIP-like message from {addr}: {data.decode(errors='ignore')}")

            # Consul'den sağlıklı hedefleri bul
            targets = find_signaling_services()
            
            if not targets:
                print("No healthy signaling services found to forward the message.")
                continue

            # Hedeflerden rastgele birini seç (basit yük dengeleme)
            chosen_target = random.choice(targets)
            print(f"Forwarding message to randomly chosen signaler: {chosen_target}")
            
            # Mesajı seçilen hedefe gönder
            sock.sendto(data, chosen_target)
        except Exception as e:
            print(f"Error in gateway UDP loop: {e}")

# --- Flask Web Sunucusu (API için) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "SIP Gateway is running. UDP port is open for calls and health checks."

@app.route('/targets')
def get_targets():
    """Consul'den şu anki sağlıklı hedefleri gösterir."""
    targets = find_signaling_services()
    if not targets:
        return jsonify({"status": "error", "message": "No healthy signaling services found"}), 503
    return jsonify({"healthy_signaling_services": [f"{h}:{p}" for h, p in targets]})

if __name__ == '__main__':
    # Gateway UDP sunucusunu ayrı bir thread'de başlat
    udp_port = int(os.environ.get("UDP_PORT", 5060))
    gateway_thread = threading.Thread(target=start_gateway_server, args=('0.0.0.0', udp_port))
    gateway_thread.daemon = True
    gateway_thread.start()

    # Flask sunucusunu başlat
    http_port = int(os.environ.get("HTTP_PORT", 5061))
    app.run(host='0.0.0.0', port=http_port)