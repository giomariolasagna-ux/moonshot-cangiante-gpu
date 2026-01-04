import json, socket
from typing import Dict, Any

class TDSenderUDP:
    def __init__(self, host: str, port: int):
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send(self, payload: Dict[str, Any]) -> None:
        s = json.dumps(payload, ensure_ascii=False)
        self.sock.sendto(s.encode("utf-8"), self.addr)
