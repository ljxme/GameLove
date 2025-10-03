import os
import json
import socket
import random
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional

# 指定的 DNS 解析服务器列表（按优先级顺序）
DNS_SERVER_LIST = [
    "1.1.1.1",            # Cloudflare DNS
    "8.8.8.8",            # Google Public DNS
    "101.101.101.101",    # Quad101 DNS (台湾)
    "101.102.103.104",    # Quad101 DNS (台湾备用)
]

# 并发解析配置
MAX_WORKERS = 10

# 项目路径
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
ROOT_HOSTS_PATH = os.path.join(PROJECT_ROOT, "hosts")
ROOT_JSON_PATH = os.path.join(PROJECT_ROOT, "hosts.json")
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
SCRIPTS_HOSTS_DIR = os.path.join(SCRIPTS_DIR, "hosts")
SCRIPTS_HOSTS_PATH = os.path.join(SCRIPTS_HOSTS_DIR, "hosts")
SCRIPTS_JSON_PATH = os.path.join(SCRIPTS_HOSTS_DIR, "hosts.json")
README_PATH = os.path.join(PROJECT_ROOT, "README.md")


# ========== DNS 查询实现 ==========

def _encode_dns_query(domain: str, qtype: int = 1) -> bytes:
    """构造一个最简 DNS 查询报文，仅支持 A 记录。"""
    ident = random.getrandbits(16)
    flags = 0x0100  # 标准查询，递归可用
    qdcount = 1
    header = ident.to_bytes(2, "big") + flags.to_bytes(2, "big") + \
             qdcount.to_bytes(2, "big") + b"\x00\x00\x00\x00\x00\x00"

    parts = domain.strip('.').split('.')
    qname = b''.join(len(p).to_bytes(1, 'big') + p.encode('utf-8') for p in parts) + b'\x00'
    question = qname + qtype.to_bytes(2, 'big') + (1).to_bytes(2, 'big')
    return header + question


def _parse_dns_response_for_a(resp: bytes) -> List[str]:
    """解析 DNS 响应，提取 A 记录 IP 列表。"""
    if len(resp) < 12:
        return []
    qdcount = int.from_bytes(resp[4:6], 'big')
    ancount = int.from_bytes(resp[6:8], 'big')
    idx = 12
    for _ in range(qdcount):
        while True:
            if idx >= len(resp): return []
            l = resp[idx]; idx += 1
            if l == 0: break
            idx += l
        idx += 4
    ips: List[str] = []
    for _ in range(ancount):
        if idx + 10 > len(resp): break
        if (resp[idx] & 0xC0) == 0xC0:
            idx += 2
        else:
            while True:
                l = resp[idx]; idx += 1
                if l == 0: break
                idx += l
        rtype = int.from_bytes(resp[idx:idx+2], 'big'); idx += 2
        rclass = int.from_bytes(resp[idx:idx+2], 'big'); idx += 2
        idx += 4
        rdlen = int.from_bytes(resp[idx:idx+2], 'big'); idx += 2
        if idx + rdlen > len(resp): break
        if rtype == 1 and rclass == 1 and rdlen == 4:
            ip_bytes = resp[idx:idx+4]
            ips.append('.'.join(str(b) for b in ip_bytes))
        idx += rdlen
    return ips


def resolve_domain(domain: str, servers: List[str], timeout: float = 2.0) -> List[str]:
    """使用给定 DNS 服务器解析域名，返回 IP 列表。"""
    query = _encode_dns_query(domain)
    for server in servers:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(timeout)
                s.sendto(query, (server, 53))
                resp, _ = s.recvfrom(2048)
            ips = _parse_dns_response_for_a(resp)
            if ips:
                return ips
        except Exception:
            continue
    return []


