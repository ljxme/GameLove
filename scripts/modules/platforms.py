#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""游戏平台配置模块

提供平台域名配置与便捷查询方法。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class PlatformInfo:
    """平台信息数据结构

    属性：
    - name: 平台名称
    - domains: 平台相关域名列表
    - success_count: 成功解析计数（运行态）
    - total_count: 总域名数（初始化为 len(domains)）
    - priority_domains: 优先解析域名集合（可选）
    """
    name: str
    domains: List[str]
    success_count: int = 0
    total_count: int = 0
    priority_domains: Set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        """初始化后自动计算总域名数"""
        self.total_count = len(self.domains)


class GamePlatformConfig:
    """游戏平台配置管理

    维护平台与其域名列表，并提供查询方法。
    """

    # 平台域名映射
    PLATFORMS: Dict[str, List[str]] = {
        'Steam': [
            'steamcommunity.com',
            'store.steampowered.com',
            'api.steampowered.com',
            'help.steampowered.com',
            'steamcdn-a.akamaihd.net',
            'steamuserimages-a.akamaihd.net',
            'steamstore-a.akamaihd.net'
        ],
        'Epic': [
            'launcher-public-service-prod06.ol.epicgames.com',
            'epicgames.com',
            'unrealengine.com',
            'fortnite.com',
            'easyanticheat.net'
        ],
        'Origin': [
            'origin.com',
            'ea.com',
            'eaassets-a.akamaihd.net',
            'ssl-lvlt.cdn.ea.com'
        ],
        'Uplay': [
            'ubisoft.com',
            'ubi.com',
            'uplay.com',
            'static3.cdn.ubi.com'
        ],
        'Battle.net': [
            'battle.net',
            'blizzard.com',
            'battlenet.com.cn',
            'blzstatic.cn'
        ],
        'GOG': [
            'gog.com',
            'gog-statics.com',
            'gogalaxy.com'
        ],
        'Rockstar': [
            'rockstargames.com',
            'socialclub.rockstargames.com'
        ]
    }

    @classmethod
    def get_all_domains(cls) -> List[str]:
        """获取所有平台的域名列表"""
        all_domains: List[str] = []
        for domains in cls.PLATFORMS.values():
            all_domains.extend(domains)
        return all_domains

    @classmethod
    def get_platform_info(cls, platform_name: str) -> Optional[PlatformInfo]:
        """根据平台名称获取平台信息"""
        domains = cls.PLATFORMS.get(platform_name)
        if domains:
            return PlatformInfo(name=platform_name, domains=domains)
        return None

    @classmethod
    def get_all_platforms(cls) -> Dict[str, PlatformInfo]:
        """获取所有平台信息映射"""
        return {name: PlatformInfo(name=name, domains=domains) for name, domains in cls.PLATFORMS.items()}