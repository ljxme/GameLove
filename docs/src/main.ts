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
    retryCount?: number;
    errorMessage?: string;
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

// 定义检测配置接口
interface TestConfig {
    timeout: number;
    maxRetries: number;
    batchSize: number;
    batchDelay: number;
    fastTimeout: number;
    slowTimeout: number;
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
    private abortController: AbortController | null = null;
    private performanceMonitor: PerformanceMonitor;
    
    // 优化的配置参数
    private config: TestConfig = {
        timeout: 8000,        // 基础超时时间
        maxRetries: 2,        // 最大重试次数
        batchSize: 8,         // 并发批次大小
        batchDelay: 200,      // 批次间延迟
        fastTimeout: 3000,    // 快速检测超时
        slowTimeout: 10000    // 慢速检测超时
    };

    constructor() {
        // 初始化性能监控器
        this.performanceMonitor = new PerformanceMonitor({
            enableMemoryMonitoring: true,
            memoryCheckInterval: 30000, // 30秒检查一次
            maxMemoryUsage: 100, // 100MB限制
            enablePerformanceLogging: true
        });
        
        this.initializePlatforms();
        this.bindEvents();
        this.loadHostsData();
    }

    /**
     * 初始化平台数据
     */
    private initializePlatforms(): void {
        // 初始化各个游戏平台的基础信息
        const platformsData = [
            { name: 'Steam', icon: 'fab fa-steam', color: 'text-blue-600' },
            { name: 'Epic Games', icon: 'fas fa-gamepad', color: 'text-purple-600' },
            { name: 'Origin', icon: 'fas fa-rocket', color: 'text-orange-600' },
            { name: 'Uplay', icon: 'fas fa-shield-alt', color: 'text-blue-500' },
            { name: 'Battle.net', icon: 'fas fa-fire', color: 'text-blue-700' },
            { name: 'GOG', icon: 'fas fa-crown', color: 'text-purple-500' },
            { name: 'Rockstar', icon: 'fas fa-star', color: 'text-yellow-600' }
        ];

        platformsData.forEach(platform => {
            this.platforms.set(platform.name, {
                ...platform,
                domains: []
            });
        });
    }

