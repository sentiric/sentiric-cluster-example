import socket
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("SIP_SIGNALING")

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

            logger.info(f"Received forwarded message from gateway {addr}: '{message_str}'")

            parts = message_str.split('|', 1)
            if len(parts) == 2:
                original_sender_str, sip_payload = parts
                original_host, original_port_str = original_sender_str.split(':')
                original_sender_addr = (original_host, int(original_port_str))

                logger.info(f"Processing call: {sip_payload.strip()}")
                logger.info(f"Sending '200 OK' response back to original caller {original_sender_addr}")
                
                response_message = b"SIP/2.0 200 OK - Processed by this server"
                sock.sendto(response_message, original_sender_addr)
            else:
                logger.warning(f"Received malformed message: {message_str}")

        except Exception as e:
            logger.error(f"Error in signaling UDP loop: {e}")

if __name__ == '__main__':
    start_udp_server('0.0.0.0', 13024)