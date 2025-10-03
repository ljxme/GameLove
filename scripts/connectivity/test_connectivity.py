"""
GameLove Hosts 连通性测试脚本（分层：TCP / TLS / HTTP）

功能：
- 读取项目根目录的 `hosts` 文件中主机块；
- 对每个 (IP, 域名) 执行分层检测：
  - TCP 连接：443、80 端口连通性与延迟；
  - TLS 握手：使用 SNI(域名)发起到该 IP 的 TLS 握手；
  - HTTP(80)：Host 头为域名的 HTTP 请求连通性与状态码；
- 输出 JSON 结果、Markdown 报告、SVG 徽章（基于 TLS 成功率）。

判定原则：
- TCP 层：三次握手完成即视为 ok；
- TLS 层：握手完成即视为 ok（不做证书校验，以可达性为主）；
- HTTP 层：收到任意响应即视为 reachable；
"""

import os
import json
import time
import socket
import ssl
import http.client
import ipaddress
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
HOSTS_PATH = os.path.join(PROJECT_ROOT, "hosts")
OUT_DIR = os.path.join(PROJECT_ROOT, "scripts", "connectivity")
JSON_OUT = os.path.join(OUT_DIR, "connectivity_results.json")
MD_OUT = os.path.join(OUT_DIR, "CONNECTIVITY.md")
SVG_OUT = os.path.join(OUT_DIR, "connectivity_badge.svg")
LATENCY_SVG_OUT = os.path.join(OUT_DIR, "latency_chart.svg")

START_MARKER = '# GameLove Host Start'
END_MARKER = '# GameLove Host End'
HTTP_TIMEOUT = 0.8
TCP_TIMEOUT = 0.6
TLS_TIMEOUT = 0.8

# 针对国外站点的网络特性：增加重试与回退（指数退避）
MAX_RETRIES = 2  # 总尝试次数=1+MAX_RETRIES（初次+重试）
BACKOFF_FACTOR = 1.7
MAX_WORKERS = 32  # 并发线程数（IO 密集型，适度偏大）


def classify_platform(domain: str) -> str:
    d = domain.lower()
    if (
        'steam' in d or 'steampowered.com' in d or 'steamstatic.com' in d or 'steamcommunity.com' in d
    ):
        return 'Steam'
    if ('epicgames.com' in d) or ('unrealengine.com' in d):
        return 'Epic Games'
    if ('origin.com' in d) or ('ea.com' in d) or ('eaassets' in d):
        return 'EA / Origin'
    if ('ubisoft.com' in d) or ('ubi.com' in d) or ('uplay.com' in d):
        return 'Ubisoft / Uplay'
    if ('battle.net' in d) or ('blizzard.com' in d) or ('battlenet.com.cn' in d):
        return 'Battle.net / Blizzard'
    if ('gog.com' in d) or ('gogalaxy' in d):
        return 'GOG'
    if ('rockstargames.com' in d) or ('socialclub.rockstargames.com' in d) or ('socialclub' in d):
        return 'Rockstar'
    return 'Other'


def choose_latency_for_display(r: Dict[str, Any]) -> float:
    https = r['layers'].get('https', {})
    http = r['layers'].get('http', {})
    lat = None
    if https and (https.get('latency_ms') is not None):
        lat = https.get('latency_ms')
    elif http and (http.get('latency_ms') is not None):
        lat = http.get('latency_ms')
    else:
        lat = r['layers']['tcp']['443'].get('latency_ms') or 0.0
    return float(lat or 0.0)


def platform_latency_averages(results: List[Dict[str, Any]]) -> Dict[str, float]:
    sums: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    for r in results:
        plat = classify_platform(r['domain'])
        lat = choose_latency_for_display(r)
        if lat is None:
            continue
        sums[plat] = sums.get(plat, 0.0) + float(lat)
        counts[plat] = counts.get(plat, 0) + 1
    return {k: round(sums[k] / counts[k], 2) for k in sums if counts.get(k, 0) > 0}


def now_iso_cn() -> str:
    # 北京时间（UTC+8），格式：YYYY-MM-DD HH:MM:SS
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")


def is_ipv6(ip: str) -> bool:
    try:
        return isinstance(ipaddress.ip_address(ip), ipaddress.IPv6Address)
    except ValueError:
        # 非法 IP，按 IPv4 处理以便抛出连接错误
        return False


