"""
GameLove Hosts生成脚本

职责：
- 并发解析各游戏平台域名的 A 记录；
- 测试可达性与延迟，挑选最优 IP；
- 生成根 hosts、平台专用 hosts、JSON 结果，以及更新 README 中的主机块；
- 对解析失败的域名进行注释化处理（仅提示，不影响解析）。

注意：本脚本的输出格式（列宽、标记文本等）已在常量中固定，修改时请保持不变以避免影响下游展示。
"""

import os
import json
import hashlib
import argparse
import socket
import random
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Optional

# 指定的 DNS 解析服务器列表（按优先级顺序，均为海外公共 DNS）
# 参考：国内外DNS服务器推荐列表 | Deep Router（https://deeprouter.org/article/dns-servers-guide）
# 推荐顺序（结合文章建议）：Google → NextDNS → AdGuard → Quad9 → OpenDNS → Cloudflare；其他为补充。
# 注：Quad9/AdGuard/CleanBrowsing/ControlD 等可能对恶意/不良域名做拦截，若需纯解析请将其后移或移除。
DNS_SERVER_LIST = [
    # —— 推荐优先级 ——
    "8.8.8.8",            # Google Public DNS（主）
    "8.8.4.4",            # Google Public DNS（备）
    "45.90.28.0",         # NextDNS（主，通用地址）
    "45.90.30.0",         # NextDNS（备，通用地址）
    "94.140.14.14",       # AdGuard Public DNS（主）
    "94.140.15.15",       # AdGuard Public DNS（备）
    "9.9.9.9",            # Quad9（主，安全拦截）
    "149.112.112.112",    # Quad9（备，安全拦截）
    "208.67.222.222",     # OpenDNS（Cisco，主）
    "208.67.220.220",     # OpenDNS（Cisco，备）
    "1.1.1.1",            # Cloudflare（主）
    "1.0.0.1",            # Cloudflare（备）

    # —— 其他稳定公共解析（补充） ——
    "185.228.168.9",      # CleanBrowsing（安全过滤，主）
    "185.228.169.9",      # CleanBrowsing（安全过滤，备）
    "76.76.2.1",          # ControlD Free（恶意域名阻断）
    "46.250.226.242",     # Blahdns（新加坡，IPv4）
    "64.6.64.6",          # UltraDNS Public（原 Verisign，主）
    "64.6.65.6",          # UltraDNS Public（原 Verisign，备）
    "101.101.101.101",    # Quad101（TWNIC，主）
    "101.102.103.104",    # Quad101（备）
    "84.200.69.80",       # DNS.WATCH（德国）
    "8.26.56.26",         # Comodo Secure DNS
    "185.222.222.222",    # DNS.SB（主）
    "45.11.45.11",        # DNS.SB（备）
    "77.88.8.8",          # Yandex DNS（主）
    "77.88.8.1",          # Yandex DNS（备）
    "74.82.42.42",        # Hurricane Electric（HE）
    "172.104.93.80",      # jp.tiar.app（日本社区 DNS）
]

# 并发解析配置
MAX_WORKERS = 16
# DNS 查询参数（可通过 CLI 覆盖）
DNS_QUERY_TIMEOUT = 1.0   # 每个DNS服务器的UDP超时（秒）
DNS_RACE_WORKERS = 6      # 每域名并行查询的DNS服务器并发数
# IP 延迟检测参数（可通过 CLI 覆盖）
LATENCY_TIMEOUT = 0.6     # TCP 连接超时（秒），更短以加速整体检测
MAX_IP_PROBES_PER_DOMAIN = 3  # 每域名参与延迟检测的IP数量上限（可通过 CLI 覆盖）
LATENCY_WORKERS = 16      # 延迟检测线程池大小（可通过 CLI 覆盖）
_LATENCY_EXECUTOR: Optional[ThreadPoolExecutor] = None

