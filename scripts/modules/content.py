#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""内容生成模块

负责生成 hosts 文本内容与统计报告文本内容。
"""

from datetime import datetime
from typing import Dict

from .platforms import GamePlatformConfig
from .resolvers import ResolveResult


class ContentGenerator:
    """内容生成器

    生成标准化的 hosts 文件内容，包含更新信息与项目链接。
    """

    @staticmethod
    def generate_hosts_content(ip_dict: Dict[str, str]) -> str:
        """生成 hosts 文件内容

        Args:
            ip_dict: 域名到 IP 的映射

        Returns:
            str: 完整的 hosts 文件内容
        """
        content = "# GameLove Host Start\n"

        # 域名按字典序排序，输出整齐对齐
        for domain in sorted(ip_dict.keys()):
            ip = ip_dict[domain]
            content += f"{ip:<30} {domain}\n"

        # 追加更新信息
        now = datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')
        content += f"\n# Update time: {now}\n"
        content += "# Update url: https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/hosts\n"
        content += "# Star me: https://github.com/artemisia1107/GameLove\n"
        content += "# GameLove Host End\n"

        return content

    @staticmethod
    def generate_json_data(ip_dict: Dict[str, str], failed_domains: list[str]) -> Dict[str, object]:
        """生成基础 JSON 数据

        Args:
            ip_dict: 成功解析的域名到 IP 映射
            failed_domains: 解析失败的域名列表

        Returns:
            Dict[str, object]: 基础 JSON 数据（后续由增强逻辑补充统计信息）
        """
        total_domains = len(ip_dict) + len(failed_domains)
        success_count = len(ip_dict)
        failed_count = len(failed_domains)
        success_rate = (success_count / total_domains * 100) if total_domains > 0 else 0

        now = datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')

        return {
            'summary': {
                'total_domains': total_domains,
                'success_count': success_count,
                'failed_count': failed_count,
                'success_rate': f"{success_rate:.1f}%",
                'update_time': now,
            },
            'all_hosts': ip_dict,
            'failed_domains': failed_domains,
            'urls': {
                'hosts_file': 'https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/hosts',
                'json_api': 'https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/hosts.json',
                'repository': 'https://github.com/artemisia1107/GameLove',
            },
        }


def create_statistics_report_content(detailed_results: Dict[str, ResolveResult], stats: Dict[str, float]) -> str:
    """创建统计报告文本内容

    Args:
        detailed_results: 域名解析的详细结果
        stats: 统计信息（包含总数、成功数、失败数、耗时等）

    Returns:
        str: 统计报告文本
    """
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 总体统计
    content = f"""GameLove Hosts 解析统计报告
生成时间: {now}
{'=' * 50}

总体统计:
- 总域名数: {stats['total_domains']}
- 成功解析: {stats['success_count']} ({stats['success_count']/stats['total_domains']*100:.1f}%)
- 解析失败: {stats['failed_count']} ({stats['failed_count']/stats['total_domains']*100:.1f}%)
- 总耗时: {stats['total_time']:.2f}秒
- 平均速度: {stats['total_domains']/stats['total_time']:.2f} 域名/秒

解析方法统计:
"""

    # 解析方法统计
    method_stats: Dict[str, Dict[str, float]] = {}
    response_times = []
    for result in detailed_results.values():
        if result.method:
            method_name = result.method.value
            if method_name not in method_stats:
                method_stats[method_name] = {'success': 0, 'failed': 0, 'times': []}
            if result.success:
                method_stats[method_name]['success'] += 1
            else:
                method_stats[method_name]['failed'] += 1
            if result.response_time:
                method_stats[method_name]['times'].append(result.response_time)
                response_times.append(result.response_time)

    for method, s in method_stats.items():
        total = s['success'] + s['failed']
        success_rate = s['success'] / total * 100 if total > 0 else 0
        avg_time = sum(s['times']) / len(s['times']) if s['times'] else 0
        content += f"- {method.upper():<10}: {s['success']}/{total} ({success_rate:.1f}%), 平均响应时间: {avg_time:.2f}s\n"

    # 平台统计
    content += "\n平台解析统计:\n"
    for platform_name, platform_info in GamePlatformConfig.get_all_platforms().items():
        success_count = sum(1 for domain in platform_info.domains
                            if domain in detailed_results and detailed_results[domain].success and detailed_results[domain].is_valid_ip)
        success_rate = success_count / len(platform_info.domains) * 100
        content += f"- {platform_name:<12}: {success_count}/{len(platform_info.domains)} ({success_rate:.1f}%)\n"

    # 失败域名详情
    failed_results = [r for r in detailed_results.values() if not r.success or not r.is_valid_ip]
    if failed_results:
        content += "\n失败域名详情:\n"
        for r in failed_results:
            error_info = r.error if r.error else "未知错误"
            if not r.is_valid_ip and r.ip:
                error_info = f"无效IP: {r.ip}"
            content += f"- {r.domain:<40}: {error_info}\n"

    return content