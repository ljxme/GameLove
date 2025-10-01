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
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum


class ResolveMethod(Enum):
    """解析方法枚举类型"""
    DNS = "dns"
    PING = "ping"
    NSLOOKUP = "nslookup"


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

    def __post_init__(self) -> None:
        """后置初始化：校验 IP 有效性"""
        if self.ip:
            self.is_valid_ip = self._validate_ip(self.ip)

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
    """连通性测试器：测量 ping 延迟并选择最低延迟 IP"""

    def __init__(self, ping_timeout: int = 3, ping_count: int = 1):
        self.ping_timeout = ping_timeout
        self.ping_count = ping_count

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

    def choose_best(self, domain: str, candidates: List[ResolveResult]) -> ResolveResult:
        """在多个成功候选中选择延迟最低的结果"""
        best: Optional[Tuple[ResolveResult, float]] = None
        for cand in candidates:
            if not cand.ip:
                continue
            latency = self.measure_ping_time(cand.ip)
            score = latency if latency is not None else (cand.response_time or float('inf'))
            if best is None or score < best[1]:
                best = (cand, score)
        return best[0] if best else candidates[0]


class SmartResolver(IPResolver):
    """智能解析器：重试、验证、并可选择最快 IP"""

    def __init__(self, resolvers: List[IPResolver], max_retries: int = 2, prefer_fastest: bool = True):
        self.resolvers = resolvers
        self.max_retries = max_retries
        self.prefer_fastest = prefer_fastest
        self.tester = ConnectivityTester()

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
        if success_candidates:
            if self.prefer_fastest and len(success_candidates) > 1:
                return self.tester.choose_best(domain, success_candidates)
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