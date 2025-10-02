import os
import json
import socket
import random
import time
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
MAX_WORKERS = 10  # 可根据需要调整并发度

# 项目路径（相对脚本所在位置）
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
ROOT_HOSTS_PATH = os.path.join(PROJECT_ROOT, "hosts")
ROOT_JSON_PATH = os.path.join(PROJECT_ROOT, "hosts.json")
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
SCRIPTS_HOSTS_DIR = os.path.join(SCRIPTS_DIR, "hosts")
SCRIPTS_HOSTS_PATH = os.path.join(SCRIPTS_HOSTS_DIR, "hosts")
SCRIPTS_JSON_PATH = os.path.join(SCRIPTS_HOSTS_DIR, "hosts.json")
README_PATH = os.path.join(PROJECT_ROOT, "README.md")


def _encode_dns_query(domain: str, qtype: int = 1) -> bytes:
    """构造一个最简 DNS 查询报文（仅支持 A 记录）。

    Args:
        domain: 查询的域名
        qtype: 查询类型，默认 1(A)

    Returns:
        原始 UDP 报文 bytes
    """
    # Header
    ident = random.getrandbits(16)
    flags = 0x0100  # 标准查询，递归可用
    qdcount = 1
    ancount = 0
    nscount = 0
    arcount = 0
    header = ident.to_bytes(2, "big") + flags.to_bytes(2, "big") + \
             qdcount.to_bytes(2, "big") + ancount.to_bytes(2, "big") + \
             nscount.to_bytes(2, "big") + arcount.to_bytes(2, "big")

    # Question
    parts = domain.strip('.').split('.')
    qname = b''.join(len(p).to_bytes(1, 'big') + p.encode('utf-8') for p in parts) + b'\x00'
    qclass = 1  # IN
    question = qname + qtype.to_bytes(2, 'big') + qclass.to_bytes(2, 'big')

    return header + question


def _parse_dns_response_for_a(resp: bytes) -> List[str]:
    """解析 DNS 响应，提取 A 记录 IP 列表。"""
    if len(resp) < 12:
        return []
    # 解析头部
    qdcount = int.from_bytes(resp[4:6], 'big')
    ancount = int.from_bytes(resp[6:8], 'big')

    # 跳过 Question 区
    idx = 12
    for _ in range(qdcount):
        # 读取 QNAME（标签序列）
        while True:
            if idx >= len(resp):
                return []
            l = resp[idx]
            idx += 1
            if l == 0:
                break
            idx += l
        # 跳过 QTYPE + QCLASS
        idx += 4

    ips: List[str] = []
    # 读取 Answer RRs
    for _ in range(ancount):
        if idx + 10 > len(resp):
            break
        # NAME（可能是压缩指针，两字节）
        # 如果是指针，前两位为 11，长度为两字节；否则为标签序列。
        name_len_or_ptr = resp[idx]
        if (name_len_or_ptr & 0xC0) == 0xC0:
            # 压缩指针，跳过两字节
            idx += 2
        else:
            # 标签序列
            while True:
                l = resp[idx]
                idx += 1
                if l == 0:
                    break
                idx += l

        rtype = int.from_bytes(resp[idx:idx+2], 'big'); idx += 2
        rclass = int.from_bytes(resp[idx:idx+2], 'big'); idx += 2
        # TTL
        idx += 4
        rdlen = int.from_bytes(resp[idx:idx+2], 'big'); idx += 2
        if idx + rdlen > len(resp):
            break

        if rtype == 1 and rclass == 1 and rdlen == 4:
            ip_bytes = resp[idx:idx+4]
            ips.append('.'.join(str(b) for b in ip_bytes))
        # 跳到下一个 RR
        idx += rdlen

    return ips


def resolve_domain(domain: str, servers: List[str], timeout: float = 2.0) -> List[str]:
    """使用给定 DNS 服务器按序解析域名的 A 记录，返回 IP 列表。"""
    query = _encode_dns_query(domain, qtype=1)
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
    """尝试与给定 IP 的常用端口建立 TCP 连接，返回最短连接时间（秒）。"""
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
            try:
                s.close()
            except Exception:
                pass
    return best


def choose_best_ip(ips: List[str]) -> Tuple[Optional[str], Optional[float], bool]:
    """在解析出的多个 IP 中选择优质 IP：优先可达、其次最低连接时延。"""
    best_ip: Optional[str] = None
    best_latency: Optional[float] = None
    reachable = False
    for ip in ips:
        lat = measure_ip_latency(ip)
        if lat is not None:
            reachable = True
            if best_latency is None or lat < best_latency:
                best_latency = lat
                best_ip = ip
    # 如无可达 IP，退回第一个解析 IP（不可达标记）
    if not reachable and ips:
        best_ip = ips[0]
    return best_ip, best_latency, reachable


