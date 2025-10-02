#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""稳定候选缓存模块

将历次解析成功且服务可达的 IP 记录为稳定候选，
用于在智能解析器的候选池中优先考虑，提高稳定性权重。
"""

import os
import json
import time
from typing import Dict, List, Optional


class StableCache:
    """稳定候选缓存

    数据结构：
    {
      "domain": {
        "ip": {
          "first_seen": 1730000000,
          "last_seen": 1730001000,
          "success": 5,
          "fail": 1,
          "reachable_success": 5,
          "reachable_fail": 0
        }
      }
    }
    """

    def __init__(self, path: Optional[str] = None, ttl_days: int = 7, min_success: int = 2, min_reach_rate: float = 0.6):
        base_dir = os.path.dirname(os.path.dirname(__file__))
        default_path = os.path.join(base_dir, 'hosts', 'cache.json')
        self.path = path or default_path
        self.ttl_seconds = ttl_days * 24 * 3600
        self.min_success = min_success
        self.min_reach_rate = min_reach_rate
        self._data: Dict[str, Dict[str, Dict[str, int | float]]] = {}
        self._load()

    def _load(self) -> None:
        try:
            with open(self.path, 'r', encoding='utf-8') as f:
                self._data = json.load(f)
        except Exception:
            self._data = {}

    def _save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, 'w', encoding='utf-8') as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def prune(self) -> None:
        now = time.time()
        changed = False
        for domain in list(self._data.keys()):
            for ip in list(self._data[domain].keys()):
                last_seen = self._data[domain][ip].get('last_seen', 0)
                if now - last_seen > self.ttl_seconds:
                    del self._data[domain][ip]
                    changed = True
            if not self._data[domain]:
                del self._data[domain]
                changed = True
        if changed:
            self._save()

    def record(self, domain: str, ip: str, success: bool, reachable: bool) -> None:
        now = time.time()
        d = self._data.setdefault(domain, {})
        rec = d.setdefault(ip, {
            'first_seen': now,
            'last_seen': now,
            'success': 0,
            'fail': 0,
            'reachable_success': 0,
            'reachable_fail': 0,
        })
        rec['last_seen'] = now
        if success:
            rec['success'] += 1
            rec['reachable_success'] += 1 if reachable else 0
            rec['reachable_fail'] += 0 if reachable else 1
        else:
            rec['fail'] += 1
            rec['reachable_fail'] += 1
        self._save()

    def get_candidates(self, domain: str, limit: int = 5) -> List[str]:
        """返回稳定候选 IP 列表（按稳定性排序）"""
        self.prune()
        d = self._data.get(domain)
        if not d:
            return []
        scored: List[tuple[str, float]] = []
        for ip, rec in d.items():
            succ = rec.get('success', 0)
            rs = rec.get('reachable_success', 0)
            rf = rec.get('reachable_fail', 0)
            total = rs + rf
            reach_rate = (rs / total) if total > 0 else 0.0
            if succ >= self.min_success and reach_rate >= self.min_reach_rate:
                # 简单稳定性评分：成功次数与可达率的乘积
                score = succ * (0.5 + 0.5 * reach_rate)
                scored.append((ip, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [ip for ip, _ in scored[:limit]]