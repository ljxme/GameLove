#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GameLove Hosts 更新工具 - 模块化重构版本

该工具用于自动更新游戏平台的hosts文件，优化网络连接。
采用模块化设计，提升代码的可维护性、可扩展性和易读性。

"""

import argparse
import time
import os
from typing import Dict, List, Tuple, Any

# 指定 DNS 解析服务器列表（按优先级）
DNS_SERVER_LIST = [
    "1.1.1.1",            # Cloudflare DNS
    "8.8.8.8",            # Google Public DNS
    "101.101.101.101",    # Quad101 DNS (台湾)
    "101.102.103.104",    # Quad101 DNS (台湾备用)
]

# 模块化导入（解析器、平台配置、内容与文件管理）
from modules.resolvers import (
    DNSResolver as R_DNSResolver,
    PingResolver as R_PingResolver,
    NslookupResolver as R_NslookupResolver,
    SmartResolver as R_SmartResolver,
    CompositeResolver as R_CompositeResolver,
    ParallelResolver as R_ParallelResolver,
    ResolveResult as R_ResolveResult,
)
from modules.platforms import GamePlatformConfig as P_GamePlatformConfig
from modules.content import ContentGenerator as C_ContentGenerator, create_statistics_report_content
from modules.files import FileManager as F_FileManager
from modules.discovery import DomainDiscovery

class GameLoveHostsUpdater:
    """GameLove Hosts更新器主控制类 - 重构版本"""
    
    def __init__(self, 
                 delay_between_requests: float = 0.1,
                 use_parallel: bool = True,
                 max_workers: int = 10,
                 use_smart_resolver: bool = True,
                 prefer_fastest: bool = True,
                 discovery_strategies: List[str] | None = None,
                 rate_limit: float | None = None,
                 discovery_timeout: float = 2.0):
        """初始化更新器
        
        Args:
            delay_between_requests: 请求间延迟时间（秒）
            use_parallel: 是否使用并行解析
            max_workers: 最大工作线程数
            use_smart_resolver: 是否使用智能解析器
        """
        self.delay_between_requests = delay_between_requests
        self.use_parallel = use_parallel
        self.max_workers = max_workers
        self.prefer_fastest = prefer_fastest
        self.discovery_strategies = discovery_strategies or ["pattern"]
        self.rate_limit = rate_limit
        self.discovery_timeout = discovery_timeout
        
        # 初始化解析器
        self._init_resolvers(use_smart_resolver)
        
        # 初始化其他组件（使用模块化实现）
        self.content_generator = C_ContentGenerator()
        self.file_manager = F_FileManager()
        self.discovery: DomainDiscovery | None = None
        self.platform_discovered: Dict[str, List[str]] = {}
        
        # 统计信息
        self.stats = {
            'total_domains': 0,
            'success_count': 0,
            'failed_count': 0,
            'start_time': None,
            'end_time': None,
            'total_time': 0
        }
    
    def _init_resolvers(self, use_smart_resolver: bool) -> None:
        """初始化解析器
        
        Args:
            use_smart_resolver: 是否使用智能解析器
        """
        # 创建基础解析器（Nslookup 使用指定 DNS 服务器列表）
        base_resolvers = [
            R_DNSResolver(timeout=10.0),
            R_PingResolver(timeout=5, count=1),
            R_NslookupResolver(timeout=10, nameservers=DNS_SERVER_LIST)
        ]
        
        if use_smart_resolver:
            # 使用智能解析器（可选最快 IP）
            self.resolver = R_SmartResolver(base_resolvers, max_retries=2, prefer_fastest=self.prefer_fastest)
        else:
            # 使用组合解析器
            self.resolver = R_CompositeResolver(base_resolvers)
        
        # 如果启用并行处理，包装为并行解析器
        if self.use_parallel:
            self.parallel_resolver = R_ParallelResolver(self.resolver, self.max_workers)
        # 初始化发现器（在解析器就绪后）
        self.discovery = DomainDiscovery(
            self.resolver,
            strategies=self.discovery_strategies,
            rate_limit=self.rate_limit,
            timeout=self.discovery_timeout,
        )
    
    def resolve_all_domains(self) -> Tuple[Dict[str, str], List[str], Dict[str, R_ResolveResult]]:
        """解析所有游戏平台域名
        
        Returns:
            Tuple[Dict[str, str], List[str], Dict[str, R_ResolveResult]]: 
            (成功解析的IP字典, 失败域名列表, 详细解析结果)
        """
        # 静态域名
        all_domains = P_GamePlatformConfig.get_all_domains()
        # 运行态发现新域名并合并
        self.platform_discovered = self.discovery.discover_all_platforms() if self.discovery else {}
        discovered_list: List[str] = [d for domains in self.platform_discovered.values() for d in domains]
        augmented_domains = list(dict.fromkeys(all_domains + discovered_list))  # 去重保持顺序
        self.stats['total_domains'] = len(all_domains)
        self.stats['start_time'] = time.time()
        
        print(f"🔍 开始解析 {len(all_domains)} 个游戏平台域名...")
        print(f"📊 解析模式: {'并行' if self.use_parallel else '串行'}")
        print(f"🧠 解析器类型: {'智能解析器' if isinstance(self.resolver, R_SmartResolver) else '组合解析器'}")
        print()
        
        if self.use_parallel:
            # 并行解析
            detailed_results = self.parallel_resolver.resolve_batch(augmented_domains)
        else:
            # 串行解析
            detailed_results = {}
            for domain in augmented_domains:
                result = self.resolver.resolve(domain)
                detailed_results[domain] = result
                
                # 显示进度
                self._print_resolve_progress(domain, result)
                
                # 添加延迟避免请求过快
                time.sleep(self.delay_between_requests)
        
        # 处理结果
        ip_dict = {}
        failed_domains = []
        
        for domain, result in detailed_results.items():
            if result.success and result.ip and result.is_valid_ip:
                ip_dict[domain] = result.ip
                self.stats['success_count'] += 1
            else:
                failed_domains.append(domain)
                self.stats['failed_count'] += 1
            
            # 如果是并行模式，在这里显示结果
            if self.use_parallel:
                self._print_resolve_progress(domain, result)
        
        self.stats['end_time'] = time.time()
        self.stats['total_time'] = self.stats['end_time'] - self.stats['start_time']
        
        return ip_dict, failed_domains, detailed_results
    
    def _print_resolve_progress(self, domain: str, result: R_ResolveResult) -> None:
        """打印解析进度
        
        Args:
            domain: 域名
            result: 解析结果
        """
        if result.success and result.ip and result.is_valid_ip:
            method_str = f"({result.method.value})" if result.method else ""
            time_str = f" [{result.response_time:.2f}s]" if result.response_time else ""
            print(f"✅ {domain:<40} -> {result.ip:<15} {method_str}{time_str}")
        elif result.success and result.ip and not result.is_valid_ip:
            method_str = f"({result.method.value})" if result.method else ""
            time_str = f" [{result.response_time:.2f}s]" if result.response_time else ""
            print(f"⚠️  {domain:<40} -> {result.ip:<15} {method_str}{time_str} [无效IP]")
        else:
            error_str = f" ({result.error[:50]}...)" if result.error and len(result.error) > 50 else f" ({result.error})" if result.error else ""
            time_str = f" [{result.response_time:.2f}s]" if result.response_time else ""
            print(f"❌ {domain:<40} -> 解析失败{error_str}{time_str}")
    
    def generate_and_save_files(self, 
                               ip_dict: Dict[str, str], 
                               failed_domains: List[str],
                               detailed_results: Dict[str, R_ResolveResult]) -> None:
        """生成并保存所有文件
        
        Args:
            ip_dict: 成功解析的IP字典
            failed_domains: 失败域名列表
            detailed_results: 详细解析结果
        """
        if not ip_dict:
            print("❌ 没有成功解析的域名，跳过文件生成")
            return
        
        print(f"\n📝 开始生成文件...")
        
        # 生成完整hosts文件
        hosts_content = self.content_generator.generate_hosts_content(ip_dict)
        
        # 保存主要文件到根目录
        main_file = self.file_manager.save_hosts_file(hosts_content, 'hosts', is_root=True)
        print(f"✅ 主文件已保存到: {main_file}")
        
        # 保存备份到hosts目录
        backup_file = self.file_manager.save_hosts_file(hosts_content, 'hosts')
        print(f"✅ 备份已保存到: {backup_file}")
        
        # 生成并保存JSON文件（包含详细统计信息）
        json_data = self._generate_enhanced_json_data(ip_dict, failed_domains, detailed_results)
        
        json_file = self.file_manager.save_json_file(json_data, 'hosts.json', is_root=True)
        print(f"✅ JSON文件已保存到: {json_file}")
        
        json_backup = self.file_manager.save_json_file(json_data, 'hosts.json')
        print(f"✅ JSON备份已保存到: {json_backup}")
        
        # 生成分平台hosts文件
        self._generate_platform_files(ip_dict)
        
        # 生成统计报告
        self._generate_statistics_report(detailed_results)
        
        # 更新README.md
        print(f"\n📝 更新README.md中的hosts内容...")
        if self.file_manager.update_readme_hosts_content(hosts_content):
            print("✅ README.md已成功更新")
        else:
            print("❌ README.md更新失败")

        # 更新 README 平台域名数量（静态 + 发现）
        platform_counts: Dict[str, int] = {}
        for name, info in P_GamePlatformConfig.get_all_platforms().items():
            discovered = self.platform_discovered.get(name, [])
            platform_counts[name] = len(info.domains) + len(discovered)
        print(f"\n📝 更新README.md中的平台域名数量...")
        if self.file_manager.update_readme_platform_counts(platform_counts):
            print("✅ README.md平台域名数量已更新")
        else:
            print("❌ README.md平台域名数量更新失败")
    
    def _generate_enhanced_json_data(self, 
                                   ip_dict: Dict[str, str], 
                                   failed_domains: List[str],
                                   detailed_results: Dict[str, R_ResolveResult]) -> Dict[str, Any]:
        """生成增强的JSON数据，包含详细统计信息
        
        Args:
            ip_dict: 成功解析的域名到IP映射
            failed_domains: 解析失败的域名列表
            detailed_results: 详细解析结果
            
        Returns:
            Dict[str, Any]: 增强的JSON数据
        """
        # 统一由 content 模块生成增强 JSON
        resolver_config = {
            'parallel_mode': self.use_parallel,
            'max_workers': self.max_workers if self.use_parallel else 1,
            'smart_resolver': isinstance(self.resolver, R_SmartResolver)
        }
        return self.content_generator.generate_enhanced_json_data(
            ip_dict,
            failed_domains,
            detailed_results,
            self.stats,
            resolver_config,
            self.platform_discovered,
        )
    
    def _generate_platform_files(self, ip_dict: Dict[str, str]) -> None:
        """生成分平台hosts文件
        
        Args:
            ip_dict: 成功解析的IP字典
        """
        print(f"\n📁 生成分平台hosts文件...")
        
        for platform_name, platform_info in P_GamePlatformConfig.get_all_platforms().items():
            platform_ips = {
                domain: ip_dict[domain] 
                for domain in platform_info.domains 
                if domain in ip_dict
            }
            
            if platform_ips:
                platform_content = self.content_generator.generate_hosts_content(platform_ips)
                platform_file = self.file_manager.save_hosts_file(
                    platform_content, 
                    f'hosts_{platform_name.lower()}'
                )
                success_rate = len(platform_ips) / len(platform_info.domains) * 100
                print(f"✅ {platform_name:<12} -> {platform_file:<30} ({len(platform_ips)}/{len(platform_info.domains)}, {success_rate:.1f}%)")
            else:
                print(f"❌ {platform_name:<12} -> 无可用域名")
    
    def _generate_statistics_report(self, detailed_results: Dict[str, R_ResolveResult]) -> None:
        """生成统计报告文件
        
        Args:
            detailed_results: 详细解析结果
        """
        report_content = create_statistics_report_content(detailed_results, self.stats)
        
        report_file = self.file_manager.save_hosts_file(
            report_content, 
            'statistics_report.txt'
        )
        print(f"📊 统计报告已保存到: {report_file}")
    
    def print_summary(self) -> None:
        """打印执行摘要"""
        print(f"\n{'='*60}")
        print(f"🎉 GameLove Hosts 更新完成！")
        print(f"{'='*60}")
        print(f"📊 解析统计:")
        print(f"   总域名数: {self.stats['total_domains']}")
        print(f"   成功解析: {self.stats['success_count']} ({self.stats['success_count']/self.stats['total_domains']*100:.1f}%)")
        print(f"   解析失败: {self.stats['failed_count']} ({self.stats['failed_count']/self.stats['total_domains']*100:.1f}%)")
        print(f"   总耗时: {self.stats['total_time']:.2f}秒")
        print(f"   平均速度: {self.stats['total_domains']/self.stats['total_time']:.2f} 域名/秒")
        print(f"\n📁 文件位置:")
        print(f"   主文件: 根目录 (hosts, hosts.json)")
        print(f"   备份: {self.file_manager.hosts_dir}/ 目录")
        print(f"   统计报告: {self.file_manager.hosts_dir}/statistics_report.txt")
        print(f"\n📖 使用说明请查看 README.md")
        print(f"⭐ 如果觉得有用，请给项目点个星: https://github.com/artemisia1107/GameLove")
    
    def run(self) -> None:
        """运行主程序"""
        print("🎮 GameLove - 游戏平台网络优化工具 (重构版 v2.0)")
        print("参考 GitHub520 设计，让你\"爱\"上游戏！")
        print("=" * 60)
        
        try:
            # 解析所有域名
            ip_dict, failed_domains, detailed_results = self.resolve_all_domains()
            
            # 生成并保存文件
            self.generate_and_save_files(ip_dict, failed_domains, detailed_results)
            
            # 打印摘要
            self.print_summary()
            
        except KeyboardInterrupt:
            print(f"\n⚠️ 用户中断操作")
        except Exception as e:
            print(f"\n❌ 程序执行出错: {e}")
            import traceback
            traceback.print_exc()


def main():
    """主函数入口"""
    parser = argparse.ArgumentParser(description="GameLove Hosts 更新工具")
    parser.add_argument("--delay", type=float, default=0.1, help="串行模式下的请求间延迟（秒）")
    parser.add_argument("--workers", type=int, default=10, help="并行模式下的最大工作线程数")
    parser.add_argument("--discovery-strategies", type=str, default="pattern", help="域名发现策略，逗号分隔：pattern,dns,robots")
    parser.add_argument("--rate-limit", type=float, default=5.0, help="发现阶段请求速率限制（每秒）")
    parser.add_argument("--discovery-timeout", type=float, default=2.0, help="发现阶段网络请求超时（秒）")

    group_parallel = parser.add_mutually_exclusive_group()
    group_parallel.add_argument("--parallel", dest="parallel", action="store_true", help="启用并行解析")
    group_parallel.add_argument("--no-parallel", dest="parallel", action="store_false", help="禁用并行解析")
    parser.set_defaults(parallel=True)

    group_smart = parser.add_mutually_exclusive_group()
    group_smart.add_argument("--smart", dest="smart", action="store_true", help="使用智能解析器")
    group_smart.add_argument("--no-smart", dest="smart", action="store_false", help="使用组合解析器")
    parser.set_defaults(smart=True)

    group_fastest = parser.add_mutually_exclusive_group()
    group_fastest.add_argument("--fastest", dest="fastest", action="store_true", help="在多个候选时优选延迟最低的 IP")
    group_fastest.add_argument("--no-fastest", dest="fastest", action="store_false", help="不进行延迟优选，使用首个成功候选")
    parser.set_defaults(fastest=True)

    args = parser.parse_args([]) if os.environ.get("GAMELOVE_ARGS_INLINE") else parser.parse_args()

    strategies = [s.strip() for s in (args.discovery_strategies or "").split(',') if s.strip()]
    updater = GameLoveHostsUpdater(
        delay_between_requests=args.delay,
        use_parallel=args.parallel,
        max_workers=args.workers,
        use_smart_resolver=args.smart,
        prefer_fastest=args.fastest,
        discovery_strategies=strategies or ["pattern"],
        rate_limit=args.rate_limit,
        discovery_timeout=args.discovery_timeout,
    )
    updater.run()


if __name__ == "__main__":
    main()