def load_platform_domains() -> Dict[str, Dict[str, List[str]]]:
    """加载各平台域名列表。
    优先从根目录 hosts.json 的 platforms 字段读取；若不可用，则使用脚本内置回退。
    返回结构：{ platform_key: { "domains": [domain1, ...] } }
    """
    # 尝试从现有 hosts.json 读取
    if os.path.exists(ROOT_JSON_PATH):
        try:
            with open(ROOT_JSON_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            platforms = data.get('platforms')
            if isinstance(platforms, dict):
                # 规范化为仅保留 domains 数组
                result: Dict[str, Dict[str, List[str]]] = {}
                for k, v in platforms.items():
                    arr = v.get('domains') if isinstance(v, dict) else None
                    if isinstance(arr, list) and all(isinstance(x, str) for x in arr):
                        result[k] = { 'domains': arr }
                if result:
                    return result
        except Exception:
            pass

    # 内置回退（与当前仓库 hosts.json 中平台域名保持一致）
    return {
        "steam": {
            "domains": [
                "steamcommunity.com",
                "store.steampowered.com",
                "api.steampowered.com",
                "help.steampowered.com",
                "steamcdn-a.akamaihd.net",
                "steamuserimages-a.akamaihd.net",
                "steamstore-a.akamaihd.net",
            ]
        },
        "epic": {
            "domains": [
                "launcher-public-service-prod06.ol.epicgames.com",
                "epicgames.com",
                "unrealengine.com",
                "fortnite.com",
                "easyanticheat.net",
            ]
        },
        "origin": {
            "domains": [
                "origin.com",
                "ea.com",
                "eaassets-a.akamaihd.net",
            ]
        },
        "uplay": {
            "domains": [
                "ubisoft.com",
                "ubi.com",
                "uplay.com",
                "static3.cdn.ubi.com",
            ]
        },
        "battle.net": {
            "domains": [
                "battle.net",
                "blizzard.com",
                "battlenet.com.cn",
                "blzstatic.cn",
            ]
        },
        "gog": {
            "domains": [
                "gog.com",
                "gog-statics.com",
                "gogalaxy.com",
            ]
        },
        "rockstar": {
            "domains": [
                "rockstargames.com",
                "socialclub.rockstargames.com",
            ]
        },
    }


def now_iso_cn() -> str:
    """按东八区生成 ISO 时间字符串（到秒）。"""
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')


def format_hosts_lines(pairs: List[Tuple[str, str]]) -> List[str]:
    """格式化 hosts 行，左列为 IP 左对齐，右列为域名。"""
    lines = []
    for ip, domain in pairs:
        lines.append(f"{ip:<28}{domain}")
    return lines


def write_hosts_files(all_pairs: List[Tuple[str, str]], per_platform: Dict[str, List[Tuple[str, str]]], update_time: str) -> None:
    """生成根 hosts、scripts/hosts/hosts 以及平台专用 hosts 文件。"""
    os.makedirs(SCRIPTS_HOSTS_DIR, exist_ok=True)

    header = ["# GameLove Host Start"]
    footer = [
        f"# Update time: {update_time}",
        "# Update url: https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/hosts",
        "# Star me: https://github.com/artemisia1107/GameLove",
        "# GameLove Host End",
    ]

    def write_one(path: str, pairs: List[Tuple[str, str]]):
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(header + format_hosts_lines(pairs) + [''] + footer + ['']))

    # 根 hosts
    write_one(ROOT_HOSTS_PATH, all_pairs)
    # scripts/hosts/hosts
    write_one(SCRIPTS_HOSTS_PATH, all_pairs)

    # 平台文件
    for pk, pairs in per_platform.items():
        # 将点替换为下划线或保留特殊文件名（如 battle.net 用 hosts_battle.net）
        file_key = pk.replace('.', '_') if pk != 'battle.net' else 'battle.net'
        path = os.path.join(SCRIPTS_HOSTS_DIR, f"hosts_{file_key}")
        write_one(path, pairs)


