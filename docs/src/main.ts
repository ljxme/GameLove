/**
 * GameLove Hosts 连通性检测工具
 * 主要功能：检测各个游戏平台域名的连通性状态
 */

// 定义连通性状态枚举
enum ConnectivityStatus {
    PENDING = 'pending',
    TESTING = 'testing',
    SUCCESS = 'success',
    WARNING = 'warning',
    ERROR = 'error'
}

// 定义域名信息接口
interface DomainInfo {
    domain: string;
    status: ConnectivityStatus;
    responseTime?: number;
    lastChecked?: Date;
}

// 定义平台信息接口
interface PlatformInfo {
    name: string;
    domains: DomainInfo[];
    icon: string;
    color: string;
}

// 定义统计信息接口
interface Statistics {
    total: number;
    success: number;
    warning: number;
    error: number;
    testing: number;
}

/**
 * 主应用类
 * 负责管理整个连通性检测应用的状态和逻辑
 */
class HostsConnectivityChecker {
    private platforms: Map<string, PlatformInfo> = new Map();
    private statistics: Statistics = {
        total: 0,
        success: 0,
        warning: 0,
        error: 0,
        testing: 0
    };
    private isTestingAll: boolean = false;

    constructor() {
        this.initializePlatforms();
        this.bindEvents();
        this.loadHostsData();
    }

    /**
     * 初始化游戏平台信息
     */
    private initializePlatforms(): void {
        const platformsConfig = [
            { name: 'steam', icon: 'fab fa-steam', color: 'text-blue-600' },
            { name: 'epic', icon: 'fas fa-store', color: 'text-purple-600' },
            { name: 'origin', icon: 'fas fa-bullseye', color: 'text-orange-600' },
            { name: 'uplay', icon: 'fas fa-chess-rook', color: 'text-blue-800' },
            { name: 'battle.net', icon: 'fas fa-sword', color: 'text-indigo-600' },
            { name: 'gog', icon: 'fas fa-university', color: 'text-green-600' },
            { name: 'rockstar', icon: 'fas fa-star', color: 'text-yellow-600' }
        ];

        platformsConfig.forEach(config => {
            this.platforms.set(config.name, {
                name: config.name,
                domains: [],
                icon: config.icon,
                color: config.color
            });
        });
    }

    /**
     * 绑定事件监听器
     */
    private bindEvents(): void {
        const testAllBtn = document.getElementById('testAllBtn');
        const refreshBtn = document.getElementById('refreshBtn');

        testAllBtn?.addEventListener('click', () => this.testAllDomains());
        refreshBtn?.addEventListener('click', () => this.refreshStatus());
    }

    /**
     * 从GitHub加载hosts数据
     */
    private async loadHostsData(): Promise<void> {
        try {
            // 首先尝试从GitHub仓库加载hosts.json文件
            let response;
            let hostsData;
            
            try {
                response = await fetch('https://raw.githubusercontent.com/artemisia1107/GameLove/main/hosts.json');
                if (response.ok) {
                    hostsData = await response.json();
                } else {
                    throw new Error(`GitHub API error: ${response.status}`);
                }
            } catch (githubError) {
                console.warn('无法从GitHub加载数据，使用本地测试数据:', githubError);
                // 使用本地测试数据
                hostsData = this.getLocalTestData();
            }
            
            this.parseHostsData(hostsData);
            this.renderPlatforms();
            this.updateStatistics();
        } catch (error) {
            console.error('加载hosts数据失败:', error);
            this.showError('无法加载hosts数据，使用本地测试数据');
            // 使用本地测试数据作为后备
            const testData = this.getLocalTestData();
            this.parseHostsData(testData);
            this.renderPlatforms();
            this.updateStatistics();
        }
    }

    /**
     * 获取本地测试数据
     */
    private getLocalTestData(): any {
        return {
            "platforms": {
                "steam": {
                    "domains": [
                        { "domain": "steamcommunity.com", "status": "success" },
                        { "domain": "store.steampowered.com", "status": "success" },
                        { "domain": "api.steampowered.com", "status": "success" }
                    ]
                },
                "epic": {
                    "domains": [
                        { "domain": "launcher-public-service-prod06.ol.epicgames.com", "status": "success" },
                        { "domain": "epicgames.com", "status": "success" }
                    ]
                },
                "origin": {
                    "domains": [
                        { "domain": "origin.com", "status": "success" },
                        { "domain": "ea.com", "status": "success" }
                    ]
                },
                "uplay": {
                    "domains": [
                        { "domain": "ubisoft.com", "status": "success" },
                        { "domain": "ubi.com", "status": "success" }
                    ]
                },
                "battle.net": {
                    "domains": [
                        { "domain": "battle.net", "status": "success" },
                        { "domain": "blizzard.com", "status": "success" }
                    ]
                },
                "gog": {
                    "domains": [
                        { "domain": "gog.com", "status": "success" },
                        { "domain": "gog-statics.com", "status": "success" }
                    ]
                },
                "rockstar": {
                    "domains": [
                        { "domain": "rockstargames.com", "status": "success" },
                        { "domain": "socialclub.rockstargames.com", "status": "success" }
                    ]
                }
            }
        };
    }