def build_timeouts(base: float, retries: int) -> List[float]:
    return [base * (BACKOFF_FACTOR ** i) for i in range(retries + 1)]


def parse_hosts_pairs(path: str) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    if not os.path.exists(path):
        return pairs
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    start = content.find(START_MARKER)
    end = content.find(END_MARKER)
    if start == -1 or end == -1 or end <= start:
        return pairs
    block = content[start:end]
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith('#') or START_MARKER in line:
            continue
        # 以空白分隔提取 IP 与域名
        parts = line.split()
        if len(parts) >= 2:
            ip, domain = parts[0], parts[-1]
            pairs.append((ip, domain))
    return pairs


def test_tcp_connectivity(ip: str, port: int, timeout_base: float = TCP_TIMEOUT, attempts: int = MAX_RETRIES) -> Dict[str, Any]:
    fam = socket.AF_INET6 if is_ipv6(ip) else socket.AF_INET
    errors: List[str] = []
    ok = False
    latency_ms = None
    used_attempts = 0
    s = None
    for i, tmo in enumerate(build_timeouts(timeout_base, attempts)):
        used_attempts = i
        t0 = time.perf_counter()
        try:
            s = socket.socket(fam, socket.SOCK_STREAM)
            s.settimeout(tmo)
            s.connect((ip, port))
            ok = True
        except Exception as e:
            ok = False
            errors.append(e.__class__.__name__)
        finally:
            try:
                if s is not None:
                    s.close()
            except Exception:
                pass
        latency_ms = (time.perf_counter() - t0) * 1000.0
        if ok:
            break
    return {
        'ip': ip,
        'port': port,
        'ok': ok,
        'latency_ms': round(latency_ms if latency_ms is not None else 0.0, 2),
        'retry_count': used_attempts,
        'error': None if ok else (errors[-1] if errors else None),
    }


def test_tls_handshake(ip: str, domain: str, timeout_base: float = TLS_TIMEOUT, attempts: int = MAX_RETRIES) -> Dict[str, Any]:
    fam = socket.AF_INET6 if is_ipv6(ip) else socket.AF_INET
    errors: List[str] = []
    ok = False
    latency_ms = None
    used_attempts = 0
    for i, tmo in enumerate(build_timeouts(timeout_base, attempts)):
        used_attempts = i
        t0 = time.perf_counter()
        try:
            ctx = ssl.create_default_context()
            # 可达性检测不做证书校验，避免域名与证书不匹配导致误判
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            raw = socket.socket(fam, socket.SOCK_STREAM)
            raw.settimeout(tmo)
            raw.connect((ip, 443))
            ssl_sock = ctx.wrap_socket(raw, server_hostname=domain)
            # 成功握手即认为 ok
            ok = True
            try:
                ssl_sock.close()
            except Exception:
                pass
        except Exception as e:
            ok = False
            errors.append(e.__class__.__name__)
        latency_ms = (time.perf_counter() - t0) * 1000.0
        if ok:
            break
    return {
        'ip': ip,
        'domain': domain,
        'ok': ok,
        'latency_ms': round(latency_ms if latency_ms is not None else 0.0, 2),
        'retry_count': used_attempts,
        'error': None if ok else (errors[-1] if errors else None),
    }


def test_http_connectivity(ip: str, domain: str, timeout_base: float = HTTP_TIMEOUT, attempts: int = MAX_RETRIES) -> Dict[str, Any]:
    status = 'unreachable'
    code = None
    method_used = 'HEAD'
    errors: List[str] = []
    latency_ms = None
    used_attempts = 0
    for method in ['HEAD', 'GET']:
        for i, tmo in enumerate(build_timeouts(timeout_base, attempts)):
            used_attempts = i
            t0 = time.perf_counter()
            conn = None
            try:
                conn = http.client.HTTPConnection(ip, 80, timeout=tmo)
                conn.request(method, '/', headers={'Host': domain, 'User-Agent': 'GameLove-Connectivity/1.0'})
                resp = conn.getresponse()
                code = getattr(resp, 'status', None)
                status = 'reachable'
                method_used = method
                ok = True
            except Exception as e:
                ok = False
                status = 'unreachable'
                errors.append(f'{method}:{e.__class__.__name__}')
            finally:
                try:
                    if conn is not None:
                        conn.close()
                except Exception:
                    pass
            latency_ms = (time.perf_counter() - t0) * 1000.0
            if ok:
                break
        if status == 'reachable':
            break
    return {
        'ip': ip,
        'domain': domain,
        'status': status,
        'http_status': code,
        'latency_ms': round(latency_ms if latency_ms is not None else 0.0, 2),
        'method': method_used,
        'retry_count': used_attempts,
        'error': None if status == 'reachable' else (errors[-1] if errors else None),
    }


