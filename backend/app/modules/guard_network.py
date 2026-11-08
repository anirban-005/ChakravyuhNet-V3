import asyncio
import logging
import os
import psutil
import httpx

logger = logging.getLogger("AntigravityAgent.Network")

C2_URL = os.getenv("C2_SERVER_URL", "http://127.0.0.1:8001")

async def start_network_guard():
    logger.info("Network Guard started.")
    known_connections = set()
    
    async with httpx.AsyncClient() as client:
        while True:
            try:
                # Use kind='inet' as per user feedback
                conns = psutil.net_connections(kind='inet')
                for conn in conns:
                    if conn.status == 'ESTABLISHED':
                        raddr = conn.raddr
                        if raddr:
                            ip, port = raddr
                            # Filter out local loopback to reduce noise
                            if ip.startswith("127.") or ip == "::1" or ip == "0.0.0.0":
                                continue
                            
                            conn_id = f"{ip}:{port}"
                            if conn_id not in known_connections:
                                known_connections.add(conn_id)
                                msg = f"New external connection established: {ip}:{port}"
                                logger.warning(msg)
                                
                                payload = {
                                    "module": "network",
                                    "message": msg,
                                    "details": {"remote_ip": ip, "remote_port": port, "pid": conn.pid}
                                }
                                try:
                                    await client.post(f"{C2_URL}/api/alerts", json=payload, timeout=5.0)
                                except Exception as e:
                                    logger.error(f"Failed to send alert to C2: {e}")
            except Exception as e:
                logger.error(f"Error in network loop: {e}")
                
            await asyncio.sleep(5)