def build_hosts_json(
    platforms: Dict[str, Dict[str, List[str]]],
    results: Dict[str, List[str]],
    chosen: Dict[str, Tuple[Optional[str], Optional[float], bool]],
    update_time: str,
    total_time: float,
) -> Dict:
    """构建 hosts.json 数据结构，尽量与现有结构对齐。"""
    # 汇总
    domains = [d for v in platforms.values() for d in v.get('domains', [])]
    success_domains = [d for d in domains if results.get(d)]
    failed_domains = [d for d in domains if not results.get(d)]

    # all_hosts 映射（选择策略后的 IP 作为首选）
    all_hosts = {d: (chosen[d][0] or results[d][0]) for d in success_domains}

    # 统计
    summary = {
        "total_domains": len(domains),
        "success_count": len(success_domains),
        "failed_count": len(failed_domains),
        "success_rate": f"{(len(success_domains)/len(domains)*100):.1f}%" if domains else "0.0%",
        "update_time": update_time,
    }

    urls = {
        "hosts_file": "https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/hosts",
        "json_api": "https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/hosts.json",
        "repository": "https://github.com/artemisia1107/GameLove",
    }

    # 方法及解析器配置（简化）
    method_stats = {
        "nslookup": {"success": 0, "failed": 0, "total": 0},
        "doh": {"success": 0, "failed": 0, "total": 0},
        "dns": {"success": len(success_domains), "failed": len(failed_domains), "total": len(domains)},
        "ping": {"success": 0, "failed": 0, "total": 0},
    }
    resolver_config = {
        "parallel_mode": True,
        "max_workers": MAX_WORKERS,
        "smart_resolver": True,
    }

    # 平台统计
    platform_stats: Dict[str, Dict[str, str]] = {}
    for pk, v in platforms.items():
        ds = v.get('domains', [])
        s = sum(1 for d in ds if results.get(d))
        platform_stats[_display_name(pk)] = {
            "static_domains": len(ds),
            "success": s,
            "success_rate": f"{(s/len(ds)*100):.1f}%" if ds else "0.0%",
        }

    # 域名指标（包含可达性与所选 IP）
    domain_metrics: Dict[str, Dict[str, object]] = {}
    latencies: List[float] = []
    for d in domains:
        ips = results.get(d, [])
        chosen_ip, latency, reachable = chosen.get(d, (None, None, False))
        if latency is not None:
            latencies.append(latency)
        domain_metrics[d] = {
            "consensus": 1 if ips else 0,
            "reachability_score": "1.000" if reachable else ("0.000" if ips else "0.000"),
            "service_reachable": bool(reachable),
            "chosen_ip": chosen_ip if chosen_ip else (ips[0] if ips else None),
        }

    # 性能统计
    avg_resp = f"{(sum(latencies)/len(latencies)):.2f}s" if latencies else "-"
    max_resp = f"{(max(latencies)):.2f}s" if latencies else "-"
    perf = {
        "total_time": f"{total_time:.2f}s",
        "avg_response_time": avg_resp,
        "max_response_time": max_resp,
        "domains_per_second": f"{(len(domains)/total_time):.2f}" if total_time > 0 else "-",
    }

    data = {
        "summary": summary,
        "all_hosts": all_hosts,
        "failed_domains": failed_domains,
        "urls": urls,
        "performance_stats": perf,
        "method_stats": method_stats,
        "resolver_config": resolver_config,
        "platform_stats": platform_stats,
        "domain_metrics": domain_metrics,
        "platforms": platforms,
    }
    return data


def _display_name(platform_key: str) -> str:
    mapping = {
        "steam": "Steam",
        "epic": "Epic",
        "origin": "Origin",
        "uplay": "Uplay",
        "battle.net": "Battle.net",
        "gog": "GOG",
        "rockstar": "Rockstar",
    }
    return mapping.get(platform_key, platform_key)


# README 主机块自动更新
README_BLOCK_DOMAINS_ORDER = [
    # Steam
    "steamcommunity.com",
    "store.steampowered.com",
    "api.steampowered.com",
    "help.steampowered.com",
    "steamcdn-a.akamaihd.net",
    "steamuserimages-a.akamaihd.net",
    "steamstore-a.akamaihd.net",

    # Epic
    "launcher-public-service-prod06.ol.epicgames.com",
    "epicgames.com",
    "unrealengine.com",
    "fortnite.com",
    "easyanticheat.net",

    # Origin
    "origin.com",
    "ea.com",
    "eaassets-a.akamaihd.net",
    "ssl-lvlt.cdn.ea.com",

    # Uplay
    "ubisoft.com",
    "ubi.com",
    "uplay.com",
    "static3.cdn.ubi.com",

    # Battle.net
    "battle.net",
    "blizzard.com",
    "battlenet.com.cn",
    "blzstatic.cn",

    # GOG
    "gog.com",
    "gog-statics.com",
    "gogalaxy.com",

    # Rockstar
    "rockstargames.com",
    "socialclub.rockstargames.com",
]