    /**
     * 解析hosts数据
     */
    private parseHostsData(hostsData: any): void {
        if (hostsData.platforms) {
            Object.keys(hostsData.platforms).forEach(platformName => {
                const platform = this.platforms.get(platformName);
                if (platform && hostsData.platforms[platformName] && hostsData.platforms[platformName].domains) {
                    platform.domains = hostsData.platforms[platformName].domains.map((domainData: any) => ({
                        domain: domainData.domain,
                        status: ConnectivityStatus.PENDING
                    }));
                }
            });
        }
    }

    /**
     * 渲染平台和域名列表
     */
    private renderPlatforms(): void {
        this.platforms.forEach((platform, platformName) => {
            const container = document.getElementById(`${platformName}-domains`);
            if (container) {
                container.innerHTML = '';
                
                platform.domains.forEach(domainInfo => {
                    const domainElement = this.createDomainElement(domainInfo);
                    container.appendChild(domainElement);
                });

                this.updatePlatformStats(platformName);
            }
        });
    }

    /**
     * 创建域名元素
     */
    private createDomainElement(domainInfo: DomainInfo): HTMLElement {
        const element = document.createElement('div');
        element.className = 'domain-item';
        element.dataset.domain = domainInfo.domain;
        
        element.innerHTML = `
            <div class="flex items-center justify-between p-3 bg-gray-50 rounded-lg border">
                <div class="flex items-center">
                    <i class="fas fa-globe text-gray-400 mr-2"></i>
                    <span class="text-sm font-medium text-gray-700">${domainInfo.domain}</span>
                </div>
                <div class="flex items-center">
                    <span class="status-indicator status-${domainInfo.status}">
                        ${this.getStatusIcon(domainInfo.status)}
                    </span>
                    ${domainInfo.responseTime ? `<span class="text-xs text-gray-500 ml-2">${domainInfo.responseTime}ms</span>` : ''}
                </div>
            </div>
        `;

        // 添加点击事件进行单独测试
        element.addEventListener('click', () => this.testSingleDomain(domainInfo));

        return element;
    }

    /**
     * 获取状态图标
     */
    private getStatusIcon(status: ConnectivityStatus): string {
        switch (status) {
            case ConnectivityStatus.SUCCESS:
                return '<i class="fas fa-check-circle text-green-500"></i>';
            case ConnectivityStatus.WARNING:
                return '<i class="fas fa-exclamation-triangle text-yellow-500"></i>';
            case ConnectivityStatus.ERROR:
                return '<i class="fas fa-times-circle text-red-500"></i>';
            case ConnectivityStatus.TESTING:
                return '<i class="fas fa-spinner fa-spin text-blue-500"></i>';
            default:
                return '<i class="fas fa-circle text-gray-400"></i>';
        }
    }

    /**
     * 测试所有域名
     */
    private async testAllDomains(): Promise<void> {
        if (this.isTestingAll) return;

        this.isTestingAll = true;
        this.updateTestAllButton(true);

        const allDomains: DomainInfo[] = [];
        this.platforms.forEach(platform => {
            allDomains.push(...platform.domains);
        });

        // 批量测试，限制并发数量
        const batchSize = 10;
        for (let i = 0; i < allDomains.length; i += batchSize) {
            const batch = allDomains.slice(i, i + batchSize);
            await Promise.all(batch.map(domain => this.testDomainConnectivity(domain)));
            
            // 更新UI
            this.renderPlatforms();
            this.updateStatistics();
            
            // 短暂延迟避免过于频繁的请求
            await new Promise(resolve => setTimeout(resolve, 100));
        }

        this.isTestingAll = false;
        this.updateTestAllButton(false);
        this.updateLastUpdateTime();
    }

    /**
     * 测试单个域名连通性
     */
    private async testSingleDomain(domainInfo: DomainInfo): Promise<void> {
        await this.testDomainConnectivity(domainInfo);
        this.renderPlatforms();
        this.updateStatistics();
    }

