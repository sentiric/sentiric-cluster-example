import socket
import logging
import os
import threading
from flask import Flask, jsonify

# NİHAİ DÜZELTME: Flask loglarını tamamen sustur
app = Flask(__name__)
log = logging.getLogger('werkzeug')
log.disabled = True
app.logger.disabled = True

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SIP_SIGNALING")

SIGNALING_PORT = int(os.getenv("SIGNAL_UDP_PORT", 13024))
HEALTH_PORT = int(os.getenv("HEALTH_API_PORT", 8080))

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

            if message_str == "LATENCY_PROBE":
                sock.sendto(b"PROBE_ACK", addr)
                continue

            logger.info(f"Received forwarded message from gateway {addr}")

            parts = message_str.split('|', 1)
            if len(parts) == 2:
                original_sender_str, sip_payload = parts
                
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

@app.route('/health')
def health_check():
    return jsonify({"status": "healthy"}), 200

def run_health_api():
    logger.info(f"Health check API server starting on port {HEALTH_PORT}")
    app.run(host='0.0.0.0', port=HEALTH_PORT)

if __name__ == '__main__':
    udp_thread = threading.Thread(target=start_udp_server, args=('0.0.0.0', SIGNALING_PORT), daemon=True)
    health_thread = threading.Thread(target=run_health_api, daemon=True)

    udp_thread.start()
    health_thread.start()
    
    udp_thread.join()
    health_thread.join()