def update_readme_hosts_block(update_time: str, results: Dict[str, List[str]], chosen: Dict[str, Tuple[Optional[str], Optional[float], bool]], platforms: Dict[str, Dict[str, List[str]]] = None) -> None:
    """更新 README 中 # GameLove Host Start/End 之间的主机块与时间戳。"""
    try:
        with open(README_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        return

    start_marker = '# GameLove Host Start'
    end_marker = '# GameLove Host End'
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)
    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx:
        return

    # 以 platforms 中的域名为准；若缺失则使用内置顺序常量
    domains_order: List[str] = []
    if platforms and isinstance(platforms, dict):
        for v in platforms.values():
            domains_order.extend(v.get('domains', []))
    if not domains_order:
        domains_order = README_BLOCK_DOMAINS_ORDER

    lines = [start_marker]
    for domain in domains_order:
        ips = results.get(domain) or []
        ip = (chosen.get(domain, (None, None, False))[0]) or (ips[0] if ips else '')
        if ip:
            lines.append(f"{ip:<27}{domain}")
        else:
            lines.append(f"{'0.0.0.0':<27}{domain}")
    lines.append(f"# Update time: {update_time}")
    lines.append("# Update url: https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/hosts")
    lines.append("# Star me: https://github.com/artemisia1107/GameLove")
    lines.append(end_marker)

    new_block = "\n" + "\n".join(lines) + "\n"

    pre = content[:start_idx]
    post = content[end_idx + len(end_marker):]
    updated = pre + new_block + post

    import re
    # 同步下方中文提示时间戳（更宽松的匹配，确保替换成功）
    # 精确替换中文提示行
    ts_line_pattern = r"^该内容会自动定时更新，数据更新时间：.*$"
    new_ts_line = f"该内容会自动定时更新，数据更新时间：{update_time}"
    if re.search(ts_line_pattern, updated, flags=re.MULTILINE):
        updated = re.sub(ts_line_pattern, new_ts_line, updated, flags=re.MULTILINE)

    try:
        with open(README_PATH, 'w', encoding='utf-8') as f:
            f.write(updated)
    except Exception:
        pass


def main() -> None:
    platforms = load_platform_domains()
    update_time = now_iso_cn()

    domains = [d for v in platforms.values() for d in v.get('domains', [])]
    start_all = time.perf_counter()

    # 并发解析并选择优质 IP
    results: Dict[str, List[str]] = {}
    chosen: Dict[str, Tuple[Optional[str], Optional[float], bool]] = {}

    def worker(domain: str):
        ips = resolve_domain(domain, DNS_SERVER_LIST, timeout=2.0)
        best_ip, latency, reachable = choose_best_ip(ips) if ips else (None, None, False)
        return domain, ips, best_ip, latency, reachable

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_map = {executor.submit(worker, d): d for d in domains}
        for fut in as_completed(future_map):
            domain, ips, best_ip, latency, reachable = fut.result()
            results[domain] = ips
            chosen[domain] = (best_ip, latency, reachable)

    total_time = time.perf_counter() - start_all

    # 汇总全部与分平台的 IP->域名对（使用选择策略后的 IP）
    all_pairs: List[Tuple[str, str]] = []
    per_platform: Dict[str, List[Tuple[str, str]]] = {pk: [] for pk in platforms.keys()}
    for pk, v in platforms.items():
        for domain in v.get('domains', []):
            ips = results.get(domain) or []
            if ips:
                ip = chosen.get(domain, (None, None, False))[0] or ips[0]
                all_pairs.append((ip, domain))
                per_platform[pk].append((ip, domain))

    # 写入 hosts 文件们
    write_hosts_files(all_pairs, per_platform, update_time)

    # 写入 JSON 文件（根与 scripts/hosts）
    data = build_hosts_json(platforms, results, chosen, update_time, total_time)
    for path in (ROOT_JSON_PATH, SCRIPTS_JSON_PATH):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # 自动更新 README 主机块
    update_readme_hosts_block(update_time, results, chosen, platforms)

    print(f"Updated hosts and hosts.json at {update_time} (workers={MAX_WORKERS}, elapsed={total_time:.2f}s)")


if __name__ == "__main__":
    main()