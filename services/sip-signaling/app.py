import socket
import os

def start_udp_server(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    print(f"UDP server listening for pings and health checks on {host}:{port}")
    
    while True:
        data, addr = sock.recvfrom(1024)
        print(f"Received message: {data.decode()} from {addr}")
        # Gelen ping'e pong ile cevap ver (opsiyonel)
        sock.sendto(b"PONG", addr)

if __name__ == '__main__':
    udp_port = int(os.environ.get("UDP_PORT", 13024))
    start_udp_server('0.0.0.0', udp_port)