def _get_latency_executor() -> ThreadPoolExecutor:
    global _LATENCY_EXECUTOR
    if _LATENCY_EXECUTOR is None:
        _LATENCY_EXECUTOR = ThreadPoolExecutor(max_workers=max(2, LATENCY_WORKERS))
    return _LATENCY_EXECUTOR

def _shutdown_latency_executor() -> None:
    global _LATENCY_EXECUTOR
    if _LATENCY_EXECUTOR is not None:
        try:
            _LATENCY_EXECUTOR.shutdown(wait=False, cancel_futures=True)  # Py3.9+
        except TypeError:
            _LATENCY_EXECUTOR.shutdown(wait=False)
        _LATENCY_EXECUTOR = None

# 域名健康状态与快速失败策略
HEALTH_FAIL_SKIP_THRESHOLD = 5   # 连续失败达到阈值后仅做最少尝试
HEALTH_RETRY_BASE = 1            # 基础重试次数（更保守以减少总耗时）
HEALTH_DECAY_STEP = 3            # 每累计N次失败，重试数递减1
DOMAIN_HEALTH: Dict[str, int] = {}

# 输出格式与文本常量（请谨慎改动以保持行为不变）
HOSTS_IP_COLUMN_WIDTH = 28         # 根/平台 hosts 列宽
README_IP_COLUMN_WIDTH = 27        # README 主机块列宽
FAILED_IP_PLACEHOLDER = "0.0.0.0"  # 失败域名注释中的占位 IP

START_MARKER = '# GameLove Host Start'
END_MARKER = '# GameLove Host End'
UPDATE_URL = 'https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/hosts'
STAR_URL = 'https://github.com/artemisia1107/GameLove'

# 项目路径
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
ROOT_HOSTS_PATH = os.path.join(PROJECT_ROOT, "hosts")
ROOT_JSON_PATH = os.path.join(PROJECT_ROOT, "hosts.json")
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")
SCRIPTS_HOSTS_DIR = os.path.join(SCRIPTS_DIR, "hosts")
SCRIPTS_HOSTS_PATH = os.path.join(SCRIPTS_HOSTS_DIR, "hosts")
SCRIPTS_JSON_PATH = os.path.join(SCRIPTS_HOSTS_DIR, "hosts.json")
README_PATH = os.path.join(PROJECT_ROOT, "README.md")
SCRIPTS_PLATFORM_PATH = os.path.join(SCRIPTS_DIR, "platforms.json")


# ========== DNS 查询实现 ==========

def _encode_dns_query(domain: str, qtype: int = 1) -> bytes:
    """构造最简 DNS 查询报文。

    参数：
    - domain: 目标域名。
    - qtype: 记录类型，默认为 A(1)。

    返回：字节串形式的查询报文。
    """
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
    """解析 DNS 响应，提取 A 记录的 IPv4 列表。

    参数：
    - resp: 原始 DNS 响应报文。

    返回：提取到的 IPv4 地址字符串列表，若无则为空列表。
    """
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


def resolve_domain(domain: str, servers: List[str], timeout: float = DNS_QUERY_TIMEOUT, max_parallel: int = DNS_RACE_WORKERS) -> List[str]:
    """并行竞速解析域名：同时向多台DNS服务器查询，优先返回最先成功的结果。

    - 限制并发数为 `max_parallel`，减少对外部DNS的瞬时压力；
    - 采用较短超时以避免长时间等待慢速/不可达服务器；
    - 在获得首个有效结果后，取消未开始的任务并忽略其结果。
    """
    query = _encode_dns_query(domain)
    if not servers:
        return []
    def _one(server: str) -> List[str]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(timeout)
                s.sendto(query, (server, 53))
                resp, _ = s.recvfrom(2048)
            ips = _parse_dns_response_for_a(resp)
            return ips
        except Exception:
            return []
    result: List[str] = []
    max_parallel = max(1, min(max_parallel, len(servers)))
    # 选择前 max_parallel 个服务器优先查询，避免全量并发带来的负载
    candidates = servers[:max_parallel]
    with ThreadPoolExecutor(max_workers=max_parallel) as ex:
        futures = [ex.submit(_one, srv) for srv in candidates]
        for fut in as_completed(futures):
            try:
                ips = fut.result()
            except Exception:
                ips = []
            if ips:
                result = ips
                # 尝试取消尚未开始的任务，快速收尾
                for f in futures:
                    if f is not fut:
                        f.cancel()
                break
    # 若首批未得到结果，降级为顺序查询剩余服务器
    if not result and len(servers) > max_parallel:
        for server in servers[max_parallel:]:
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
    return result


