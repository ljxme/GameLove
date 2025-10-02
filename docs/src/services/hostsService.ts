import type { HostsJson, IHostsDataSource } from '../types';

/**
 * Hosts 数据源实现
 * - 主来源：GitHub RAW
 * - 备来源：jsDelivr CDN
 * - 本地回退：内置测试数据
 */
/**
 * HostsDataSource
 * 统一管理 `hosts.json` 的加载流程：主源 -> 备源 -> 本地回退。
 * - 主源：GitHub RAW（更新及时）
 * - 备源：jsDelivr CDN（可用性高）
 * - 本地回退：内置测试数据，确保前端在离线或远端不可达时仍可运行。
 */
export class HostsDataSource implements IHostsDataSource {
  private readonly primaryUrl =
    'https://raw.githubusercontent.com/artemisia1107/GameLove/main/hosts.json';
  private readonly backupUrl = 'https://cdn.jsdelivr.net/gh/artemisia1107/GameLove@main/hosts.json';

  /**
   * 加载 hosts 数据。
   * 返回：优先返回远端有效 JSON，若失败则返回本地回退数据。
   */
  async load(): Promise<HostsJson> {
    // 尝试主来源
    const primary = await this.safeFetch(this.primaryUrl);
    if (primary) return primary;

    // 退回备来源
    const backup = await this.safeFetch(this.backupUrl);
    if (backup) return backup;

    // 最后使用本地数据
    return this.getLocalFallback();
  }

  /**
   * 安全获取远端数据。
   * - 捕获异常并返回 `null`，避免传播网络错误导致 UI 崩溃。
   * - 简单结构校验：需要存在 `platforms` 字段。
   */
  private async safeFetch(url: string): Promise<HostsJson | null> {
    try {
      const resp = await fetch(url, { cache: 'no-store' });
      if (!resp.ok) return null;
      const data = await resp.json();
      // 轻量校验结构
      if (data && typeof data === 'object' && data.platforms) {
        return data as HostsJson;
      }
      return null;
    } catch {
      return null;
    }
  }

  /**
   * 本地回退数据。
   * - 提供最小可运行集，方便快速验证 UI 与逻辑。
   */
  private getLocalFallback(): HostsJson {
    return {
      urls: {
        hosts_file: 'https://raw.githubusercontent.com/artemisia1107/GameLove/main/hosts',
        json_api: 'https://raw.githubusercontent.com/artemisia1107/GameLove/main/hosts.json',
      },
      platforms: {
        steam: {
          domains: [
            { domain: 'steamcommunity.com' },
            { domain: 'store.steampowered.com' },
            { domain: 'steamcdn-a.akamaihd.net' },
          ],
        },
        epic: {
          domains: [
            { domain: 'launcher-public-service-prod06.ol.epicgames.com' },
            { domain: 'epicgames.com' },
            { domain: 'unrealengine.com' },
          ],
        },
        origin: {
          domains: [{ domain: 'origin.com' }, { domain: 'ea.com' }, { domain: 'eaplay.com' }],
        },
        uplay: {
          domains: [{ domain: 'ubisoft.com' }, { domain: 'ubi.com' }, { domain: 'uplay.com' }],
        },
        'battle.net': {
          domains: [
            { domain: 'battle.net' },
            { domain: 'blizzard.com' },
            { domain: 'battlenet.com.cn' },
          ],
        },
        gog: {
          domains: [{ domain: 'gog.com' }, { domain: 'gogalaxy.com' }, { domain: 'cdprojekt.com' }],
        },
        rockstar: {
          domains: [
            { domain: 'rockstargames.com' },
            { domain: 'socialclub.rockstargames.com' },
            { domain: 'rsg.sc' },
          ],
        },
      },
    };
  }
}
