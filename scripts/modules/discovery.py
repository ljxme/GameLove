#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""域名自动发现模块

基于常见子域名模式与可解析性检测，自动为游戏平台发现潜在新域名。

设计目标：
- 非侵入：不修改静态平台配置，仅在运行态返回候选域名。
- 轻量：不做爬虫，仅基于常见子域生成与解析校验。
- 可扩展：支持自定义子域名集合与解析器注入。
"""

from typing import Dict, List, Set

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


class DomainDiscovery:
    """域名发现器：为各平台生成候选子域并校验解析可用性"""

    def __init__(self, resolver: IPResolver, subdomains: List[str] | None = None) -> None:
        self.resolver = resolver
        self.subdomains = subdomains or DEFAULT_SUBDOMAINS

    def _generate_candidates(self, base_domains: List[str]) -> Set[str]:
        """基于基础域名生成候选子域集合"""
        candidates: Set[str] = set()
        for base in base_domains:
            # 基础域直接纳入（确保去重）
            candidates.add(base)
            # 组合常见子域名
            for sub in self.subdomains:
                candidates.add(f"{sub}.{base}")
        return candidates

    def _is_resolvable(self, domain: str) -> bool:
        """使用注入的解析器校验域名是否可解析且为有效公网 IP"""
        try:
            result: ResolveResult = self.resolver.resolve(domain)
            return bool(result.success and result.ip and result.is_valid_ip)
        except Exception:
            return False

    def discover_for_platform(self, platform: PlatformInfo) -> List[str]:
        """为单个平台发现新域名（剔除已存在项）"""
        base_set: Set[str] = set(platform.domains)
        candidates = self._generate_candidates(platform.domains)

        discovered: List[str] = []
        for domain in sorted(candidates):
            if domain in base_set:
                continue
            if self._is_resolvable(domain):
                discovered.append(domain)
        return discovered

    def discover_all_platforms(self) -> Dict[str, List[str]]:
        """为所有平台执行发现并返回平台到新域名映射"""
        results: Dict[str, List[str]] = {}
        for name, info in GamePlatformConfig.get_all_platforms().items():
            new_domains = self.discover_for_platform(info)
            if new_domains:
                results[name] = new_domains
        return results