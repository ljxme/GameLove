#!/usr/bin/env python3
import subprocess
from ping3 import ping
from datetime import datetime
import os

HOSTS_DIR = "../hosts"
STEAM_DOMAINS = ["store.steampowered.com", "steamcommunity.com", "cdn.cloudflare.steamstatic.com"]
EPIC_DOMAINS = ["www.epicgames.com", "launcher-public-service-prod06.ol.epicgames.com", "epicgames-download1.akamaized.net"]

def get_ips(domain):
    result = subprocess.run(["nslookup", domain], capture_output=True, text=True)
    ips = []
    for line in result.stdout.splitlines():
        if "Address:" in line and not line.strip().endswith(domain):
            ips.append(line.split()[-1])
    return ips

def best_ip(domain):
    ips = get_ips(domain)
    best = None
    lowest = 9999
    for ip in ips:
        latency = ping(ip, timeout=2)
        if latency is None:
            latency = 9999
        if latency < lowest:
            lowest = latency
            best = ip
    return best

def generate_hosts(domains, filename):
    with open(filename, "w") as f:
        f.write(f"# Generated hosts - {datetime.now()}\n")
        for domain in domains:
            ip = best_ip(domain)
            if ip:
                f.write(f"{ip} {domain}\n")

os.makedirs(HOSTS_DIR, exist_ok=True)
generate_hosts(STEAM_DOMAINS, f"{HOSTS_DIR}/steam_hosts")
generate_hosts(EPIC_DOMAINS, f"{HOSTS_DIR}/epic_hosts")

print("Hosts files generated successfully!")
