import socket
import logging
import os
import threading
import signal
from flask import Flask, jsonify

# --- Flask loglarını tamamen sustur ---
app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.disabled = True
app.logger.disabled = True

# --- Temel yapılandırma ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SIP_SIGNALING")

SIP_SIGNALING_UDP_PORT = int(os.getenv("SIP_SIGNALING_UDP_PORT", 13024))
SIP_SIGNALING_HTTP_PORT = int(os.getenv("SIP_SIGNALING_HTTP_PORT", 13020))

# --- Global Kontrol Mekanizmaları ---
shutdown_event = threading.Event()

# --- UDP Sunucusu ---
def start_udp_server(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    sock.settimeout(1.0) # Bloklamayı engellemek için timeout
    logger.info(f"SIP Signaling UDP server listening on {host}:{port}")
    
    while not shutdown_event.is_set():
        try:
            data, addr = sock.recvfrom(2048) # Gateway adresi 'addr'
            
            if not data:
                continue

            message_str = data.decode(errors='ignore')

            if message_str == "LATENCY_PROBE":
                sock.sendto(b"PROBE_ACK", addr)
                continue

            logger.info(f"Received forwarded message from gateway {addr}")

            parts = message_str.split('|', 1)
            if len(parts) == 2:
                original_sender_str, sip_payload = parts
                
                try:
                    # Orijinal istemci adresi parse ediliyor, ama yanıt için kullanılmayacak.
                    original_host, original_port_str = original_sender_str.rsplit(':', 1)
                    original_sender_addr = (original_host, int(original_port_str))

                    logger.info(f"Processing SIP payload: '{sip_payload.strip()}' for original sender {original_sender_addr}")
                    
                    response_message = f"SIP/2.0 200 OK - Processed by {os.getenv('ZONE_A_HOSTNAME', 'unknown-signaler')}".encode()
                    
                    # --- MİMARİ GÜNCELLEMESİ: Yanıtı gateway'e geri gönderiyoruz ---
                    sock.sendto(response_message, addr)
                    logger.info(f"Sent response back to gateway at {addr}")

                except ValueError as e:
                     logger.warning(f"Could not parse original sender address '{original_sender_str}': {e}")
            else:
                logger.warning(f"Received malformed message (no '|' separator): {message_str}")

        except socket.timeout:
            continue # Timeout normal, döngüye devam et
        except Exception as e:
            logger.error(f"Error in signaling UDP loop: {e}")
    
    sock.close()
    logger.info("Signaling UDP server gracefully stopped.")

# --- API Sunucusu ---
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
    
    udp_thread = threading.Thread(target=start_udp_server, args=('0.0.0.0', SIP_SIGNALING_UDP_PORT), daemon=False)
    udp_thread.start()

    logger.info(f"Health check API server starting on port {SIP_SIGNALING_HTTP_PORT}")
    # Flask'i ana thread'de çalıştırarak sinyalleri yakalamasını sağlıyoruz.
    # Bu basit bir uygulama için yeterli.
    app.run(host='0.0.0.0', port=SIP_SIGNALING_HTTP_PORT)
    
    udp_thread.join()
    logger.info("Application has been shut down.")