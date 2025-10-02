#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析器模块

提供域名解析的多种实现：DNS、Ping、Nslookup，以及智能选择与并行解析。
所有函数与类均提供中文注释，便于维护与扩展。
"""

import socket
import time
import subprocess
import re
import ipaddress
import concurrent.futures
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import json
import urllib.request
import urllib.parse
import requests


class ResolveMethod(Enum):
    """解析方法枚举类型"""
    DNS = "dns"
    PING = "ping"
    NSLOOKUP = "nslookup"
    DOH = "doh"


@dataclass
class ScoringConfig:
    """评分配置（可调权重与惩罚/加成）

    字段说明：
    - w_tcp: TCP连接耗时权重（越小越好）
    - w_ping: Ping 延迟权重（越小越好）
    - w_resolve: 解析耗时权重（越小越好）
    - penalty_unreachable: 服务不可达的惩罚系数（>1 放大得分）
    - consensus_weight: 共识加成权重（>0 时多来源同IP更优）
    """
    w_tcp: float = 1.0
    w_ping: float = 1.0
    w_resolve: float = 1.0
    penalty_unreachable: float = 3.0
    consensus_weight: float = 1.0


@dataclass
class ResolveResult:
    """解析结果数据结构

    属性说明：
    - domain: 解析的域名
    - ip: 解析出的 IPv4 地址（可能为 None）
    - method: 使用的解析方法
    - success: 是否解析成功
    - error: 失败时的错误信息
    - response_time: 解析耗时（秒）
    - is_valid_ip: IP 是否为有效公网地址
    """
    domain: str
    ip: Optional[str]
    method: Optional[ResolveMethod]
    success: bool
    error: Optional[str] = None
    response_time: Optional[float] = None
    is_valid_ip: bool = False
    meta: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        """后置初始化：校验 IP 有效性"""
        if self.ip:
            self.is_valid_ip = self._validate_ip(self.ip)
        if self.meta is None:
            self.meta = {}

    def _validate_ip(self, ip: str) -> bool:
        """校验 IPv4 地址是否为有效公网地址

        - 排除私有、回环、多播、保留、链路本地地址
        """
        try:
            ip_obj = ipaddress.ip_address(ip)
            return (
                not ip_obj.is_private and
                not ip_obj.is_loopback and
                not ip_obj.is_multicast and
                not ip_obj.is_reserved and
                not ip_obj.is_link_local
            )
        except ValueError:
            return False


class IPResolver(ABC):
    """解析器抽象基类

    子类需实现 resolve(domain) 方法以返回解析结果。
    """

    @abstractmethod
    def resolve(self, domain: str) -> ResolveResult:
        """解析指定域名并返回结果"""
        raise NotImplementedError


class DNSResolver(IPResolver):
    """DNS 解析器：使用系统 DNS 进行解析"""

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def resolve(self, domain: str) -> ResolveResult:
        """通过 socket.gethostbyname 执行 DNS 解析"""
        start_time = time.time()
        try:
            old_timeout = socket.getdefaulttimeout()
            socket.setdefaulttimeout(self.timeout)
            ip = socket.gethostbyname(domain)
            return ResolveResult(domain, ip, ResolveMethod.DNS, True, response_time=time.time() - start_time)
        except Exception as e:
            return ResolveResult(domain, None, ResolveMethod.DNS, False, error=str(e), response_time=time.time() - start_time)
        finally:
            socket.setdefaulttimeout(old_timeout)


class PingResolver(IPResolver):
    """Ping 解析器：通过 ping 输出提取 IP（备用）"""

    def __init__(self, timeout: int = 5, count: int = 1):
        self.timeout = timeout
        self.count = count

    def resolve(self, domain: str) -> ResolveResult:
        """执行 ping 并从输出解析 IPv4 地址"""
        start_time = time.time()
        try:
            result = subprocess.run(
                ['ping', '-n', str(self.count), domain],
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if 'Reply from' in line or 'Pinging' in line:
                        m = re.search(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', line)
                        if m:
                            return ResolveResult(domain, m.group(), ResolveMethod.PING, True, response_time=time.time() - start_time)
            return ResolveResult(domain, None, ResolveMethod.PING, False, error='No IP found in ping output', response_time=time.time() - start_time)
        except Exception as e:
            return ResolveResult(domain, None, ResolveMethod.PING, False, error=str(e), response_time=time.time() - start_time)


class NslookupResolver(IPResolver):
    """Nslookup 解析器：支持指定 DNS 服务器列表"""

    def __init__(self, timeout: int = 10, nameservers: Optional[List[str]] = None):
        self.timeout = timeout
        self.nameservers = nameservers or []

    def _parse(self, stdout: str) -> Optional[str]:
        """从 nslookup 输出中解析 IPv4 地址（排除 IPv6）"""
        for line in stdout.splitlines():
            if 'Address:' in line and '::' not in line:
                m = re.search(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', line)
                if m:
                    return m.group()
        return None

    def resolve(self, domain: str) -> ResolveResult:
        """依次尝试指定 DNS 服务器，失败则回退系统默认"""
        # 尝试指定 DNS
        for server in self.nameservers:
            start_time = time.time()
            try:
                result = subprocess.run(
                    ['nslookup', domain, server],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout
                )
                if result.returncode == 0:
                    ip = self._parse(result.stdout)
                    if ip:
                        return ResolveResult(domain, ip, ResolveMethod.NSLOOKUP, True, response_time=time.time() - start_time)
            except Exception:
                # 单个服务器失败不影响整体，继续下一个
                continue

        # 回退系统默认
        start_time = time.time()
        try:
            result = subprocess.run(
                ['nslookup', domain],
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            ip = self._parse(result.stdout) if result.returncode == 0 else None
            if ip:
                return ResolveResult(domain, ip, ResolveMethod.NSLOOKUP, True, response_time=time.time() - start_time)
            return ResolveResult(domain, None, ResolveMethod.NSLOOKUP, False, error='No IP found in nslookup output', response_time=time.time() - start_time)
        except Exception as e:
            return ResolveResult(domain, None, ResolveMethod.NSLOOKUP, False, error=str(e), response_time=time.time() - start_time)


class ConnectivityTester:
    """连通性测试器：测量 TCP 连接耗时/端口可达与 ping 延迟"""

    def __init__(self, ping_timeout: int = 3, ping_count: int = 1, tcp_timeout: float = 1.5, service_ports: Optional[List[int]] = None, scoring_config: Optional[ScoringConfig] = None):
        self.ping_timeout = ping_timeout
        self.ping_count = ping_count
        self.tcp_timeout = tcp_timeout
        self.service_ports = service_ports or [443, 80]
        self.scoring_config = scoring_config or ScoringConfig()

    def measure_ping_time(self, ip: str) -> Optional[float]:
        """测量指定 IP 的平均 ping 延迟（秒），失败返回 None"""
        try:
            result = subprocess.run(
                ['ping', '-n', str(self.ping_count), '-w', str(self.ping_timeout * 1000), ip],
                capture_output=True,
                text=True,
                timeout=self.ping_timeout + 1
            )
            if result.returncode != 0:
                return None
            times_ms: List[int] = []
            for line in result.stdout.splitlines():
                m = re.search(r'time[=<]\s*(\d+)ms', line)
                if m:
                    times_ms.append(int(m.group(1)))
            if not times_ms:
                m2 = re.search(r'Average =\s*(\d+)ms', result.stdout)
                if m2:
                    times_ms.append(int(m2.group(1)))
            if not times_ms:
                return None
            return sum(times_ms) / len(times_ms) / 1000.0
        except Exception:
            return None

    def measure_tcp_connect_time(self, ip: str) -> Optional[float]:
        """测量到指定 IP 在优先端口上的 TCP 连接耗时（秒），失败返回 None

        优先尝试 443，再尝试 80；任一端口成功则返回对应耗时。
        """
        for port in self.service_ports:
            start = time.time()
            try:
                with socket.create_connection((ip, port), timeout=self.tcp_timeout):
                    return time.time() - start
            except Exception:
                continue
        return None

    def is_service_reachable(self, ip: str) -> bool:
        """判断服务端口是否可达（80/443 任一可达即认为可达）"""
        for port in self.service_ports:
            try:
                with socket.create_connection((ip, port), timeout=self.tcp_timeout):
                    return True
            except Exception:
                continue
        return False

    def choose_best(self, domain: str, candidates: List[ResolveResult]) -> ResolveResult:
        """在多个成功候选中选择综合质量最优

        评分策略：
        - 首选 TCP 连接耗时（越小越好），其次 Ping 延迟，最后解析耗时
        - 服务不可达（80/443 都失败）加权惩罚
        - 共识加成：同一 IP 被多个来源解析到时降低得分
        """
        cfg = self.scoring_config
        # 统计共识（相同 IP 的出现次数）
        freq: Dict[str, int] = {}
        conn_times: Dict[str, Optional[float]] = {}
        reach_map: Dict[str, bool] = {}
        for c in candidates:
            if c.ip:
                freq[c.ip] = freq.get(c.ip, 0) + 1

        best: Optional[Tuple[ResolveResult, float]] = None
        for cand in candidates:
            if not cand.ip:
                continue
            # 基础指标：优先 TCP，其次 Ping，其次解析耗时
            connect_time = self.measure_tcp_connect_time(cand.ip)
            if connect_time is not None:
                base = connect_time * cfg.w_tcp
            else:
                latency = self.measure_ping_time(cand.ip)
                if latency is not None:
                    base = latency * cfg.w_ping
                else:
                    base = (cand.response_time or float('inf')) * cfg.w_resolve

            # 可达性惩罚：不可达放大得分
            reachable = self.is_service_reachable(cand.ip)
            penalty = 1.0 if reachable else cfg.penalty_unreachable
            conn_times[cand.ip] = connect_time
            reach_map[cand.ip] = reachable

            # 共识加成：同一 IP 多来源命中时折减得分
            consensus = freq.get(cand.ip, 1)
            bonus = 1.0 / (1 + max(consensus - 1, 0) * max(cfg.consensus_weight, 0.0001))

            score = base * penalty * bonus

            if best is None or score < best[1]:
                best = (cand, score)

        if best:
            chosen = best[0]
            ip = chosen.ip or ""
            # 注入附加指标用于后续统计
            if ip:
                chosen.meta["consensus"] = freq.get(ip, 1)
                chosen.meta["tcp_connect_time"] = conn_times.get(ip)
                chosen.meta["service_reachable"] = reach_map.get(ip, False)
            return chosen
        return candidates[0]


class SmartResolver(IPResolver):
    """智能解析器：重试、验证、并可选择最快 IP"""

    def __init__(self, resolvers: List[IPResolver], max_retries: int = 2, prefer_fastest: bool = True, scoring_config: Optional[ScoringConfig] = None, stable_cache: Optional[object] = None):
        self.resolvers = resolvers
        self.max_retries = max_retries
        self.prefer_fastest = prefer_fastest
        self.tester = ConnectivityTester(scoring_config=scoring_config)
        self.stable_cache = stable_cache

    def resolve(self, domain: str) -> ResolveResult:
        """依次使用各解析器，收集成功候选并选优"""
        best_result: Optional[ResolveResult] = None
        success_candidates: List[ResolveResult] = []
        for resolver in self.resolvers:
            for attempt in range(self.max_retries + 1):
                result = resolver.resolve(domain)
                if result.success and result.is_valid_ip:
                    success_candidates.append(result)
                if best_result is None or self._is_better(result, best_result):
                    best_result = result
                if result.success:
                    break
                if attempt < self.max_retries:
                    time.sleep(0.5)
        # 若有成功候选，按需扩展更多 IP 并进行优选
        if success_candidates:
            if self.prefer_fastest:
                augmented = self._collect_additional_candidates(domain, success_candidates)
                pool = augmented if augmented else success_candidates
                return self.tester.choose_best(domain, pool)
            return success_candidates[0]
        return best_result or ResolveResult(domain, None, None, False, error='All resolvers failed')

    def _is_better(self, a: ResolveResult, b: ResolveResult) -> bool:
        """比较两个解析结果的优劣"""
        if a.success and a.is_valid_ip:
            if not (b.success and b.is_valid_ip):
                return True
            return (a.response_time or float('inf')) < (b.response_time or float('inf'))
        if a.success and not a.is_valid_ip:
            return not b.success
        if not a.success and not b.success:
            return (a.response_time or float('inf')) < (b.response_time or float('inf'))
        return False

    def _collect_additional_candidates(self, domain: str, base: List[ResolveResult]) -> List[ResolveResult]:
        """收集额外候选 IP：基于 getaddrinfo 获取所有 A 记录，并与已有候选去重"""
        # 已有 IP 集合
        existing: Dict[str, ResolveResult] = {r.ip: r for r in base if r.ip}
        # 尝试通过 socket.getaddrinfo 获取更多 IPv4 地址
        try:
            infos = socket.getaddrinfo(domain, None, family=socket.AF_INET)
            for info in infos:
                ip = info[4][0]
                if ip not in existing:
                    rr = ResolveResult(domain=domain, ip=ip, method=ResolveMethod.DNS, success=True, response_time=None)
                    if rr.is_valid_ip:
                        existing[ip] = rr
        except Exception:
            # 忽略扩展失败
            pass
        # 从稳定缓存中追加候选
        try:
            if self.stable_cache:
                cached_ips: List[str] = self.stable_cache.get_candidates(domain)
                for ip in cached_ips:
                    if ip not in existing:
                        rr = ResolveResult(domain=domain, ip=ip, method=ResolveMethod.DNS, success=True, response_time=None)
                        if rr.is_valid_ip:
                            existing[ip] = rr
        except Exception:
            pass
        return list(existing.values())


class DoHResolver(IPResolver):
    """DNS-over-HTTPS 解析器：调用公开 DoH JSON 接口解析 A 记录

    兼容 Cloudflare 与 Google 接口：
    - Cloudflare: https://cloudflare-dns.com/dns-query?name=example.com&type=A
      需要请求头 Accept: application/dns-json
    - Google:     https://dns.google/resolve?name=example.com&type=A
    返回 JSON 中的 Answer 列表提取 IPv4 地址。
    """

    def __init__(self, endpoint: str, timeout: float = 4.0, headers: Optional[Dict[str, str]] = None, max_retries: int = 1, backoff_factor: float = 0.3, session: Optional[requests.Session] = None):
        self.endpoint = endpoint.rstrip('/')
        self.timeout = timeout
        self.headers = headers or {"Accept": "application/dns-json", "User-Agent": "GameLove-DoH/1.0"}
        # 连接复用：使用 Session，并设置 Keep-Alive
        self.headers.setdefault("Connection", "keep-alive")
        self.session = session or requests.Session()
        # 不在 Session 覆盖 Accept，避免外部自定义 headers 被覆盖；使用每次请求 headers
        self.max_retries = max(0, int(max_retries))
        self.backoff_factor = max(0.0, float(backoff_factor))

    def _build_url(self, domain: str) -> str:
        params = {"name": domain, "type": "A"}
        return f"{self.endpoint}?{urllib.parse.urlencode(params)}"

    def _pick_ip(self, data: Dict[str, Any]) -> Optional[str]:
        try:
            answers = data.get("Answer") or []
            for ans in answers:
                # type 1 为 A 记录
                if ans.get("type") == 1:
                    ip = ans.get("data")
                    if ip and isinstance(ip, str):
                        return ip
        except Exception:
            return None
        return None

    def resolve(self, domain: str) -> ResolveResult:
        start_time = time.time()
        url = self._build_url(domain)
        last_error: Optional[str] = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self.session.get(url, headers=self.headers, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
                ip = self._pick_ip(data)
                if ip:
                    return ResolveResult(domain, ip, ResolveMethod.DOH, True, response_time=time.time() - start_time)
                status = data.get("Status")
                last_error = f"No A record in Answer (status={status})" if status is not None else "No A record found"
            except Exception as e:
                last_error = str(e)
            # 简单指数退避
            if attempt < self.max_retries:
                time.sleep(self.backoff_factor * (2 ** attempt))
        return ResolveResult(domain, None, ResolveMethod.DOH, False, error=last_error, response_time=time.time() - start_time)


class CompositeResolver(IPResolver):
    """组合解析器：按优先级依次尝试多个解析器"""

    def __init__(self, resolvers: List[IPResolver]):
        self.resolvers = resolvers

    def resolve(self, domain: str) -> ResolveResult:
        """返回第一个成功的解析结果，否则返回最后一次失败结果"""
        last_result: Optional[ResolveResult] = None
        for resolver in self.resolvers:
            result = resolver.resolve(domain)
            if result.success:
                return result
            last_result = result
        return last_result or ResolveResult(domain, None, None, False, error='All resolvers failed')


class ParallelResolver:
    """并行解析器：使用线程池并发解析多个域名"""

    def __init__(self, resolver: IPResolver, max_workers: int = 10):
        self.resolver = resolver
        self.max_workers = max_workers

    def resolve_batch(self, domains: List[str]) -> Dict[str, ResolveResult]:
        """并行解析域名列表，返回域名到解析结果的映射"""
        results: Dict[str, ResolveResult] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_domain = {executor.submit(self.resolver.resolve, d): d for d in domains}
            for future in concurrent.futures.as_completed(future_to_domain):
                domain = future_to_domain[future]
                try:
                    results[domain] = future.result()
                except Exception as e:
                    results[domain] = ResolveResult(domain, None, None, False, error=f'Parallel execution error: {e}')
        return results