def measure_ip_latency(ip: str, ports: List[int] = [443, 80], timeout: float = LATENCY_TIMEOUT) -> Optional[float]:
    """并行检测 TCP 连接耗时，优先443端口，失败后回退到80端口。

    实现：同时启动 443 与 80 的连接任务；优先等待 443 的结果，若失败或超时，再取 80 的结果；
    若两者均失败，返回 None。返回值为成功端口的连接耗时（秒）。
    """
    # 准备任务
    def _connect(port: int) -> Optional[float]:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        t0 = time.perf_counter()
        try:
            s.connect((ip, port))
            return time.perf_counter() - t0
        except Exception:
            return None
        finally:
            try: s.close()
            except Exception: pass

    # 使用全局线程池并行任务，减少频繁创建销毁开销
    ex = _get_latency_executor()
    futs: Dict[int, any] = {p: ex.submit(_connect, p) for p in ports}
    # 优先尝试 443
    if 443 in futs:
        try:
            lat = futs[443].result(timeout=timeout)
            if lat is not None:
                return lat
        except Exception:
            pass
    # 回退尝试其他端口（如 80）
    for p in ports:
        if p == 443:
            continue
        try:
            lat = futs[p].result(timeout=timeout)
            if lat is not None:
                return lat
        except Exception:
            pass
    return None


def choose_best_ip(ips: List[str]) -> Tuple[Optional[str], Optional[float], bool]:
    """从候选 IP 中选择最佳项。

    策略：优先可达（有 TCP 端口可连），其间选延迟最低者；若均不可达但有候选，则返回第一个。

    返回：(最佳 IP, 最佳延迟, 是否可达)。
    """
    best_ip, best_latency, reachable = None, None, False
    # 限制参与检测的IP数量，降低总检测成本
    candidates = ips[:MAX_IP_PROBES_PER_DOMAIN] if ips else []
    for ip in candidates:
        lat = measure_ip_latency(ip)
        if lat is not None:
            reachable = True
            if best_latency is None or lat < best_latency:
                best_latency, best_ip = lat, ip
    if not reachable and ips:
        best_ip = ips[0]
    return best_ip, best_latency, reachable


# ========== 数据加载 / 输出 ==========

# 平台域名配置（默认内置 + 外部配置覆盖）
DEFAULT_PLATFORMS: Dict[str, Dict[str, List[str]]] = {
    "steam": {
        "domains": [
            "steamcommunity.com",
            "www.steamcommunity.com",
            "store.steampowered.com",
            "api.steampowered.com",
            "steamcdn-a.akamaihd.net",
            "cdn.akamai.steamstatic.com",
            "community.akamai.steamstatic.com",
            "store.akamai.steamstatic.com",
            "cdn.cloudflare.steamstatic.com",
            "steam-chat.com"
        ]
    },
    "epic": {
        "domains": [
            "launcher-public-service-prod06.ol.epicgames.com",
            "epicgames.com",
            "unrealengine.com",
            "fortnite.com",
            "easyanticheat.net"
        ]
    },
    "origin": {
        "domains": [
            "origin.com",
            "ea.com",
            "eaassets-a.akamaihd.net"
        ]
    },
    "uplay": {
        "domains": [
            "ubisoft.com",
            "ubi.com",
            "uplay.com",
            "static3.cdn.ubi.com"
        ]
    },
    "battle.net": {
        "domains": [
            "battle.net",
            "blizzard.com",
            "battlenet.com.cn",
            "blzstatic.cn"
        ]
    },
    "gog": {
        "domains": [
            "gog.com",
            "gog-statics.com",
            "gogalaxy.com"
        ]
    },
    "rockstar": {
        "domains": [
            "rockstargames.com",
            "socialclub.rockstargames.com"
        ]
    },
}