def measure_ip_latency(ip: str, ports: List[int] = [443, 80], timeout: float = 1.0) -> Optional[float]:
    """测试 IP 的 TCP 延迟，返回最短成功连接时间。"""
    best: Optional[float] = None
    for port in ports:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        t0 = time.perf_counter()
        try:
            s.connect((ip, port))
            dt = time.perf_counter() - t0
            if best is None or dt < best:
                best = dt
        except Exception:
            pass
        finally:
            try: s.close()
            except Exception: pass
    return best


def choose_best_ip(ips: List[str]) -> Tuple[Optional[str], Optional[float], bool]:
    """选择最佳 IP：优先可达，选延迟最低。"""
    best_ip, best_latency, reachable = None, None, False
    for ip in ips:
        lat = measure_ip_latency(ip)
        if lat is not None:
            reachable = True
            if best_latency is None or lat < best_latency:
                best_latency, best_ip = lat, ip
    if not reachable and ips:
        best_ip = ips[0]
    return best_ip, best_latency, reachable


# ========== 数据加载 / 输出 ==========

def load_platform_domains() -> Dict[str, Dict[str, List[str]]]:
    """加载平台域名（优先 hosts.json，否则内置）。"""
    if os.path.exists(ROOT_JSON_PATH):
        try:
            with open(ROOT_JSON_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            platforms = data.get('platforms')
            if isinstance(platforms, dict):
                result: Dict[str, Dict[str, List[str]]] = {}
                for k, v in platforms.items():
                    arr = v.get('domains') if isinstance(v, dict) else None
                    if isinstance(arr, list):
                        result[k] = {'domains': arr}
                if result: return result
        except Exception: pass
    return {
        "steam": {"domains": [
            "steamcommunity.com","www.steamcommunity.com","store.steampowered.com",
            "api.steampowered.com","steamcdn-a.akamaihd.net","cdn.akamai.steamstatic.com",
            "community.akamai.steamstatic.com","store.akamai.steamstatic.com",
            "cdn.cloudflare.steamstatic.com","steam-chat.com"]},
        "epic": {"domains": [
            "launcher-public-service-prod06.ol.epicgames.com","epicgames.com","unrealengine.com",
            "fortnite.com","easyanticheat.net"]},
        "origin": {"domains": ["origin.com","ea.com","eaassets-a.akamaihd.net"]},
        "uplay": {"domains": ["ubisoft.com","ubi.com","uplay.com","static3.cdn.ubi.com"]},
        "battle.net": {"domains": ["battle.net","blizzard.com","battlenet.com.cn","blzstatic.cn"]},
        "gog": {"domains": ["gog.com","gog-statics.com","gogalaxy.com"]},
        "rockstar": {"domains": ["rockstargames.com","socialclub.rockstargames.com"]},
    }


def now_iso_cn() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')


def format_hosts_lines(pairs: List[Tuple[str, str]]) -> List[str]:
    return [f"{ip:<28}{domain}" for ip, domain in pairs]


def write_hosts_files(all_pairs, per_platform, update_time, failed_per_platform=None):
    os.makedirs(SCRIPTS_HOSTS_DIR, exist_ok=True)
    header = ["# GameLove Host Start"]
    footer = [
        f"# Update time: {update_time}",
        "# Update url: https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/hosts",
        "# Star me: https://github.com/artemisia1107/GameLove",
        "# GameLove Host End",
    ]
    def write_one(path, pairs, failed_domains=None):
        body = header + format_hosts_lines(pairs)
        if failed_domains:
            body += ['','# Below are unresolved/failed domains (commented):']
            for d in failed_domains:
                body.append(f"# {'0.0.0.0':<27}{d}")
        body += [''] + footer + ['']
        with open(path, 'w', encoding='utf-8') as f: f.write('\n'.join(body))
    write_one(ROOT_HOSTS_PATH, all_pairs)
    write_one(SCRIPTS_HOSTS_PATH, all_pairs)
    for pk, pairs in per_platform.items():
        file_key = pk.replace('.', '_') if pk != 'battle.net' else 'battle.net'
        path = os.path.join(SCRIPTS_HOSTS_DIR, f"hosts_{file_key}")
        failed = (failed_per_platform or {}).get(pk) or []
        write_one(path, pairs, failed_domains=failed)


def update_readme_hosts_block(update_time, results, chosen, platforms=None):
    try:
        with open(README_PATH, 'r', encoding='utf-8') as f: content = f.read()
    except Exception: return
    start_marker, end_marker = '# GameLove Host Start', '# GameLove Host End'
    start_idx, end_idx = content.find(start_marker), content.find(end_marker)
    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx: return
    domains_order = []
    if platforms:
        for v in platforms.values(): domains_order.extend(v.get('domains', []))
    lines = [start_marker]
    for domain in domains_order:
        ips = results.get(domain) or []
        ip = (chosen.get(domain, (None,None,False))[0]) or (ips[0] if ips else '')
        if ip: lines.append(f"{ip:<27}{domain}")
        else: lines.append(f"# {'0.0.0.0':<27}{domain}")
    lines.append(f"# Update time: {update_time}")
    lines.append("# Update url: https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/hosts")
    lines.append("# Star me: https://github.com/artemisia1107/GameLove")
    lines.append(end_marker)
    # 只保留主机块前后一个空行，避免页面留白过多
    prefix = content[:start_idx].rstrip("\n \t")
    suffix = content[end_idx+len(end_marker):].lstrip("\n \t")
    updated = prefix + "\n" + "\n".join(lines) + "\n" + suffix
    ts_line_pattern = r"^该内容会自动定时更新，数据更新时间：.*$"
    new_ts_line = f"该内容会自动定时更新，数据更新时间：{update_time}"
    if re.search(ts_line_pattern, updated, flags=re.MULTILINE):
        updated = re.sub(ts_line_pattern, new_ts_line, updated, flags=re.MULTILINE)
    with open(README_PATH, 'w', encoding='utf-8') as f: f.write(updated)


# ========== 主函数 ==========

def main():
    platforms = load_platform_domains()
    update_time = now_iso_cn()
    domains = [d for v in platforms.values() for d in v.get('domains', [])]
    start_all = time.perf_counter()
    results, chosen = {}, {}
    def worker(domain: str):
        ips = resolve_domain(domain, DNS_SERVER_LIST, timeout=2.0)
        best_ip, latency, reachable = choose_best_ip(ips) if ips else (None,None,False)
        return domain, ips, best_ip, latency, reachable
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for fut in as_completed({executor.submit(worker,d): d for d in domains}):
            domain, ips, best_ip, latency, reachable = fut.result()
            results[domain], chosen[domain] = ips, (best_ip,latency,reachable)
    total_time = time.perf_counter() - start_all
    all_pairs, per_platform, failed_per_platform = [], {pk: [] for pk in platforms}, {pk: [] for pk in platforms}
    for pk, v in platforms.items():
        for domain in v.get('domains', []):
            ips = results.get(domain) or []
            if ips:
                ip = chosen.get(domain,(None,None,False))[0] or ips[0]
                all_pairs.append((ip,domain)); per_platform[pk].append((ip,domain))
            else:
                failed_per_platform[pk].append(domain)
    write_hosts_files(all_pairs, per_platform, update_time, failed_per_platform)
    with open(ROOT_JSON_PATH,'w',encoding='utf-8') as f: json.dump({"update_time":update_time,"results":results},f,ensure_ascii=False,indent=2)
    with open(SCRIPTS_JSON_PATH,'w',encoding='utf-8') as f: json.dump({"update_time":update_time,"results":results},f,ensure_ascii=False,indent=2)
    update_readme_hosts_block(update_time, results, chosen, platforms)
    print(f"Updated hosts at {update_time} (workers={MAX_WORKERS}, elapsed={total_time:.2f}s)")


if __name__ == "__main__":
    main()
