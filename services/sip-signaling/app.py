# DEĞİŞTİ: Kod, ortam değişkenlerinden port alacak şekilde daha temiz hale getirildi.
import socket
import logging
import os

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SIP_SIGNALING")

# YENİ: Port'u ortam değişkeninden alıyoruz.
SIGNALING_PORT = int(os.getenv("SIGNAL_UDP_PORT", 13024))

def start_udp_server(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    logger.info(f"SIP Signaling UDP server listening on {host}:{port}")
    
    while True:
        try:
            data, addr = sock.recvfrom(1024)
            
            if not data:
                continue

            message_str = data.decode(errors='ignore')

            # Gateway'den gelen latency testine cevap ver
            if message_str == "LATENCY_PROBE":
                sock.sendto(b"PROBE_ACK", addr)
                continue
            
            # Sağlık kontrolü için gelen basit mesaja cevap ver (check'te kullanılıyor)
            if message_str == "HEALTH":
                sock.sendto(b"HEALTH_ACK", addr)
                continue

            logger.info(f"Received forwarded message from gateway {addr}")

            parts = message_str.split('|', 1)
            if len(parts) == 2:
                original_sender_str, sip_payload = parts
                
                # Orijinal göndericinin adresini doğru şekilde parse et
                try:
                    original_host, original_port_str = original_sender_str.rsplit(':', 1)
                    original_sender_addr = (original_host, int(original_port_str))

                    logger.info(f"Processing SIP payload: '{sip_payload.strip()}' for original sender {original_sender_addr}")
                    
                    response_message = f"SIP/2.0 200 OK - Processed by {os.getenv('CURRENT_NODE_NAME', 'unknown-signaler')}".encode()
                    sock.sendto(response_message, original_sender_addr)
                except ValueError as e:
                     logger.warning(f"Could not parse original sender address '{original_sender_str}': {e}")
            else:
                logger.warning(f"Received malformed message (no '|' separator): {message_str}")

        except Exception as e:
            logger.error(f"Error in signaling UDP loop: {e}")

if __name__ == '__main__':
    start_udp_server('0.0.0.0', SIGNALING_PORT)