# 不在导入时读取外部文件，默认在运行期通过 hosts.json 加载


DOMAIN_LABEL_RE = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$")

def canonicalize_domain(d: str) -> str:
    """域名归一化：去空白、去结尾点、转小写；支持 IDN punycode。"""
    d = (d or "").strip().rstrip('.') .lower()
    if not d:
        return ""
    try:
        # 将可能的非 ASCII 域名转换为 punycode，保持解析一致性
        d = d.encode('idna').decode('ascii')
    except Exception:
        pass
    return d

def is_valid_domain(d: str) -> bool:
    """校验域名格式：长度、标签合法性、至少一个点。"""
    if not d or len(d) > 253 or '.' not in d:
        return False
    labels = d.split('.')
    return all(DOMAIN_LABEL_RE.match(label or '') for label in labels)

def validate_and_normalize_platforms(raw: Dict[str, Dict[str, List[str]]]) -> Tuple[Dict[str, Dict[str, List[str]]], List[str]]:
    """校验并归一化平台域名配置。

    返回 (规范化后的平台配置, 警告列表)。
    规则：
    - 平台名为非空字符串；
    - domains 为字符串列表；
    - 每个域名归一化并进行格式校验；
    - 去重并保留顺序；
    - 过滤空/非法域名，记录警告。
    """
    warnings: List[str] = []
    result: Dict[str, Dict[str, List[str]]] = {}
    if not isinstance(raw, dict):
        return ({}, ["平台配置须为对象（字典）。已忽略外部配置。"])
    for pk, v in raw.items():
        if not isinstance(pk, str) or not pk.strip():
            warnings.append(f"发现非法平台键：{pk!r}（需非空字符串），已跳过")
            continue
        domains = []
        if isinstance(v, dict) and isinstance(v.get('domains'), list):
            seen = set()
            for d in v['domains']:
                if not isinstance(d, str):
                    warnings.append(f"平台 {pk} 包含非字符串域名项，已跳过：{d!r}")
                    continue
                nd = canonicalize_domain(d)
                if not nd:
                    warnings.append(f"平台 {pk} 存在空域名项，已跳过")
                    continue
                if not is_valid_domain(nd):
                    warnings.append(f"平台 {pk} 存在非法域名，已跳过：{nd}")
                    continue
                if nd in seen:
                    continue
                seen.add(nd); domains.append(nd)
        else:
            warnings.append(f"平台 {pk} 配置缺少 domains 列表，已跳过")
            continue
        result[pk] = {"domains": domains}
    return result, warnings

def load_platform_domains() -> Dict[str, Dict[str, List[str]]]:
    """加载平台域名配置：仅从根目录 hosts.json 的 platforms 字段读取；无效则回退默认。"""
    if os.path.exists(ROOT_JSON_PATH):
        try:
            with open(ROOT_JSON_PATH, 'r', encoding='utf-8') as f:
                root_obj = json.load(f)
            raw = root_obj.get('platforms') if isinstance(root_obj, dict) else None
            if isinstance(raw, dict):
                normalized, warns = validate_and_normalize_platforms(raw)
                for w in warns:
                    print(f"[platforms] warn: {w}")
                if normalized:
                    print(f"[platforms] loaded from hosts.json (platforms={len(normalized)})")
                    return normalized
                else:
                    print("[platforms] hosts.json 平台字段为空或无效，回退默认")
        except Exception as e:
            print(f"[platforms] 读取 hosts.json 失败，回退默认：{e}")
    return DEFAULT_PLATFORMS


def now_iso_cn() -> str:
    """返回东八区当前时间的 ISO 字符串（到秒）。"""
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')


def format_hosts_lines(pairs: List[Tuple[str, str]]) -> List[str]:
    """格式化 hosts 行，按固定列宽对齐。"""
    return [f"{ip:<{HOSTS_IP_COLUMN_WIDTH}}{domain}" for ip, domain in pairs]


