import socket
import os
import requests
from flask import Flask, jsonify

# --- Consul'den servis bulmak için yardımcı fonksiyon ---
def find_signaling_services():
    services = []
    # Consul DNS arayüzü, servis adını çözümleyerek IP listesi döner.
    # network_mode:host kullandığımız için doğrudan host'un DNS'ini kullanabiliriz.
    # Daha garantili yol, Consul DNS'ini (127.0.0.1:8600) kullanmaktır.
    # Ama basitlik için Consul HTTP API'sini kullanalım.
    try:
        consul_url = "http://127.0.0.1:8500/v1/health/service/sip-signaling?passing"
        response = requests.get(consul_url)
        response.raise_for_status()
        service_instances = response.json()
        for instance in service_instances:
            addr = instance['Service']['Address']
            port = instance['Service']['Port']
            services.append(f"{addr}:{port}")
    except Exception as e:
        print(f"Error querying Consul: {e}")
    return services

# --- UDP sunucusu (Sağlık kontrolü için) ---
def start_udp_server(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    print(f"UDP server listening for health checks on {host}:{port}")
    # Bu basit sunucu sadece portu açık tutar. Gelen veriyi işlemez.
    while True:
        sock.recvfrom(1024) # Bekle

# --- Flask Web Sunucusu (API için) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "SIP Gateway is running. UDP port is open for health checks."

@app.route('/ping-signalers')
def ping_signalers():
    """Consul'den sağlıklı signaling servislerini bulur ve onlara bir mesaj gönderir."""
    found_services = find_signaling_services()
    if not found_services:
        return jsonify({"status": "error", "message": "No healthy signaling services found in Consul."}), 503

    responses = {}
    client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    for service_addr in found_services:
        try:
            host, port = service_addr.split(':')
            message = b"PING from gateway"
            client_sock.sendto(message, (host, int(port)))
            print(f"Sent PING to {service_addr}")
            responses[service_addr] = "PING sent"
        except Exception as e:
            responses[service_addr] = f"Error: {e}"
    
    return jsonify({
        "status": "success",
        "message": f"Attempted to ping {len(found_services)} signaling service(s).",
        "targets": responses
    })

if __name__ == '__main__':
    # UDP sunucusunu ayrı bir thread'de başlat
    import threading
    udp_port = int(os.environ.get("UDP_PORT", 5060))
    udp_thread = threading.Thread(target=start_udp_server, args=('0.0.0.0', udp_port))
    udp_thread.daemon = True
    udp_thread.start()

    # Flask sunucusunu başlat (API için farklı bir portta çalıştırabiliriz)
    http_port = int(os.environ.get("HTTP_PORT", 5061))
    app.run(host='0.0.0.0', port=http_port)