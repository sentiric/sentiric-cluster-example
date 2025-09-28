import socket

def start_udp_server(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    print(f"SIP Signaling UDP server listening on {host}:{port}")
    
    while True:
        data, addr = sock.recvfrom(1024)
        # Sadece boş olmayan, gerçek mesajlara cevap ver.
        # Consul'un sağlık kontrolü boş paket gönderir.
        if data:
            message = data.decode(errors='ignore')
            print(f"Received message: '{message}' from {addr}")
            # Sadece PING mesajı olmayanlara PONG ile cevap ver.
            if "PONG" not in message.upper():
                 sock.sendto(b"PONG from signaling", addr)

if __name__ == '__main__':
    udp_port = 13024
    start_udp_server('0.0.0.0', udp_port)