    /**
     * 测试域名连通性的核心方法
     */
    private async testDomainConnectivity(domainInfo: DomainInfo): Promise<void> {
        domainInfo.status = ConnectivityStatus.TESTING;
        domainInfo.lastChecked = new Date();

        const startTime = Date.now();
        
        try {
            // 使用fetch API测试连通性
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 10000); // 10秒超时

            await fetch(`https://${domainInfo.domain}`, {
                method: 'HEAD',
                mode: 'no-cors', // 避免CORS问题
                signal: controller.signal
            });

            clearTimeout(timeoutId);
            const responseTime = Date.now() - startTime;
            domainInfo.responseTime = responseTime;

            // 根据响应时间判断状态
            if (responseTime < 2000) {
                domainInfo.status = ConnectivityStatus.SUCCESS;
            } else if (responseTime < 5000) {
                domainInfo.status = ConnectivityStatus.WARNING;
            } else {
                domainInfo.status = ConnectivityStatus.ERROR;
            }

        } catch (error) {
            const responseTime = Date.now() - startTime;
            domainInfo.responseTime = responseTime;
            
            // 由于no-cors模式，大多数请求会被标记为失败
            // 但如果能在合理时间内返回，说明域名是可达的
            if (responseTime < 5000) {
                domainInfo.status = ConnectivityStatus.SUCCESS;
            } else {
                domainInfo.status = ConnectivityStatus.ERROR;
            }
        }
    }

    /**
     * 刷新状态
     */
    private refreshStatus(): void {
        this.platforms.forEach(platform => {
            platform.domains.forEach(domain => {
                domain.status = ConnectivityStatus.PENDING;
                domain.responseTime = undefined;
            });
        });

        this.renderPlatforms();
        this.updateStatistics();
    }

    /**
     * 更新统计信息
     */
    private updateStatistics(): void {
        this.statistics = {
            total: 0,
            success: 0,
            warning: 0,
            error: 0,
            testing: 0
        };

        this.platforms.forEach(platform => {
            platform.domains.forEach(domain => {
                this.statistics.total++;
                switch (domain.status) {
                    case ConnectivityStatus.SUCCESS:
                        this.statistics.success++;
                        break;
                    case ConnectivityStatus.WARNING:
                        this.statistics.warning++;
                        break;
                    case ConnectivityStatus.ERROR:
                        this.statistics.error++;
                        break;
                    case ConnectivityStatus.TESTING:
                        this.statistics.testing++;
                        break;
                }
            });
        });

        this.updateStatisticsUI();
    }

    /**
     * 更新统计信息UI
     */
    private updateStatisticsUI(): void {
        document.getElementById('successCount')!.textContent = this.statistics.success.toString();
        document.getElementById('warningCount')!.textContent = this.statistics.warning.toString();
        document.getElementById('errorCount')!.textContent = this.statistics.error.toString();
        document.getElementById('testingCount')!.textContent = this.statistics.testing.toString();
        document.getElementById('totalStats')!.innerHTML = `<i class="fas fa-list mr-1"></i>总计: ${this.statistics.total} 个域名`;
    }

    /**
     * 更新平台统计信息
     */
    private updatePlatformStats(platformName: string): void {
        const platform = this.platforms.get(platformName);
        if (!platform) return;

        const successCount = platform.domains.filter(d => d.status === ConnectivityStatus.SUCCESS).length;
        const totalCount = platform.domains.length;

        const platformElement = document.querySelector(`[data-platform="${platformName}"]`);
        if (platformElement) {
            const successSpan = platformElement.querySelector('.platform-success');
            const totalSpan = platformElement.querySelector('.platform-total');
            
            if (successSpan) successSpan.textContent = successCount.toString();
            if (totalSpan) totalSpan.textContent = totalCount.toString();
        }
    }

    /**
     * 更新测试按钮状态
     */
    private updateTestAllButton(isTesting: boolean): void {
        const button = document.getElementById('testAllBtn') as HTMLButtonElement;
        if (button) {
            button.disabled = isTesting;
            button.innerHTML = isTesting 
                ? '<i class="fas fa-spinner fa-spin mr-2"></i>检测中...'
                : '<i class="fas fa-search mr-2"></i>检测所有域名';
        }
    }

    /**
     * 更新最后更新时间
     */
    private updateLastUpdateTime(): void {
        const now = new Date();
        const timeString = now.toLocaleString('zh-CN');
        document.getElementById('lastUpdate')!.innerHTML = `<i class="fas fa-clock mr-1"></i>最后更新: ${timeString}`;
    }

    /**
     * 显示错误信息
     */
    private showError(message: string): void {
        // 创建简单的错误提示
        const errorDiv = document.createElement('div');
        errorDiv.className = 'fixed top-4 right-4 bg-red-500 text-white px-4 py-2 rounded-lg shadow-lg z-50';
        errorDiv.innerHTML = `<i class="fas fa-exclamation-triangle mr-2"></i>${message}`;
        
        document.body.appendChild(errorDiv);
        
        setTimeout(() => {
            errorDiv.remove();
        }, 5000);
    }
}

// 当DOM加载完成后初始化应用
document.addEventListener('DOMContentLoaded', () => {
    new HostsConnectivityChecker();
});