def write_hosts_files(
    all_pairs: List[Tuple[str, str]],
    per_platform: Dict[str, List[Tuple[str, str]]],
    update_time: str,
    failed_per_platform: Optional[Dict[str, List[str]]] = None,
) -> None:
    """写出根 hosts 与平台专用 hosts 文件。

    - all_pairs: 全部成功解析的 (ip, domain) 列表，用于根 hosts。
    - per_platform: 各平台成功解析的 (ip, domain) 列表。
    - update_time: 更新时间（ISO 字符串）。
    - failed_per_platform: 各平台解析失败的域名，用于注释提示。
    """
    os.makedirs(SCRIPTS_HOSTS_DIR, exist_ok=True)
    header = [START_MARKER]
    footer = [
        f"# Update time: {update_time}",
        f"# Update url: {UPDATE_URL}",
        f"# Star me: {STAR_URL}",
        END_MARKER,
    ]
    def write_one(path: str, pairs: List[Tuple[str, str]], failed_domains: Optional[List[str]] = None) -> None:
        """写出单个 hosts 文件，不写入失败域名。"""
        body = header + format_hosts_lines(pairs)
        body += [''] + footer + ['']
        with open(path, 'w', encoding='utf-8') as f: f.write('\n'.join(body))
    write_one(ROOT_HOSTS_PATH, all_pairs)
    write_one(SCRIPTS_HOSTS_PATH, all_pairs)
    for pk, pairs in per_platform.items():
        file_key = pk.replace('.', '_') if pk != 'battle.net' else 'battle.net'
        path = os.path.join(SCRIPTS_HOSTS_DIR, f"hosts_{file_key}")
        failed = (failed_per_platform or {}).get(pk) or []
        write_one(path, pairs, failed_domains=failed)


def update_readme_hosts_block(update_time: str, results: Dict[str, List[str]], chosen: Dict[str, Tuple[Optional[str], Optional[float], bool]], platforms: Optional[Dict[str, Dict[str, List[str]]]] = None) -> None:
    """更新 README 中的主机块。

    - 将成功解析的域名按列宽写入；
    - 解析失败的域名以注释形式提示（不影响解析）；
    - 收紧主机块前后空白，仅保留单个换行；
    - 同步更新“数据更新时间”文案。
    """
    try:
        with open(README_PATH, 'r', encoding='utf-8') as f: content = f.read()
    except Exception: return
    start_idx, end_idx = content.find(START_MARKER), content.find(END_MARKER)
    if start_idx == -1 or end_idx == -1 or end_idx <= start_idx: return
    domains_order = []
    if platforms:
        for v in platforms.values(): domains_order.extend(v.get('domains', []))
    lines = [START_MARKER]
    for domain in domains_order:
        ips = results.get(domain) or []
        ip = (chosen.get(domain, (None,None,False))[0]) or (ips[0] if ips else '')
        if ip:
            lines.append(f"{ip:<{README_IP_COLUMN_WIDTH}}{domain}")
    lines.append(f"# Update time: {update_time}")
    lines.append(f"# Update url: {UPDATE_URL}")
    lines.append(f"# Star me: {STAR_URL}")
    lines.append(END_MARKER)
    # 只保留主机块前后一个空行，避免页面留白过多
    prefix = content[:start_idx].rstrip("\n \t")
    suffix = content[end_idx+len(END_MARKER):].lstrip("\n \t")
    updated = prefix + "\n" + "\n".join(lines) + "\n" + suffix
    ts_line_pattern = r"^该内容会自动定时更新，数据更新时间：.*$"
    new_ts_line = f"该内容会自动定时更新，数据更新时间：{update_time}"
    if re.search(ts_line_pattern, updated, flags=re.MULTILINE):
        updated = re.sub(ts_line_pattern, new_ts_line, updated, flags=re.MULTILINE)
    with open(README_PATH, 'w', encoding='utf-8') as f: f.write(updated)