    /**
     * 绑定事件监听器
     */
    private bindEvents(): void {
        const testAllBtn = document.getElementById('test-all-btn');
        const refreshBtn = document.getElementById('refresh-btn');
        
        if (testAllBtn) {
            testAllBtn.addEventListener('click', () => this.handleTestAllClick());
        }
        
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => this.refreshStatus());
        }
    }

    /**
     * 处理测试所有按钮点击事件
     */
    private async handleTestAllClick(): Promise<void> {
        if (this.isTestingAll) {
            this.stopAllTests();
        } else {
            await this.testAllDomains();
        }
    }

    /**
     * 停止所有测试
     */
    private stopAllTests(): void {
        if (this.abortController) {
            this.abortController.abort();
            this.abortController = null;
        }
        this.isTestingAll = false;
        this.updateTestAllButton(false);
        
        // 重置所有正在测试的域名状态
        this.platforms.forEach(platform => {
            platform.domains.forEach(domain => {
                if (domain.status === ConnectivityStatus.TESTING) {
                    domain.status = ConnectivityStatus.PENDING;
                }
            });
        });
        
        this.renderPlatforms();
        this.updateStatistics();
    }

    /**
     * 加载hosts数据
     */
    private async loadHostsData(): Promise<void> {
        try {
            // 尝试从远程API加载数据
            const response = await fetch('https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/hosts.json');
            if (response.ok) {
                const hostsData = await response.json();
                this.parseHostsData(hostsData);
            } else {
                throw new Error('Failed to load remote data');
            }
        } catch (error) {
            console.warn('Failed to load remote hosts data, using local test data:', error);
            // 使用本地测试数据作为后备
            try {
                const localData = this.getLocalTestData();
                this.parseHostsData(localData);
            } catch (localError) {
                this.showError('无法加载hosts数据，请检查网络连接');
            }
        }
    }

    /**
     * 获取本地测试数据
     */
    private getLocalTestData(): any {
        return {
            "urls": {
                "hosts_file": "https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/hosts",
                "json_api": "https://raw.githubusercontent.com/artemisia1107/GameLove/refs/heads/main/hosts.json"
            },
            "platforms": {
                "Steam": [
                    "steamcommunity.com",
                    "store.steampowered.com",
                    "steamcdn-a.akamaihd.net"
                ],
                "Epic Games": [
                    "launcher-public-service-prod06.ol.epicgames.com",
                    "epicgames.com",
                    "unrealengine.com"
                ],
                "Origin": [
                    "origin.com",
                    "ea.com",
                    "eaplay.com"
                ],
                "Uplay": [
                    "ubisoft.com",
                    "ubi.com",
                    "uplay.com"
                ],
                "Battle.net": [
                    "battle.net",
                    "blizzard.com",
                    "battlenet.com.cn"
                ],
                "GOG": [
                    "gog.com",
                    "gogalaxy.com",
                    "cdprojekt.com"
                ],
                "Rockstar": [
                    "rockstargames.com",
                    "socialclub.rockstargames.com",
                    "rsg.sc"
                ]
            }
        };
    }

    /**
     * 解析hosts数据
     */
    private parseHostsData(hostsData: any): void {
        if (hostsData && hostsData.platforms) {
            Object.entries(hostsData.platforms).forEach(([platformName, domains]) => {
                const platform = this.platforms.get(platformName);
                if (platform && Array.isArray(domains)) {
                    platform.domains = (domains as string[]).map(domain => ({
                        domain,
                        status: ConnectivityStatus.PENDING,
                        retryCount: 0
                    }));
                }
            });
        }
        this.renderPlatforms();
        this.updateStatistics();
    }

    /**
     * 渲染平台列表
     */
    private renderPlatforms(): void {
        const container = document.getElementById('platforms-container');
        if (!container) return;

        container.innerHTML = '';
        this.platforms.forEach(platform => {
            const platformElement = this.createPlatformElement(platform);
            container.appendChild(platformElement);
        });
    }

    /**
     * 创建平台元素
     */
    private createPlatformElement(platform: PlatformInfo): HTMLElement {
        const platformDiv = document.createElement('div');
        platformDiv.className = 'bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow duration-300';
        
        const successCount = platform.domains.filter(d => d.status === ConnectivityStatus.SUCCESS).length;
        const totalCount = platform.domains.length;
        const testingCount = platform.domains.filter(d => d.status === ConnectivityStatus.TESTING).length;
        
        platformDiv.innerHTML = `
            <div class="flex items-center justify-between mb-4">
                <div class="flex items-center">
                    <i class="${platform.icon} ${platform.color} text-2xl mr-3"></i>
                    <h3 class="text-xl font-semibold text-gray-800">${platform.name}</h3>
                </div>
                <div class="text-sm text-gray-600">
                    ${successCount}/${totalCount} 可用
                    ${testingCount > 0 ? `<span class="text-blue-500">(${testingCount} 检测中)</span>` : ''}
                </div>
            </div>
            <div class="space-y-2">
                ${platform.domains.map(domain => this.createDomainElement(domain).outerHTML).join('')}
            </div>
        `;
        
        return platformDiv;
    }

    /**
     * 创建域名元素
     */
    private createDomainElement(domainInfo: DomainInfo): HTMLElement {
        const domainDiv = document.createElement('div');
        domainDiv.className = 'flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors duration-200';
        
        const statusIcon = this.getStatusIcon(domainInfo.status);
        const responseTimeText = domainInfo.responseTime ? `${domainInfo.responseTime}ms` : '';
        const lastCheckedText = domainInfo.lastChecked ? 
            `最后检测: ${domainInfo.lastChecked.toLocaleTimeString()}` : '';
        
        domainDiv.innerHTML = `
            <div class="flex items-center">
                <span class="mr-3">${statusIcon}</span>
                <div>
                    <span class="font-medium text-gray-800">${domainInfo.domain}</span>
                    ${domainInfo.errorMessage ? `<div class="text-xs text-red-500">${domainInfo.errorMessage}</div>` : ''}
                    ${lastCheckedText ? `<div class="text-xs text-gray-500">${lastCheckedText}</div>` : ''}
                </div>
            </div>
            <div class="flex items-center space-x-2">
                ${responseTimeText ? `<span class="text-sm text-gray-600">${responseTimeText}</span>` : ''}
                <button class="test-single-btn px-3 py-1 text-sm bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors duration-200" 
                        data-domain="${domainInfo.domain}" 
                        ${domainInfo.status === ConnectivityStatus.TESTING ? 'disabled' : ''}>
                    ${domainInfo.status === ConnectivityStatus.TESTING ? '检测中...' : '测试'}
                </button>
            </div>
        `;
        
        // 绑定单个测试按钮事件
        const testBtn = domainDiv.querySelector('.test-single-btn') as HTMLButtonElement;
        if (testBtn) {
            testBtn.addEventListener('click', () => this.testSingleDomain(domainInfo));
        }
        
        return domainDiv;
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
     * 测试所有域名（优化版本）
     */
    private async testAllDomains(): Promise<void> {
        if (this.isTestingAll) return;

        // 开始性能监控
        this.performanceMonitor.startMeasure('testAllDomains');

        this.isTestingAll = true;
        this.abortController = new AbortController();
        this.updateTestAllButton(true);

        const allDomains: DomainInfo[] = [];
        this.platforms.forEach(platform => {
            allDomains.push(...platform.domains);
        });

        try {
            // 使用优化的批处理策略
            await this.processDomainsBatch(allDomains);
        } catch (error: any) {
            if (error.name !== 'AbortError') {
                console.error('测试过程中发生错误:', error);
                this.showError('测试过程中发生错误，请重试');
            }
        } finally {
            this.isTestingAll = false;
            this.abortController = null;
            this.updateTestAllButton(false);
            this.updateLastUpdateTime();
            // 结束性能监控
            this.performanceMonitor.endMeasure('testAllDomains');
        }
    }

    /**
     * 批处理域名测试
     */
    private async processDomainsBatch(domains: DomainInfo[]): Promise<void> {
        const { batchSize, batchDelay } = this.config;
        
        for (let i = 0; i < domains.length; i += batchSize) {
            if (this.abortController?.signal.aborted) {
                throw new Error('AbortError');
            }
            
            const batch = domains.slice(i, i + batchSize);
            
            // 并行处理当前批次
            await Promise.allSettled(
                batch.map(domain => this.testDomainWithRetry(domain))
            );
            
            // 实时更新UI
            this.renderPlatforms();
            this.updateStatistics();
            
            // 批次间延迟，避免过于频繁的请求
            if (i + batchSize < domains.length) {
                await this.delay(batchDelay);
            }
        }
    }

    /**
     * 带重试机制的域名测试
     */
    private async testDomainWithRetry(domainInfo: DomainInfo): Promise<void> {
        domainInfo.retryCount = 0;
        domainInfo.errorMessage = '';
        
        for (let attempt = 0; attempt <= this.config.maxRetries; attempt++) {
            if (this.abortController?.signal.aborted) {
                return;
            }
            
            try {
                await this.testDomainConnectivity(domainInfo);
                
                // 如果成功，跳出重试循环
                if (domainInfo.status === ConnectivityStatus.SUCCESS || 
                    domainInfo.status === ConnectivityStatus.WARNING) {
                    break;
                }
            } catch (error) {
                domainInfo.retryCount = attempt + 1;
                
                if (attempt === this.config.maxRetries) {
                    domainInfo.status = ConnectivityStatus.ERROR;
                    domainInfo.errorMessage = this.getErrorMessage(error);
                } else {
                    // 重试前短暂延迟
                    await this.delay(500 * (attempt + 1));
                }
            }
        }
    }

    /**
     * 测试单个域名连通性
     */
    private async testSingleDomain(domainInfo: DomainInfo): Promise<void> {
        await this.testDomainWithRetry(domainInfo);
        this.renderPlatforms();
        this.updateStatistics();
    }

    /**
     * 测试域名连通性的核心方法（优化版本）
     */
    private async testDomainConnectivity(domainInfo: DomainInfo): Promise<void> {
        // 开始性能监控
        this.performanceMonitor.startMeasure(`testDomain-${domainInfo.domain}`);
        
        domainInfo.status = ConnectivityStatus.TESTING;
        domainInfo.lastChecked = new Date();

        const startTime = Date.now();
        
        try {
            // 使用动态超时策略
            const timeout = this.getDynamicTimeout(domainInfo);
            const controller = new AbortController();
            
            // 组合信号：全局中止 + 单个请求超时
            const signals: AbortSignal[] = [controller.signal];
            if (this.abortController?.signal) {
                signals.push(this.abortController.signal);
            }
            const combinedSignal = this.combineAbortSignals(signals);
            
            const timeoutId = setTimeout(() => controller.abort(), timeout);

            // 尝试多种检测方法
            await this.performConnectivityTest(domainInfo.domain, combinedSignal);

            clearTimeout(timeoutId);
            const responseTime = Date.now() - startTime;
            domainInfo.responseTime = responseTime;

            // 根据响应时间判断状态
            this.determineStatus(domainInfo, responseTime);

        } catch (error) {
            const responseTime = Date.now() - startTime;
            domainInfo.responseTime = responseTime;
            
            // 智能错误处理
            this.handleConnectivityError(domainInfo, error, responseTime);
        } finally {
            // 结束性能监控
            this.performanceMonitor.endMeasure(`testDomain-${domainInfo.domain}`);
        }
    }

    /**
     * 执行连通性测试
     */
    private async performConnectivityTest(domain: string, signal: AbortSignal): Promise<void> {
        // 尝试多种测试方法，提高检测准确性
        const testMethods = [
            () => fetch(`https://${domain}`, { 
                method: 'HEAD', 
                mode: 'no-cors', 
                signal,
                cache: 'no-cache'
            }),
            () => fetch(`https://${domain}/favicon.ico`, { 
                method: 'GET', 
                mode: 'no-cors', 
                signal,
                cache: 'no-cache'
            }),
            () => fetch(`https://${domain}`, { 
                method: 'GET', 
                mode: 'no-cors', 
                signal,
                cache: 'no-cache'
            })
        ];

        // 尝试第一种方法
        try {
            await testMethods[0]();
        } catch (error) {
            // 如果第一种方法失败，尝试其他方法
            let lastError = error;
            for (let i = 1; i < testMethods.length; i++) {
                try {
                    await testMethods[i]();
                    return; // 成功则返回
                } catch (e) {
                    lastError = e;
                }
            }
            throw lastError;
        }
    }

    /**
     * 获取动态超时时间
     */
    private getDynamicTimeout(domainInfo: DomainInfo): number {
        // 根据历史性能调整超时时间
        if (domainInfo.responseTime) {
            if (domainInfo.responseTime < 1000) {
                return this.config.fastTimeout;
            } else if (domainInfo.responseTime > 5000) {
                return this.config.slowTimeout;
            }
        }
        return this.config.timeout;
    }

    /**
     * 组合多个AbortSignal
     */
    private combineAbortSignals(signals: AbortSignal[]): AbortSignal {
        const controller = new AbortController();
        
        signals.forEach(signal => {
            if (signal?.aborted) {
                controller.abort();
            } else {
                signal?.addEventListener('abort', () => controller.abort());
            }
        });
        
        return controller.signal;
    }

    /**
     * 确定连通性状态
     */
    private determineStatus(domainInfo: DomainInfo, responseTime: number): void {
        if (responseTime < 1500) {
            domainInfo.status = ConnectivityStatus.SUCCESS;
        } else if (responseTime < 4000) {
            domainInfo.status = ConnectivityStatus.WARNING;
        } else {
            domainInfo.status = ConnectivityStatus.ERROR;
        }
    }

    /**
     * 处理连通性错误
     */
    private handleConnectivityError(domainInfo: DomainInfo, error: any, responseTime: number): void {
        // 由于no-cors模式的限制，需要智能判断
        if (error.name === 'AbortError') {
            domainInfo.status = ConnectivityStatus.ERROR;
            domainInfo.errorMessage = '请求超时';
        } else if (responseTime < 3000) {
            // 快速返回的"错误"通常意味着域名是可达的
            domainInfo.status = ConnectivityStatus.SUCCESS;
        } else if (responseTime < 6000) {
            domainInfo.status = ConnectivityStatus.WARNING;
        } else {
            domainInfo.status = ConnectivityStatus.ERROR;
            domainInfo.errorMessage = this.getErrorMessage(error);
        }
    }

    /**
     * 获取错误消息
     */
    private getErrorMessage(error: any): string {
        if (error.name === 'AbortError') {
            return '请求超时';
        } else if (error.name === 'TypeError') {
            return '网络错误';
        } else {
            return '连接失败';
        }
    }

    /**
     * 销毁实例并清理资源
     */
    destroy(): void {
        // 停止所有正在进行的测试
        if (this.abortController) {
            this.abortController.abort();
        }
        
        // 清理性能监控
        this.performanceMonitor.destroy();
        
        // 清理DOM事件监听器
        const testBtn = document.getElementById('test-all-btn');
        const refreshBtn = document.getElementById('refresh-btn');
        
        if (testBtn) {
            testBtn.removeEventListener('click', this.handleTestAllClick.bind(this));
        }
        if (refreshBtn) {
            refreshBtn.removeEventListener('click', this.refreshStatus.bind(this));
        }
    }

    /**
     * 延迟函数
     */
    private delay(ms: number): Promise<void> {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * 刷新状态
     */
    private refreshStatus(): void {
        this.platforms.forEach(platform => {
            platform.domains.forEach(domain => {
                domain.status = ConnectivityStatus.PENDING;
                domain.responseTime = undefined;
                domain.lastChecked = undefined;
                domain.retryCount = 0;
                domain.errorMessage = '';
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
        this.updatePlatformStats();
    }

    /**
     * 更新统计信息UI
     */
    private updateStatisticsUI(): void {
        const elements = {
            total: document.getElementById('total-count'),
            success: document.getElementById('success-count'),
            warning: document.getElementById('warning-count'),
            error: document.getElementById('error-count'),
            testing: document.getElementById('testing-count')
        };

        Object.entries(elements).forEach(([key, element]) => {
            if (element) {
                element.textContent = this.statistics[key as keyof Statistics].toString();
            }
        });
    }

    /**
     * 更新平台统计信息
     */
    private updatePlatformStats(platformName?: string): void {
        const platforms = platformName ? [platformName] : Array.from(this.platforms.keys());
        
        platforms.forEach(name => {
            const platform = this.platforms.get(name);
            if (platform) {
                const successCount = platform.domains.filter(d => d.status === ConnectivityStatus.SUCCESS).length;
                const totalCount = platform.domains.length;
                
                // 更新平台特定的统计显示
                const platformElement = document.querySelector(`[data-platform="${name}"]`);
                if (platformElement) {
                    const statsElement = platformElement.querySelector('.platform-stats');
                    if (statsElement) {
                        statsElement.textContent = `${successCount}/${totalCount} 可用`;
                    }
                }
            }
        });
    }

    /**
     * 更新测试所有按钮状态
     */
    private updateTestAllButton(isTesting: boolean): void {
        const button = document.getElementById('test-all-btn') as HTMLButtonElement;
        if (button) {
            if (isTesting) {
                button.innerHTML = '<i class="fas fa-stop mr-2"></i>停止测试';
                button.className = 'px-6 py-3 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors duration-200 font-medium';
            } else {
                button.innerHTML = '<i class="fas fa-play mr-2"></i>测试所有';
                button.className = 'px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors duration-200 font-medium';
            }
        }
    }

    /**
     * 更新最后更新时间
     */
    private updateLastUpdateTime(): void {
        const element = document.getElementById('last-update-time');
        if (element) {
            element.textContent = `最后更新: ${new Date().toLocaleString()}`;
        }
    }

    /**
     * 显示错误信息
     */
    private showError(message: string): void {
        // 创建错误提示
        const errorDiv = document.createElement('div');
        errorDiv.className = 'fixed top-4 right-4 bg-red-500 text-white px-6 py-3 rounded-lg shadow-lg z-50 animate-fade-in';
        errorDiv.innerHTML = `
            <div class="flex items-center">
                <i class="fas fa-exclamation-triangle mr-2"></i>
                <span>${message}</span>
                <button class="ml-4 text-white hover:text-gray-200" onclick="this.parentElement.parentElement.remove()">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `;
        
        document.body.appendChild(errorDiv);
        
        // 3秒后自动移除
        setTimeout(() => {
            if (errorDiv.parentElement) {
                errorDiv.remove();
            }
        }, 3000);
    }
}

// 初始化应用
document.addEventListener('DOMContentLoaded', () => {
    new HostsConnectivityChecker();
});

/**
 * 性能监控配置接口
 */
interface PerformanceConfig {
    enableMemoryMonitoring: boolean;
    memoryCheckInterval: number;
    maxMemoryUsage: number;
    enablePerformanceLogging: boolean;
}

/**
 * 性能监控器类
 */
class PerformanceMonitor {
    private config: PerformanceConfig;
    private memoryCheckTimer?: number;
    private performanceEntries: Map<string, number> = new Map();

    constructor(config: PerformanceConfig) {
        this.config = config;
        if (this.config.enableMemoryMonitoring) {
            this.startMemoryMonitoring();
        }
    }

    /**
     * 开始性能测量
     */
    startMeasure(name: string): void {
        if (this.config.enablePerformanceLogging) {
            this.performanceEntries.set(name, performance.now());
        }
    }

    /**
     * 结束性能测量并记录
     */
    endMeasure(name: string): number {
        if (!this.config.enablePerformanceLogging) return 0;
        
        const startTime = this.performanceEntries.get(name);
        if (startTime) {
            const duration = performance.now() - startTime;
            console.log(`[性能] ${name}: ${duration.toFixed(2)}ms`);
            this.performanceEntries.delete(name);
            return duration;
        }
        return 0;
    }

    /**
     * 开始内存监控
     */
    private startMemoryMonitoring(): void {
        this.memoryCheckTimer = window.setInterval(() => {
            this.checkMemoryUsage();
        }, this.config.memoryCheckInterval);
    }

    /**
     * 检查内存使用情况
     */
    private checkMemoryUsage(): void {
        if ('memory' in performance) {
            const memory = (performance as any).memory;
            const usedMB = memory.usedJSHeapSize / 1024 / 1024;
            
            if (usedMB > this.config.maxMemoryUsage) {
                console.warn(`[内存警告] 当前使用: ${usedMB.toFixed(2)}MB, 超过限制: ${this.config.maxMemoryUsage}MB`);
                this.triggerGarbageCollection();
            }
        }
    }

    /**
     * 触发垃圾回收建议
     */
    private triggerGarbageCollection(): void {
        // 清理性能条目
        this.performanceEntries.clear();
        
        // 建议浏览器进行垃圾回收
        if ('gc' in window) {
            (window as any).gc();
        }
    }

    /**
     * 停止监控
     */
    destroy(): void {
        if (this.memoryCheckTimer) {
            clearInterval(this.memoryCheckTimer);
        }
        this.performanceEntries.clear();
    }
}