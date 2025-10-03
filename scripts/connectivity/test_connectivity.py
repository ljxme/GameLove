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
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Dict, Any


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
HOSTS_PATH = os.path.join(PROJECT_ROOT, "hosts")
OUT_DIR = os.path.join(PROJECT_ROOT, "scripts", "connectivity")
JSON_OUT = os.path.join(OUT_DIR, "connectivity_results.json")
MD_OUT = os.path.join(OUT_DIR, "CONNECTIVITY.md")
SVG_OUT = os.path.join(OUT_DIR, "connectivity_badge.svg")

START_MARKER = '# GameLove Host Start'
END_MARKER = '# GameLove Host End'
HTTP_TIMEOUT = 0.8
TCP_TIMEOUT = 0.6
TLS_TIMEOUT = 0.8


def now_iso_cn() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')


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


def test_tcp_connectivity(ip: str, port: int, timeout: float = TCP_TIMEOUT) -> Dict[str, Any]:
    t0 = time.perf_counter()
    ok = False
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, port))
        ok = True
    except Exception:
        ok = False
    finally:
        try:
            s.close()
        except Exception:
            pass
    latency_ms = (time.perf_counter() - t0) * 1000.0
    return {
        'ip': ip,
        'port': port,
        'ok': ok,
        'latency_ms': round(latency_ms, 2),
    }


def test_tls_handshake(ip: str, domain: str, timeout: float = TLS_TIMEOUT) -> Dict[str, Any]:
    t0 = time.perf_counter()
    ok = False
    try:
        ctx = ssl.create_default_context()
        # 可达性检测不做证书校验，避免域名与证书不匹配导致误判
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        raw = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw.settimeout(timeout)
        raw.connect((ip, 443))
        ssl_sock = ctx.wrap_socket(raw, server_hostname=domain)
        # 成功握手即认为 ok
        ok = True
        try:
            ssl_sock.close()
        except Exception:
            pass
    except Exception:
        ok = False
    latency_ms = (time.perf_counter() - t0) * 1000.0
    return {
        'ip': ip,
        'domain': domain,
        'ok': ok,
        'latency_ms': round(latency_ms, 2),
    }


def test_http_connectivity(ip: str, domain: str, timeout: float = HTTP_TIMEOUT) -> Dict[str, Any]:
    t0 = time.perf_counter()
    status = 'unreachable'
    code = None
    try:
        conn = http.client.HTTPConnection(ip, 80, timeout=timeout)
        conn.request('GET', '/', headers={'Host': domain, 'User-Agent': 'GameLove-Connectivity/1.0'})
        resp = conn.getresponse()
        code = getattr(resp, 'status', None)
        status = 'reachable'
    except Exception:
        status = 'unreachable'
    finally:
        try:
            conn.close()
        except Exception:
            pass
    latency_ms = (time.perf_counter() - t0) * 1000.0
    return {
        'ip': ip,
        'domain': domain,
        'status': status,
        'http_status': code,
        'latency_ms': round(latency_ms, 2),
    }


def make_markdown(update_time: str, results: List[Dict[str, Any]]) -> str:
    total = len(results)
    tls_ok = sum(1 for r in results if r['layers']['tls']['ok'])
    http_ok = sum(1 for r in results if r['layers']['http']['status'] == 'reachable')
    tcp443_ok = sum(1 for r in results if r['layers']['tcp']['443']['ok'])
    tcp80_ok = sum(1 for r in results if r['layers']['tcp']['80']['ok'])
    lines = []
    lines.append(f"数据更新时间: {update_time}")
    lines.append("")
    lines.append(f"分层统计: TLS ✅ {tls_ok}/{total} | TCP443 ✅ {tcp443_ok}/{total} | TCP80 ✅ {tcp80_ok}/{total} | HTTP(80) ✅ {http_ok}/{total}")
    lines.append("")
    lines.append("| 域名 | IP | TCP443 | TCP80 | TLS 握手 | HTTP(80) | 状态码 | 延迟(ms) |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in results:
        tcp443 = r['layers']['tcp']['443']
        tcp80 = r['layers']['tcp']['80']
        tls = r['layers']['tls']
        http = r['layers']['http']
        lines.append(
            f"| {r['domain']} | {r['ip']} | {'✅' if tcp443['ok'] else '❌'} | {'✅' if tcp80['ok'] else '❌'} | {'✅' if tls['ok'] else '❌'} | {'✅' if http['status']=='reachable' else '❌'} | {http['http_status'] if http['http_status'] is not None else '-'} | {http['latency_ms']} |")
    lines.append("")
    lines.append("提示：分层检测：TCP(443/80)→TLS握手→HTTP(80)。此测试为网络侧可达性参考，游戏实际连接可能需其他端口与协议。")
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


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    pairs = parse_hosts_pairs(HOSTS_PATH)
    update_time = now_iso_cn()
    results: List[Dict[str, Any]] = []
    for ip, domain in pairs:
        # TCP 分层
        tcp443 = test_tcp_connectivity(ip, 443)
        tcp80 = test_tcp_connectivity(ip, 80)
        # TLS 握手（基于 443）
        tls = test_tls_handshake(ip, domain)
        # HTTP(80)
        http = test_http_connectivity(ip, domain)
        results.append({
            'ip': ip,
            'domain': domain,
            'layers': {
                'tcp': {
                    '443': tcp443,
                    '80': tcp80,
                },
                'tls': tls,
                'http': http,
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
    print(f"Connectivity report written: {MD_OUT}, {JSON_OUT}, {SVG_OUT}")


if __name__ == '__main__':
    main()