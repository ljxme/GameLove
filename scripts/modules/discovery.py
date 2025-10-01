#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""域名自动发现模块

基于常见子域名模式与可解析性检测，自动为游戏平台发现潜在新域名。

设计目标：
- 非侵入：不修改静态平台配置，仅在运行态返回候选域名。
- 轻量：以模式生成为主，可选轻量 HTTP 探测（robots/sitemap）。
- 可扩展：策略化设计，支持速率限制与统一错误处理。
"""

from typing import Dict, List, Set, Protocol, Optional
import time
import re
import urllib.request
import urllib.parse

from .platforms import GamePlatformConfig, PlatformInfo
from .resolvers import IPResolver, ResolveResult


DEFAULT_SUBDOMAINS: List[str] = [
    # 通用服务
    "www", "api", "cdn", "store", "help", "support", "status", "static", "assets", "images", "media",
    # 下载与客户端
    "download", "client", "launcher", "update",
    # 其他常见别名
    "edge", "content", "secure", "fastly", "s1", "s2",
]


class DiscoveryError(Exception):
    """域名发现过程中产生的统一错误类型"""


class RateLimiter:
    """简单速率限制器（固定间隔）"""

    def __init__(self, rate_per_sec: float = 5.0) -> None:
        # 每次请求之间的最小间隔
        self.interval = 1.0 / rate_per_sec if rate_per_sec > 0 else 0.0
        self._next_time = time.monotonic()

    def acquire(self, tokens: int = 1) -> None:
        if self.interval <= 0:
            return
        # 简单线性等待，按令牌数扩大间隔
        wait_until = self._next_time + self.interval * max(tokens, 1)
        now = time.monotonic()
        if wait_until > now:
            time.sleep(wait_until - now)
        self._next_time = time.monotonic()


class DiscoveryStrategy(Protocol):
    """发现策略接口"""

    def discover(self, base_domain: str, resolver: IPResolver, timeout: float,
                 limiter: Optional[RateLimiter]) -> List[str]:
        ...


class PatternStrategy:
    """基于常见子域名模式的发现策略"""

    def __init__(self, subdomains: List[str]) -> None:
        self.subdomains = subdomains

    def discover(self, base_domain: str, resolver: IPResolver, timeout: float,
                 limiter: Optional[RateLimiter]) -> List[str]:
        discovered: List[str] = []
        base_set = {base_domain}
        for sub in self.subdomains:
            candidate = f"{sub}.{base_domain}"
            if candidate in base_set:
                continue
            try:
                if limiter:
                    limiter.acquire(1)
                result: ResolveResult = resolver.resolve(candidate)
                if result.success and result.ip and result.is_valid_ip:
                    discovered.append(candidate)
            except Exception:
                # 忽略单次错误
                pass
        return discovered


class DnsRecordStrategy:
    """直接基于解析尝试的策略（与 PatternStrategy 类似，保留扩展位）"""

    COMMON_PREFIX = ["api", "cdn", "static", "assets", "images", "media", "download"]

    def discover(self, base_domain: str, resolver: IPResolver, timeout: float,
                 limiter: Optional[RateLimiter]) -> List[str]:
        discovered: List[str] = []
        for sub in self.COMMON_PREFIX:
            candidate = f"{sub}.{base_domain}"
            try:
                if limiter:
                    limiter.acquire(1)
                result: ResolveResult = resolver.resolve(candidate)
                if result.success and result.ip and result.is_valid_ip:
                    discovered.append(candidate)
            except Exception:
                pass
        return list(dict.fromkeys(discovered))


class RobotsSitemapStrategy:
    """轻量从 robots.txt 与 sitemap.xml 解析同域链接，提取子域并校验"""

    def _fetch(self, url: str, timeout: float, limiter: Optional[RateLimiter]) -> str:
        try:
            if limiter:
                limiter.acquire(1)
            req = urllib.request.Request(url, headers={"User-Agent": "GameLove/Discovery"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status >= 400:
                    return ""
                data = resp.read()
                return data.decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def discover(self, base_domain: str, resolver: IPResolver, timeout: float,
                 limiter: Optional[RateLimiter]) -> List[str]:
        discovered: Set[str] = set()
        scheme = "https"
        robots_url = f"{scheme}://{base_domain}/robots.txt"
        sitemap_url = f"{scheme}://{base_domain}/sitemap.xml"

        robots_txt = self._fetch(robots_url, timeout, limiter)
        sitemap_xml = self._fetch(sitemap_url, timeout, limiter)

        # 在文本中寻找同域链接，抽取子域
        def extract_hosts(text: str) -> List[str]:
            hosts: List[str] = []
            if not text:
                return hosts
            # 匹配 http(s) 链接
            for m in re.finditer(r"https?://([A-Za-z0-9.-]+)(/|\\b)", text):
                host = m.group(1)
                hosts.append(host)
            return hosts

        for host in extract_hosts(robots_txt) + extract_hosts(sitemap_xml):
            # 仅考虑同一主域的子域
            if host == base_domain or host.endswith("." + base_domain):
                try:
                    if limiter:
                        limiter.acquire(1)
                    result: ResolveResult = resolver.resolve(host)
                    if result.success and result.ip and result.is_valid_ip:
                        discovered.add(host)
                except Exception:
                    pass

        return sorted(discovered)


class DomainDiscovery:
    """域名发现器：聚合多策略并支持速率限制与错误处理"""

    def __init__(self, resolver: IPResolver, subdomains: Optional[List[str]] = None,
                 strategies: Optional[List[str]] = None, rate_limit: Optional[float] = None,
                 timeout: float = 2.0) -> None:
        self.resolver = resolver
        self.subdomains = subdomains or DEFAULT_SUBDOMAINS
        self.timeout = timeout
        self.limiter = RateLimiter(rate_limit) if rate_limit else None

        # 策略注册表
        self._strategies: Dict[str, DiscoveryStrategy] = {}
        # 默认至少包含模式策略
        self.register_strategy("pattern", PatternStrategy(self.subdomains))
        # 可选扩展策略
        if strategies:
            for s in strategies:
                key = s.strip().lower()
                if key == "dns":
                    self.register_strategy("dns", DnsRecordStrategy())
                elif key == "robots":
                    self.register_strategy("robots", RobotsSitemapStrategy())

    def register_strategy(self, name: str, strategy: DiscoveryStrategy) -> None:
        self._strategies[name] = strategy

    def set_rate_limiter(self, limiter: RateLimiter) -> None:
        self.limiter = limiter

    def _run_strategies(self, base_domain: str) -> List[str]:
        discovered: List[str] = []
        for name, strategy in self._strategies.items():
            try:
                candidates = strategy.discover(base_domain, self.resolver, self.timeout, self.limiter)
                discovered.extend(candidates)
            except Exception:
                # 策略失败不终止整体流程
                continue
        # 去重
        return list(dict.fromkeys(discovered))

    def discover_for_platform(self, platform: PlatformInfo) -> List[str]:
        """为单个平台发现新域名（剔除已存在项）"""
        base_set: Set[str] = set(platform.domains)
        discovered: List[str] = []
        for base in platform.domains:
            for d in self._run_strategies(base):
                if d not in base_set:
                    discovered.append(d)
        return list(dict.fromkeys(discovered))

    def discover_all_platforms(self) -> Dict[str, List[str]]:
        """为所有平台执行发现并返回平台到新域名映射"""
        results: Dict[str, List[str]] = {}
        for name, info in GamePlatformConfig.get_all_platforms().items():
            new_domains = self.discover_for_platform(info)
            if new_domains:
                results[name] = new_domains
        return results