def test_https_connectivity(ip: str, domain: str, timeout_base: float = TLS_TIMEOUT, attempts: int = MAX_RETRIES) -> Dict[str, Any]:
    fam = socket.AF_INET6 if is_ipv6(ip) else socket.AF_INET
    status = 'unreachable'
    code = None
    method_used = 'HEAD'
    errors: List[str] = []
    latency_ms = None
    used_attempts = 0
    for method in ['HEAD', 'GET']:
        for i, tmo in enumerate(build_timeouts(timeout_base, attempts)):
            used_attempts = i
            t0 = time.perf_counter()
            raw = None
            ssl_sock = None
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                raw = socket.socket(fam, socket.SOCK_STREAM)
                raw.settimeout(tmo)
                raw.connect((ip, 443))
                ssl_sock = ctx.wrap_socket(raw, server_hostname=domain)
                req = f"{method} / HTTP/1.1\r\nHost: {domain}\r\nUser-Agent: GameLove-Connectivity/1.0\r\nConnection: close\r\n\r\n".encode('ascii')
                ssl_sock.sendall(req)
                buf = b''
                while b"\r\n" not in buf:
                    chunk = ssl_sock.recv(1024)
                    if not chunk:
                        break
                    buf += chunk
                first_line = buf.split(b"\r\n", 1)[0].decode('iso-8859-1', errors='ignore')
                parts = first_line.split()
                if len(parts) >= 2 and parts[0].startswith('HTTP/'):
                    try:
                        code = int(parts[1])
                    except Exception:
                        code = None
                status = 'reachable'
                method_used = method
                ok = True
            except Exception as e:
                ok = False
                status = 'unreachable'
                errors.append(f'{method}:{e.__class__.__name__}')
            finally:
                try:
                    if ssl_sock is not None:
                        ssl_sock.close()
                except Exception:
                    pass
                try:
                    if raw is not None:
                        raw.close()
                except Exception:
                    pass
            latency_ms = (time.perf_counter() - t0) * 1000.0
            if ok:
                break
        if status == 'reachable':
            break
    return {
        'ip': ip,
        'domain': domain,
        'status': status,
        'http_status': code,
        'latency_ms': round(latency_ms if latency_ms is not None else 0.0, 2),
        'method': method_used,
        'retry_count': used_attempts,
        'error': None if status == 'reachable' else (errors[-1] if errors else None),
    }


