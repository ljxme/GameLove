#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""文件管理模块

负责保存 hosts/JSON 文件以及更新 README.md 中的展示内容。
"""

import os
import json
from datetime import datetime
from typing import Any, Dict


class FileManager:
    """文件管理器

    负责文件保存到仓库根目录与 scripts/hosts 备份目录，并提供
    更新 README.md 中 hosts 内容的能力。
    """

    def __init__(self, base_dir: str | None = None) -> None:
        """初始化文件管理器

        Args:
            base_dir: 仓库根目录（默认为脚本所在目录的上一级）
        """
        if base_dir is None:
            self.base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
        else:
            self.base_dir = base_dir

        # 备份目录固定为 scripts/hosts
        self.hosts_dir = os.path.join(self.base_dir, 'scripts', 'hosts')

    def save_hosts_file(self, content: str, filename: str, is_root: bool = False) -> str:
        """保存 hosts 文件内容到指定位置

        Args:
            content: 文件内容
            filename: 文件名（如 'hosts' 或 'hosts_steam'）
            is_root: True 保存到仓库根目录；False 保存到备份目录

        Returns:
            str: 实际保存的文件路径
        """
        if is_root:
            filepath = os.path.join(self.base_dir, filename)
        else:
            os.makedirs(self.hosts_dir, exist_ok=True)
            filepath = os.path.join(self.hosts_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return filepath

    def save_json_file(self, data: Dict[str, Any], filename: str, is_root: bool = False) -> str:
        """保存 JSON 文件

        Args:
            data: JSON 数据对象
            filename: 文件名（如 'hosts.json'）
            is_root: True 保存到仓库根目录；False 保存到备份目录

        Returns:
            str: 实际保存的文件路径
        """
        if is_root:
            filepath = os.path.join(self.base_dir, filename)
        else:
            os.makedirs(self.hosts_dir, exist_ok=True)
            filepath = os.path.join(self.hosts_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return filepath

    def update_readme_hosts_content(self, hosts_content: str) -> bool:
        """更新 README.md 中的 hosts 内容块

        Args:
            hosts_content: 完整 hosts 文本内容

        Returns:
            bool: 是否更新成功
        """
        readme_path = os.path.join(self.base_dir, 'README.md')
        try:
            with open(readme_path, 'r', encoding='utf-8') as f:
                readme_content = f.read()
        except FileNotFoundError:
            print('README.md文件未找到')
            return False

        # 匹配从 ``` 开始的 hosts 代码块到更新时间行结束
        import re
        pattern = r"```\n# GameLove Host Start.*?# GameLove Host End\n```\n\n该内容会自动定时更新，数据更新时间：[^\n]*"
        match = re.search(pattern, readme_content, re.DOTALL)
        if not match:
            print('在README.md中未找到完整的hosts内容块')
            return False

        clean_hosts_content = self._clean_hosts_content_for_readme(hosts_content)
        now = datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')
        new_hosts_block = f"""```
# GameLove Host Start
{clean_hosts_content}
# GameLove Host End
```

该内容会自动定时更新，数据更新时间：{now}"""

        new_readme_content = readme_content[:match.start()] + new_hosts_block + readme_content[match.end():]
        try:
            with open(readme_path, 'w', encoding='utf-8') as f:
                f.write(new_readme_content)
            print(f"README.md已更新，更新时间：{now}")
            return True
        except Exception as e:
            print(f"更新README.md时出错：{e}")
            return False

    def _clean_hosts_content_for_readme(self, hosts_content: str) -> str:
        """清理 hosts 内容用于 README 展示"""
        hosts_lines = hosts_content.split('\n')
        if hosts_lines and hosts_lines[0].strip() == '# GameLove Host Start':
            hosts_lines = hosts_lines[1:]
        if hosts_lines and hosts_lines[-1].strip() == '# GameLove Host End':
            hosts_lines = hosts_lines[:-1]
        clean_lines = []
        for line in hosts_lines:
            line = line.strip()
            if line and line not in ['# GameLove Host Start', '# GameLove Host End']:
                clean_lines.append(line)
        return '\n'.join(clean_lines)

    def update_readme_platform_counts(self, platform_counts: Dict[str, int]) -> bool:
        """更新 README.md 中平台域名数量统计表

        该方法定位到“支持的游戏平台”表格区域，并将每一行中的“X个域名”替换为传入的实际数量。
        为避免误匹配，仅在该段落内进行替换。

        Args:
            platform_counts: 平台名称到域名数量的映射

        Returns:
            bool: 是否更新成功
        """
        readme_path = os.path.join(self.base_dir, 'README.md')
        try:
            with open(readme_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except FileNotFoundError:
            print('README.md文件未找到')
            return False

        import re
        # 锁定“支持的游戏平台”段落范围
        section_start = re.search(r"^##\s*三、支持的游戏平台\s*$", content, flags=re.MULTILINE)
        if not section_start:
            print('未找到“支持的游戏平台”段落标题')
            return False

        # 查找下一个同级标题，作为段落结束
        section_end = re.search(r"^##\s+", content[section_start.end():], flags=re.MULTILINE)
        start_idx = section_start.start()
        end_idx = section_start.end() + (section_end.start() if section_end else len(content[section_start.end():]))

        prefix = content[:start_idx]
        section = content[start_idx:end_idx]
        suffix = content[end_idx:]

        updated_section = section
        for name, count in platform_counts.items():
            # 平台名在 README 中可能有装饰，如加粗或图标，这里仅根据平台关键字匹配行
            # 例如："**Steam** | 7个域名" 或 "Battle.net | 4个域名"
            pattern = rf"(^.*?{re.escape(name)}.*?\|\s*)\d+个域名"
            replacement = rf"\1{count}个域名"
            updated_section = re.sub(pattern, replacement, updated_section, flags=re.MULTILINE)

        if updated_section == section:
            print('README 平台域名数量未变化或未匹配到表格行')
            return False

        try:
            with open(readme_path, 'w', encoding='utf-8') as f:
                f.write(prefix + updated_section + suffix)
            print('README 平台域名数量统计已更新')
            return True
        except Exception as e:
            print(f'更新 README 平台域名数量失败：{e}')
            return False