# ========== 主函数 ==========

def run_once(domain_health: Optional[Dict[str, int]] = None) -> None:
    """单次运行：解析域名、挑选最佳 IP，写出各类输出文件并更新 README。"""
    platforms = load_platform_domains()
    update_time = now_iso_cn()
    domains = [d for v in platforms.values() for d in v.get('domains', [])]
    start_all = time.perf_counter()
    results: Dict[str, List[str]] = {}
    chosen: Dict[str, Tuple[Optional[str], Optional[float], bool]] = {}
    def worker(domain: str):
        # 基于域名健康状态确定重试次数与快速失败
        fail_cnt = (domain_health or {}).get(domain, 0)
        # 计算当次尝试次数：1 + 动态重试数（随失败次数递减）
        dyn_retry = max(0, HEALTH_RETRY_BASE - (fail_cnt // HEALTH_DECAY_STEP))
        attempts = 1 + dyn_retry
        if fail_cnt >= HEALTH_FAIL_SKIP_THRESHOLD:
            attempts = 1
        ips: List[str] = []
        for _ in range(attempts):
            ips = resolve_domain(domain, DNS_SERVER_LIST, timeout=DNS_QUERY_TIMEOUT, max_parallel=DNS_RACE_WORKERS)
            if ips:
                break
        best_ip, latency, reachable = choose_best_ip(ips) if ips else (None,None,False)
        return domain, ips, best_ip, latency, reachable
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for fut in as_completed({executor.submit(worker,d): d for d in domains}):
            domain, ips, best_ip, latency, reachable = fut.result()
            results[domain], chosen[domain] = ips, (best_ip,latency,reachable)
    total_time = time.perf_counter() - start_all
    all_pairs: List[Tuple[str, str]] = []
    per_platform: Dict[str, List[Tuple[str, str]]] = {pk: [] for pk in platforms}
    failed_per_platform: Dict[str, List[str]] = {pk: [] for pk in platforms}
    for pk, v in platforms.items():
        for domain in v.get('domains', []):
            ips = results.get(domain) or []
            if ips:
                ip = chosen.get(domain,(None,None,False))[0] or ips[0]
                all_pairs.append((ip,domain)); per_platform[pk].append((ip,domain))
            else:
                failed_per_platform[pk].append(domain)
    write_hosts_files(all_pairs, per_platform, update_time, failed_per_platform)
    # 同步写入平台域名配置到 JSON 输出，便于外部工具读取（使用已加载的 platforms）
    json_payload = {"update_time": update_time, "platforms": platforms, "results": results}
    with open(ROOT_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(json_payload, f, ensure_ascii=False, indent=2)
    with open(SCRIPTS_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(json_payload, f, ensure_ascii=False, indent=2)
    # 更新域名健康状态：成功则清零，失败则累加
    if domain_health is not None:
        for pk, v in platforms.items():
            for domain in v.get('domains', []):
                ips = results.get(domain) or []
                reachable = chosen.get(domain, (None, None, False))[2]
                if ips and reachable:
                    domain_health[domain] = 0
                else:
                    domain_health[domain] = (domain_health.get(domain, 0) + 1)
    update_readme_hosts_block(update_time, results, chosen, platforms)
    print(f"Updated hosts at {update_time} (workers={MAX_WORKERS}, dns_timeout={DNS_QUERY_TIMEOUT}s, race={DNS_RACE_WORKERS}, latency_timeout={LATENCY_TIMEOUT}s, elapsed={total_time:.2f}s)")

def main() -> None:
    parser = argparse.ArgumentParser(description="GameLove hosts generator using hosts.json platforms with hot-reload")
    parser.add_argument('--watch', action='store_true', help='启用热更新，监控 hosts.json 的 platforms 字段变化并自动重新生成')
    parser.add_argument('--interval', type=int, default=60, help='热更新轮询间隔秒（默认60）')
    parser.add_argument('--workers', type=int, help='解析并发线程数（默认16）')
    parser.add_argument('--dns-timeout', type=float, help='每DNS服务器查询超时秒（默认1.0）')
    parser.add_argument('--race-workers', type=int, help='每域名并发的DNS服务器数量（默认6）')
    parser.add_argument('--latency-timeout', type=float, help='TCP 延迟检测超时秒（默认0.6）')
    parser.add_argument('--latency-workers', type=int, help='延迟检测线程池大小（默认16）')
    parser.add_argument('--health-fail-threshold', type=int, help='连续失败达到该阈值后快速跳过（默认5）')
    parser.add_argument('--health-retry-base', type=int, help='失败后基础重试次数（默认1）')
    parser.add_argument('--health-decay-step', type=int, help='每累计N次失败重试数递减（默认3）')
    parser.add_argument('--max-ip-probes', type=int, help='每域名参与延迟检测的IP数量上限（默认3）')
    args = parser.parse_args()
    # 应用 CLI 覆盖参数
    global MAX_WORKERS, DNS_QUERY_TIMEOUT, DNS_RACE_WORKERS
    if args.workers and args.workers > 0:
        MAX_WORKERS = args.workers
    if args.dns_timeout and args.dns_timeout > 0:
        DNS_QUERY_TIMEOUT = args.dns_timeout
    if args.race_workers and args.race_workers > 0:
        DNS_RACE_WORKERS = args.race_workers
    global LATENCY_TIMEOUT, MAX_IP_PROBES_PER_DOMAIN, LATENCY_WORKERS
    if args.latency_timeout and args.latency_timeout > 0:
        LATENCY_TIMEOUT = args.latency_timeout
    if args.max_ip_probes and args.max_ip_probes > 0:
        MAX_IP_PROBES_PER_DOMAIN = args.max_ip_probes
    if args.latency_workers and args.latency_workers > 0:
        LATENCY_WORKERS = args.latency_workers
    global HEALTH_FAIL_SKIP_THRESHOLD, HEALTH_RETRY_BASE, HEALTH_DECAY_STEP
    if args.health_fail_threshold and args.health_fail_threshold > 0:
        HEALTH_FAIL_SKIP_THRESHOLD = args.health_fail_threshold
    if args.health_retry_base and args.health_retry_base >= 0:
        HEALTH_RETRY_BASE = args.health_retry_base
    if args.health_decay_step and args.health_decay_step > 0:
        HEALTH_DECAY_STEP = args.health_decay_step
    if not args.watch:
        run_once(DOMAIN_HEALTH)
        _shutdown_latency_executor()
        return
    # 轮询 hosts.json 的 platforms 内容哈希，避免因程序自身写入导致循环触发
    last_hash: Optional[str] = None
    print(f"[watch] 热更新已启动，轮询间隔 {args.interval}s，监控：{ROOT_JSON_PATH} -> platforms")
    while True:
        try:
            platforms_obj: Optional[Dict[str, Dict[str, List[str]]]] = None
            if os.path.exists(ROOT_JSON_PATH):
                with open(ROOT_JSON_PATH, 'r', encoding='utf-8') as f:
                    obj = json.load(f)
                if isinstance(obj, dict) and isinstance(obj.get('platforms'), dict):
                    platforms_obj = obj['platforms']
            # 计算平台字段哈希（未找到则使用默认，以保证首次运行）
            source = platforms_obj if platforms_obj is not None else DEFAULT_PLATFORMS
            dump = json.dumps(source, ensure_ascii=False, sort_keys=True)
            h = hashlib.md5(dump.encode('utf-8')).hexdigest()
            if last_hash is None:
                print("[watch] 首次运行…")
                run_once(DOMAIN_HEALTH)
                last_hash = h
            elif h != last_hash:
                print("[watch] 检测到 hosts.json 平台配置变化，开始重新生成…")
                run_once(DOMAIN_HEALTH)
                last_hash = h
        except Exception as e:
            print(f"[watch] 轮询或生成失败：{e}")
        time.sleep(max(1, args.interval))


if __name__ == "__main__":
    main()