def make_markdown(update_time: str, results: List[Dict[str, Any]]) -> str:
    total = len(results)
    tls_ok = sum(1 for r in results if r['layers']['tls']['ok'])
    http_ok = sum(1 for r in results if r['layers']['http']['status'] == 'reachable')
    tcp443_ok = sum(1 for r in results if r['layers']['tcp']['443']['ok'])
    tcp80_ok = sum(1 for r in results if r['layers']['tcp']['80']['ok'])
    https_ok = sum(1 for r in results if r['layers'].get('https', {'status': 'unreachable'})['status'] == 'reachable')
    lines = []
    lines.append(f"数据更新时间: {update_time}")
    lines.append("")
    lines.append(f"分层统计: TLS ✅ {tls_ok}/{total} | TCP(443) ✅ {tcp443_ok}/{total} | TCP(80) ✅ {tcp80_ok}/{total} | HTTP(80) ✅ {http_ok}/{total} | HTTPS(443) ✅ {https_ok}/{total}")
    lines.append("")
    lines.append("### 可视化")
    lines.append("")
    # 移除饼图展示，避免视觉占用；保留分层统计文本在顶部
    lines.append("#### 延迟柱状图（Top 15）")
    lines.append("")
    # 在同目录下引用生成的延迟图 SVG
    lines.append("![Latency Chart](latency_chart.svg)")
    lines.append("")
    lines.append("| 域名 | IP | TCP443 | TCP80 | TLS 握手 | HTTP(80) | 状态码 | HTTPS(443) | 状态码(HTTPS) | 延迟(ms) |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        tcp443 = r['layers']['tcp']['443']
        tcp80 = r['layers']['tcp']['80']
        tls = r['layers']['tls']
        http = r['layers']['http']
        https = r['layers'].get('https', {'status': 'unreachable', 'http_status': None})
        # 域名列改为可点击链接：优先 HTTPS → 回退 HTTP
        proto = 'https' if https.get('status') == 'reachable' else ('http' if http.get('status') == 'reachable' else 'https')
        domain_link = f"[{r['domain']}]({proto}://{r['domain']}/)"
        lines.append(
            f"| {domain_link} | {r['ip']} | {'✅' if tcp443['ok'] else '❌'} | {'✅' if tcp80['ok'] else '❌'} | {'✅' if tls['ok'] else '❌'} | {'✅' if http['status']=='reachable' else '❌'} | {http['http_status'] if http['http_status'] is not None else '-'} | {'✅' if https['status']=='reachable' else '❌'} | {https['http_status'] if https['http_status'] is not None else '-'} | {https['latency_ms'] if https.get('latency_ms') is not None else http['latency_ms']} |")
    lines.append("")
    lines.append("提示：分层检测：TCP(443/80)→TLS握手→HTTP(80/HTTPS(443))。此测试为网络侧可达性参考，游戏实际连接可能需其他端口与协议。")
    return "\n".join(lines)


def make_badge_svg(ok: int, total: int) -> str:
    # 简易徽章：绿色（全通过）、黄色（部分失败）、红色（全部失败）
    if ok == total:
        color = '#4c1'  # green
    elif ok == 0:
        color = '#e05d44'  # red
    else:
        color = '#dfb317'  # yellow
    label = 'TLS Connectivity'
    value = f'{ok}/{total}'
    # 基于最小宽度的静态 SVG
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="190" height="20">
  <linearGradient id="b" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <mask id="a">
    <rect width="190" height="20" rx="3" fill="#fff"/>
  </mask>
  <g mask="url(#a)">
    <rect width="120" height="20" fill="#555"/>
    <rect x="120" width="70" height="20" fill="{color}"/>
    <rect width="190" height="20" fill="url(#b)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="60" y="14">{label}</text>
    <text x="155" y="14">{value}</text>
  </g>
</svg>'''


def make_latency_bar_svg(results: List[Dict[str, Any]], top_n: int = 15) -> str:
    # 选择用于展示的延迟：优先 HTTPS，其次 HTTP，最后 TCP443
    items = []
    for r in results:
        lat = choose_latency_for_display(r)
        items.append({'domain': r['domain'], 'latency_ms': lat})
    # 取 Top N 按延迟升序（越低越好）
    items.sort(key=lambda x: x['latency_ms'])
    items = items[:top_n]
    if not items:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="40"><text x="10" y="25" font-size="14">No data</text></svg>'
    max_lat = max(i['latency_ms'] for i in items) or 1.0
    # 画布参数
    width = 800
    left_pad = 180
    right_pad = 40
    top_pad = 30
    bar_h = 22
    gap = 10
    height = top_pad + len(items) * (bar_h + gap) + 30
    scale = (width - left_pad - right_pad) / max_lat
    # 构建 SVG 内容
    svg_lines = []
    svg_lines.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">')
    svg_lines.append('<style> .label{font-family:DejaVu Sans,Verdana,Geneva,sans-serif;font-size:12px;fill:#333} .value{font-family:DejaVu Sans,Verdana,Geneva,sans-serif;font-size:12px;fill:#555} </style>')
    svg_lines.append(f'<text x="10" y="20" class="label">延迟柱状图（越低越好，Top {len(items)}），单位 ms</text>')
    # bars
    y = top_pad
    for i, it in enumerate(items):
        bar_w = round(it['latency_ms'] * scale, 2)
        color = '#4c78a8'
        svg_lines.append(f'<text x="10" y="{y + 16}" class="label">{it["domain"]}</text>')
        svg_lines.append(f'<rect x="{left_pad}" y="{y}" width="{bar_w}" height="{bar_h}" fill="{color}" rx="3"/>')
        svg_lines.append(f'<text x="{left_pad + bar_w + 8}" y="{y + 16}" class="value">{it["latency_ms"]:.2f}</text>')
        y += bar_h + gap
    # axis line
    svg_lines.append(f'<line x1="{left_pad}" y1="{top_pad}" x2="{left_pad}" y2="{height-20}" stroke="#ccc"/>')
    svg_lines.append(f'<line x1="{left_pad}" y1="{height-20}" x2="{width-right_pad}" y2="{height-20}" stroke="#ccc"/>')
    svg_lines.append('</svg>')
    return "\n".join(svg_lines)


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    pairs = parse_hosts_pairs(HOSTS_PATH)
    update_time = now_iso_cn()
    results: List[Dict[str, Any]] = []

    def test_one(ip: str, domain: str) -> Dict[str, Any]:
        tcp443 = test_tcp_connectivity(ip, 443)
        tcp80 = test_tcp_connectivity(ip, 80)
        tls = test_tls_handshake(ip, domain)
        http = test_http_connectivity(ip, domain)
        https = test_https_connectivity(ip, domain)
        return {
            'ip': ip,
            'domain': domain,
            'layers': {
                'tcp': {
                    '443': tcp443,
                    '80': tcp80,
                },
                'tls': tls,
                'http': http,
                'https': https,
            }
        }

    workers = min(MAX_WORKERS, max(4, (os.cpu_count() or 4) * 4))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_pair = {executor.submit(test_one, ip, domain): (ip, domain) for ip, domain in pairs}
        for fut in as_completed(future_to_pair):
            try:
                results.append(fut.result())
            except Exception as e:
                ip, domain = future_to_pair[fut]
                results.append({
                    'ip': ip,
                    'domain': domain,
                    'layers': {
                        'tcp': {
                            '443': {'ip': ip, 'port': 443, 'ok': False, 'latency_ms': 0.0, 'retry_count': 0, 'error': 'ExecutorError'},
                            '80': {'ip': ip, 'port': 80, 'ok': False, 'latency_ms': 0.0, 'retry_count': 0, 'error': 'ExecutorError'},
                        },
                        'tls': {'ip': ip, 'domain': domain, 'ok': False, 'latency_ms': 0.0, 'retry_count': 0, 'error': 'ExecutorError'},
                        'http': {'ip': ip, 'domain': domain, 'status': 'unreachable', 'http_status': None, 'latency_ms': 0.0, 'method': 'HEAD', 'retry_count': 0, 'error': 'ExecutorError'},
                        'https': {'ip': ip, 'domain': domain, 'status': 'unreachable', 'http_status': None, 'latency_ms': 0.0, 'method': 'HEAD', 'retry_count': 0, 'error': 'ExecutorError'},
                    }
                })
    payload = {
        'update_time': update_time,
        'summary': {
            'total': len(results),
            'tls_ok': sum(1 for r in results if r['layers']['tls']['ok']),
            'tcp443_ok': sum(1 for r in results if r['layers']['tcp']['443']['ok']),
            'tcp80_ok': sum(1 for r in results if r['layers']['tcp']['80']['ok']),
            'http_ok': sum(1 for r in results if r['layers']['http']['status'] == 'reachable'),
            'https_ok': sum(1 for r in results if r['layers'].get('https', {'status': 'unreachable'})['status'] == 'reachable'),
        },
        'results': results,
    }
    with open(JSON_OUT, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    md = make_markdown(update_time, results)
    with open(MD_OUT, 'w', encoding='utf-8') as f:
        f.write(md)
    badge = make_badge_svg(payload['summary']['tls_ok'], payload['summary']['total'])
    with open(SVG_OUT, 'w', encoding='utf-8') as f:
        f.write(badge)
    # 生成延迟柱状图
    latency_svg = make_latency_bar_svg(results)
    with open(LATENCY_SVG_OUT, 'w', encoding='utf-8') as f:
        f.write(latency_svg)
    print(f"Connectivity report written: {MD_OUT}, {JSON_OUT}, {SVG_OUT}, {LATENCY_SVG_OUT}")


if __name__ == '__main__':
    main()