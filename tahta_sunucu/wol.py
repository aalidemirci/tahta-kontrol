"""Uzaktan açma (Wake-on-LAN) sihirli paketi.

Tahtalar ayrı bir alt ağdaysa genel yayın yönlendiriciden geçmeyebilir; bu
yüzden paket birkaç hedefe birden gönderilir. Çalışıp çalışmadığı ancak
sahada görülür (tahtanın BIOS ayarına ve ağ donanımına bağlıdır).
"""

from __future__ import annotations

import ipaddress
import socket


def gonder(mac: str, son_ip: str = "") -> list[str]:
    temiz = mac.replace(":", "").replace("-", "").strip()
    if len(temiz) != 12:
        raise ValueError("MAC adresi geçersiz")
    paket = b"\xff" * 6 + bytes.fromhex(temiz) * 16
    hedefler = ["255.255.255.255"]
    if son_ip:
        hedefler.append(son_ip)
        for onek in (24, 22):
            try:
                ag = ipaddress.ip_network(f"{son_ip}/{onek}", strict=False)
                hedefler.append(str(ag.broadcast_address))
            except ValueError:
                pass
    gonderilen = []
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as soket:
        soket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for hedef in dict.fromkeys(hedefler):
            for port in (9, 7):
                try:
                    soket.sendto(paket, (hedef, port))
                    gonderilen.append(f"{hedef}:{port}")
                except OSError:
                    pass
    return gonderilen
