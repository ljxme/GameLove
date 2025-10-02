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
    pending: number;
    successRate: number;
    averageResponseTime: number;
    lastUpdateTime: Date | null;
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
        testing: 0,
        pending: 0,
        successRate: 0,
        averageResponseTime: 0,
        lastUpdateTime: null
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
            const handler = () => this.handleTestAllClick();
            (testAllBtn as any).__onClick = handler;
            testAllBtn.addEventListener('click', handler);
        }

        if (refreshBtn) {
            const handler = () => this.refreshStatus();
            (refreshBtn as any).__onClick = handler;
            refreshBtn.addEventListener('click', handler);
        }
    }

    /**
     * 处理测试所有按钮点击事件
     */
    private async handleTestAllClick(): Promise<void> {
        if (this.isTestingAll) {
            this.stopAllTests();
        } else {
            // 显示确认对话框（如果有正在进行的测试）
            const hasOngoingTests = Array.from(this.platforms.values()).some(platform =>
                platform.domains.some(domain => domain.status === ConnectivityStatus.TESTING)
            );
            
            if (hasOngoingTests) {
                const confirmed = confirm('检测到有正在进行的测试，是否要重新开始全部测试？');
                if (!confirmed) return;
            }
            
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
            // 尝试从远程API加载数据（修正为正确的 RAW 路径）
            const response = await fetch('https://raw.githubusercontent.com/artemisia1107/GameLove/main/hosts.json', { cache: 'no-store' });
            if (response.ok) {
                const hostsData = await response.json();
                this.parseHostsData(hostsData);
            } else {
                throw new Error(`Failed to load remote data: ${response.status} ${response.statusText}`);
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
        // 本地数据结构与真实 hosts.json 对齐，避免解析失败
        return {
            "urls": {
                "hosts_file": "https://raw.githubusercontent.com/artemisia1107/GameLove/main/hosts",
                "json_api": "https://raw.githubusercontent.com/artemisia1107/GameLove/main/hosts.json"
            },
            "platforms": {
                "steam": {
                    "domains": [
                        { "domain": "steamcommunity.com" },
                        { "domain": "store.steampowered.com" },
                        { "domain": "steamcdn-a.akamaihd.net" }
                    ]
                },
                "epic": {
                    "domains": [
                        { "domain": "launcher-public-service-prod06.ol.epicgames.com" },
                        { "domain": "epicgames.com" },
                        { "domain": "unrealengine.com" }
                    ]
                },
                "origin": {
                    "domains": [
                        { "domain": "origin.com" },
                        { "domain": "ea.com" },
                        { "domain": "eaplay.com" }
                    ]
                },
                "uplay": {
                    "domains": [
                        { "domain": "ubisoft.com" },
                        { "domain": "ubi.com" },
                        { "domain": "uplay.com" }
                    ]
                },
                "battle.net": {
                    "domains": [
                        { "domain": "battle.net" },
                        { "domain": "blizzard.com" },
                        { "domain": "battlenet.com.cn" }
                    ]
                },
                "gog": {
                    "domains": [
                        { "domain": "gog.com" },
                        { "domain": "gogalaxy.com" },
                        { "domain": "cdprojekt.com" }
                    ]
                },
                "rockstar": {
                    "domains": [
                        { "domain": "rockstargames.com" },
                        { "domain": "socialclub.rockstargames.com" },
                        { "domain": "rsg.sc" }
                    ]
                }
            }
        };
    }

    /**
     * 解析hosts数据
     */
    private parseHostsData(hostsData: any): void {
        if (hostsData && hostsData.platforms) {
            // 处理实际的hosts.json格式
            Object.entries(hostsData.platforms).forEach(([platformKey, platformData]: [string, any]) => {
                // 将平台键名映射到显示名称
                const platformNameMap: { [key: string]: string } = {
                    'steam': 'Steam',
                    'epic': 'Epic Games',
                    'origin': 'Origin',
                    'uplay': 'Uplay',
                    'battle.net': 'Battle.net',
                    'gog': 'GOG',
                    'rockstar': 'Rockstar'
                };
                
                const platformName = platformNameMap[platformKey] || platformKey;
                const platform = this.platforms.get(platformName);
                
                if (!platform) {
                    return;
                }

                // 兼容两种域名数组格式：字符串数组或对象数组
                const domainsArray = platformData?.domains;
                if (Array.isArray(domainsArray)) {
                    platform.domains = domainsArray.map((item: any) => ({
                        domain: typeof item === 'string' ? item : item?.domain,
                        status: ConnectivityStatus.PENDING,
                        retryCount: 0
                    })).filter(d => !!d.domain);
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
        platformDiv.className = 'bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-all duration-300 transform hover:scale-[1.02]';
        
        const successCount = platform.domains.filter(d => d.status === ConnectivityStatus.SUCCESS).length;
        const totalCount = platform.domains.length;
        const testingCount = platform.domains.filter(d => d.status === ConnectivityStatus.TESTING).length;
        const errorCount = platform.domains.filter(d => d.status === ConnectivityStatus.ERROR).length;
        const warningCount = platform.domains.filter(d => d.status === ConnectivityStatus.WARNING).length;
        
        // 计算成功率
        const successRate = totalCount > 0 ? Math.round((successCount / totalCount) * 100) : 0;
        
        // 确定平台状态颜色
        let statusColor = 'text-gray-500';
        let statusBg = 'bg-gray-100';
        if (testingCount > 0) {
            statusColor = 'text-blue-600';
            statusBg = 'bg-blue-100';
        } else if (successRate >= 80) {
            statusColor = 'text-green-600';
            statusBg = 'bg-green-100';
        } else if (successRate >= 50) {
            statusColor = 'text-yellow-600';
            statusBg = 'bg-yellow-100';
        } else if (successCount > 0) {
            statusColor = 'text-orange-600';
            statusBg = 'bg-orange-100';
        } else if (errorCount > 0) {
            statusColor = 'text-red-600';
            statusBg = 'bg-red-100';
        }
        
        platformDiv.innerHTML = `
            <div class="flex items-center justify-between mb-4">
                <div class="flex items-center">
                    <div class="relative">
                        <i class="${platform.icon} ${platform.color} text-2xl mr-3 transition-transform duration-300 hover:scale-110"></i>
                        ${testingCount > 0 ? '<div class="absolute -top-1 -right-1 w-3 h-3 bg-blue-500 rounded-full animate-pulse"></div>' : ''}
                    </div>
                    <h3 class="text-xl font-semibold text-gray-800">${platform.name}</h3>
                </div>
                <div class="flex items-center gap-3">
                    <div class="text-sm ${statusColor} font-medium">
                        ${successCount}/${totalCount} 可用
                        ${successRate > 0 ? `(${successRate}%)` : ''}
                    </div>
                    <div class="px-3 py-1 rounded-full text-xs font-medium ${statusBg} ${statusColor}">
                        ${testingCount > 0 ? `检测中 ${testingCount}` : 
                          successRate >= 80 ? '优秀' :
                          successRate >= 50 ? '良好' :
                          successCount > 0 ? '一般' :
                          errorCount > 0 ? '异常' : '未知'}
                    </div>
                </div>
            </div>
            
            <!-- 平台进度条 -->
            <div class="mb-4">
                <div class="flex justify-between text-xs text-gray-500 mb-1">
                    <span>连接状态</span>
                    <span>${successCount + errorCount + warningCount}/${totalCount} 已检测</span>
                </div>
                <div class="w-full bg-gray-200 rounded-full h-2 overflow-hidden">
                    <div class="h-full flex">
                        <div class="bg-green-500 transition-all duration-500" style="width: ${(successCount / totalCount) * 100}%"></div>
                        <div class="bg-yellow-500 transition-all duration-500" style="width: ${(warningCount / totalCount) * 100}%"></div>
                        <div class="bg-red-500 transition-all duration-500" style="width: ${(errorCount / totalCount) * 100}%"></div>
                        <div class="bg-blue-500 animate-pulse transition-all duration-500" style="width: ${(testingCount / totalCount) * 100}%"></div>
                    </div>
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
        
        // 根据状态设置不同的样式
        let statusClass = 'bg-gray-50 border-l-4 border-gray-300';
        let statusBadge = '';
        
        switch (domainInfo.status) {
            case ConnectivityStatus.SUCCESS:
                statusClass = 'bg-green-50 border-l-4 border-green-400';
                statusBadge = '<span class="px-2 py-1 bg-green-100 text-green-800 text-xs rounded-full font-medium">正常</span>';
                break;
            case ConnectivityStatus.WARNING:
                statusClass = 'bg-yellow-50 border-l-4 border-yellow-400';
                statusBadge = '<span class="px-2 py-1 bg-yellow-100 text-yellow-800 text-xs rounded-full font-medium">警告</span>';
                break;
            case ConnectivityStatus.ERROR:
                statusClass = 'bg-red-50 border-l-4 border-red-400';
                statusBadge = '<span class="px-2 py-1 bg-red-100 text-red-800 text-xs rounded-full font-medium">异常</span>';
                break;
            case ConnectivityStatus.TESTING:
                statusClass = 'bg-blue-50 border-l-4 border-blue-400 animate-pulse';
                statusBadge = '<span class="px-2 py-1 bg-blue-100 text-blue-800 text-xs rounded-full font-medium animate-pulse">检测中</span>';
                break;
            default:
                statusClass = 'bg-gray-50 border-l-4 border-gray-300';
                statusBadge = '<span class="px-2 py-1 bg-gray-100 text-gray-600 text-xs rounded-full font-medium">未知</span>';
        }
        
        domainDiv.className = `flex items-center justify-between p-3 ${statusClass} rounded-lg hover:shadow-md transition-all duration-200 transform hover:scale-[1.01]`;
        
        const statusIcon = this.getStatusIcon(domainInfo.status);
        const responseTimeText = domainInfo.responseTime ? `${domainInfo.responseTime}ms` : '';
        const lastCheckedText = domainInfo.lastChecked ? 
            `最后检测: ${domainInfo.lastChecked.toLocaleTimeString()}` : '';
        
        // 响应时间颜色
        let responseTimeColor = 'text-gray-600';
        if (domainInfo.responseTime) {
            if (domainInfo.responseTime < 200) {
                responseTimeColor = 'text-green-600';
            } else if (domainInfo.responseTime < 500) {
                responseTimeColor = 'text-yellow-600';
            } else {
                responseTimeColor = 'text-red-600';
            }
        }
        
        domainDiv.innerHTML = `
            <div class="flex items-center flex-1">
                <span class="mr-3 text-lg">${statusIcon}</span>
                <div class="flex-1">
                    <div class="flex items-center gap-2 mb-1">
                        <span class="font-medium text-gray-800">${domainInfo.domain}</span>
                        ${statusBadge}
                    </div>
                    <div class="flex items-center gap-4 text-xs">
                        ${domainInfo.errorMessage ? `<span class="text-red-500 flex items-center"><i class="fas fa-exclamation-triangle mr-1"></i>${domainInfo.errorMessage}</span>` : ''}
                        ${lastCheckedText ? `<span class="text-gray-500 flex items-center"><i class="fas fa-clock mr-1"></i>${lastCheckedText}</span>` : ''}
                        ${responseTimeText ? `<span class="${responseTimeColor} flex items-center font-medium"><i class="fas fa-tachometer-alt mr-1"></i>${responseTimeText}</span>` : ''}
                    </div>
                </div>
            </div>
            <div class="flex items-center space-x-2 ml-4">
                <button class="test-single-btn px-3 py-1 text-sm bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-all duration-200 font-medium shadow-sm transform hover:scale-105 disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none" 
                        data-domain="${domainInfo.domain}" 
                        ${domainInfo.status === ConnectivityStatus.TESTING ? 'disabled' : ''}>
                    <i class="fas ${domainInfo.status === ConnectivityStatus.TESTING ? 'fa-spinner fa-spin' : 'fa-play'} mr-1"></i>
                    ${domainInfo.status === ConnectivityStatus.TESTING ? '检测中' : '测试'}
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
        
        // 添加全局测试开始动画
        this.addGlobalTestStartAnimation();
        this.updateTestAllButton(true);

        const allDomains: DomainInfo[] = [];
        this.platforms.forEach(platform => {
            allDomains.push(...platform.domains);
        });

        try {
            // 重置所有域名状态
            this.resetAllDomainsStatus(allDomains);
            
            // 使用优化的批处理策略
            await this.processDomainsBatch(allDomains);
            
            // 添加全局测试完成动画
            this.addGlobalTestCompleteAnimation();
            
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
            this.removeGlobalTestAnimation();
            // 结束性能监控
            this.performanceMonitor.endMeasure('testAllDomains');
        }
    }

    /**
     * 添加全局测试开始动画
     */
    private addGlobalTestStartAnimation(): void {
        const container = document.querySelector('.controls-container');
        if (container) {
            container.classList.add('testing-active');
        }
        
        // 添加页面级别的测试状态指示
        document.body.classList.add('testing-mode');
        
        // 显示测试开始提示
        this.showTestingToast('开始检测所有域名...', 'info');
    }

    /**
     * 添加全局测试完成动画
     */
    private addGlobalTestCompleteAnimation(): void {
        const successCount = this.statistics.success;
        const totalCount = this.statistics.total;
        const successRate = totalCount > 0 ? Math.round((successCount / totalCount) * 100) : 0;
        
        // 显示详细的完成统计
        this.showDetailedTestResults();
        
        // 添加完成动画效果
        this.addTestCompleteVisualEffects();
        
        // 显示简短的完成提示
        let message = '';
        let type: 'success' | 'warning' | 'error' = 'success';
        
        if (successRate >= 80) {
            message = `检测完成！成功率 ${successRate}% - 连接状态良好 🎉`;
            type = 'success';
        } else if (successRate >= 50) {
            message = `检测完成！成功率 ${successRate}% - 部分域名异常 ⚠️`;
            type = 'warning';
        } else {
            message = `检测完成！成功率 ${successRate}% - 多数域名异常 ❌`;
            type = 'error';
        }
        
        this.showTestingToast(message, type);
        
        // 启用结果导出功能
        this.enableResultExport();
    }

    /**
     * 显示详细的测试结果
     */
    private showDetailedTestResults(): void {
        const { success, warning, error, total, averageResponseTime } = this.statistics;
        const successRate = total > 0 ? Math.round((success / total) * 100) : 0;
        
        // 创建详细结果弹窗
        const resultModal = this.createResultModal({
            total,
            success,
            warning,
            error,
            successRate,
            averageResponseTime,
            fastestDomain: this.getFastestDomain(),
            slowestDomain: this.getSlowestDomain(),
            failedDomains: this.getFailedDomains()
        });
        
        // 显示弹窗
        document.body.appendChild(resultModal);
        
        // 3秒后自动关闭（除非用户交互）
        setTimeout(() => {
            if (resultModal.parentNode) {
                resultModal.remove();
            }
        }, 8000);
    }

    /**
     * 添加测试完成的视觉效果
     */
    private addTestCompleteVisualEffects(): void {
        // 为成功的域名添加庆祝动画
        const successDomains = this.getAllDomains().filter(d => d.status === ConnectivityStatus.SUCCESS);
        successDomains.forEach((domain, index) => {
            setTimeout(() => {
                this.addCelebrationAnimation(domain);
            }, index * 100);
        });
        
        // 为整体界面添加完成效果
        const container = document.querySelector('.controls-container');
        if (container) {
            container.classList.add('animate-pulse');
            setTimeout(() => {
                container.classList.remove('animate-pulse');
            }, 1500);
        }
        
        // 更新进度条为完成状态
        const progressBar = document.getElementById('test-progress-bar');
        if (progressBar) {
            progressBar.style.background = 'linear-gradient(90deg, #10b981, #059669)';
            progressBar.classList.add('animate-pulse');
            setTimeout(() => {
                progressBar.classList.remove('animate-pulse');
            }, 2000);
        }
    }

    /**
     * 启用结果导出功能
     */
    private enableResultExport(): void {
        // 检查是否已存在导出按钮
        let exportBtn = document.getElementById('export-results-btn') as HTMLButtonElement;
        
        if (!exportBtn) {
            // 创建导出按钮
            exportBtn = document.createElement('button');
            exportBtn.id = 'export-results-btn';
            exportBtn.className = 'px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors duration-200 shadow-lg transform hover:scale-105';
            exportBtn.innerHTML = '📊 导出结果';
            
            // 添加到控制容器
            const controlsContainer = document.querySelector('.controls-container');
            if (controlsContainer) {
                controlsContainer.appendChild(exportBtn);
            }
        }
        
        // 绑定导出事件
        exportBtn.onclick = () => this.exportTestResults();
        exportBtn.disabled = false;
        exportBtn.style.display = 'inline-block';
    }

    /**
     * 移除全局测试动画
     */
    private removeGlobalTestAnimation(): void {
        const container = document.querySelector('.controls-container');
        if (container) {
            container.classList.remove('testing-active');
        }
        
        document.body.classList.remove('testing-mode');
    }

    /**
     * 重置所有域名状态
     */
    private resetAllDomainsStatus(domains: DomainInfo[]): void {
        domains.forEach(domain => {
            domain.status = ConnectivityStatus.PENDING;
            domain.responseTime = undefined;
            domain.errorMessage = undefined;
        });
        
        // 立即更新UI显示重置状态
        this.renderPlatforms();
        this.updateStatistics();
        this.updateProgressBar();
    }

    /**
     * 显示测试状态提示
     */
    private showTestingToast(message: string, type: 'success' | 'warning' | 'error' | 'info'): void {
        // 移除现有的提示
        const existingToast = document.querySelector('.testing-toast');
        if (existingToast) {
            existingToast.remove();
        }
        
        const toast = document.createElement('div');
        toast.className = `testing-toast fixed top-4 right-4 px-6 py-3 rounded-lg shadow-lg z-50 transform transition-all duration-300 translate-x-full`;
        
        let bgColor = '';
        let textColor = '';
        let icon = '';
        
        switch (type) {
            case 'success':
                bgColor = 'bg-green-500';
                textColor = 'text-white';
                icon = '<i class="fas fa-check-circle mr-2"></i>';
                break;
            case 'warning':
                bgColor = 'bg-yellow-500';
                textColor = 'text-white';
                icon = '<i class="fas fa-exclamation-triangle mr-2"></i>';
                break;
            case 'error':
                bgColor = 'bg-red-500';
                textColor = 'text-white';
                icon = '<i class="fas fa-times-circle mr-2"></i>';
                break;
            case 'info':
                bgColor = 'bg-blue-500';
                textColor = 'text-white';
                icon = '<i class="fas fa-info-circle mr-2"></i>';
                break;
        }
        
        toast.className += ` ${bgColor} ${textColor}`;
        toast.innerHTML = `${icon}${message}`;
        
        document.body.appendChild(toast);
        
        // 动画显示
        setTimeout(() => {
            toast.classList.remove('translate-x-full');
        }, 100);
        
        // 自动隐藏
        setTimeout(() => {
            toast.classList.add('translate-x-full');
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300);
        }, type === 'info' ? 2000 : 4000);
    }

    /**
     * 批处理域名测试（优化版本）
     */
    private async processDomainsBatch(domains: DomainInfo[]): Promise<void> {
        const { batchSize, batchDelay } = this.config;
        const totalBatches = Math.ceil(domains.length / batchSize);
        
        for (let i = 0; i < domains.length; i += batchSize) {
            if (this.abortController?.signal.aborted) {
                throw new Error('AbortError');
            }
            
            const batch = domains.slice(i, i + batchSize);
            const currentBatch = Math.floor(i / batchSize) + 1;
            
            // 更新批次进度提示
            this.updateBatchProgress(currentBatch, totalBatches, batch);
            
            // 为当前批次的域名添加测试开始动画
            batch.forEach(domain => {
                domain.status = ConnectivityStatus.TESTING;
                this.addTestStartAnimation(domain);
            });
            
            // 立即更新UI显示测试状态
            this.renderPlatforms();
            this.updateStatistics();
            this.updateProgressBar();
            
            // 并行处理当前批次
            await Promise.allSettled(
                batch.map(domain => this.testDomainWithRetry(domain))
            );
            
            // 为完成的域名添加完成动画
            batch.forEach(domain => {
                this.addTestCompleteAnimation(domain);
            });
            
            // 实时更新UI
            this.renderPlatforms();
            this.updateStatistics();
            this.updateProgressBar();
            
            // 显示批次完成状态
            this.showBatchCompleteStatus(currentBatch, totalBatches, batch);
            
            // 批次间延迟，避免过于频繁的请求
            if (i + batchSize < domains.length) {
                await this.delay(batchDelay);
            }
        }
    }

    /**
     * 更新批次进度
     */
    private updateBatchProgress(currentBatch: number, totalBatches: number, batch: DomainInfo[]): void {
        const progressText = document.getElementById('test-progress-text');
        if (progressText) {
            progressText.textContent = `批次 ${currentBatch}/${totalBatches} - 正在检测 ${batch.map(d => d.domain).join(', ')}`;
        }
    }

    /**
     * 显示批次完成状态
     */
    private showBatchCompleteStatus(currentBatch: number, totalBatches: number, batch: DomainInfo[]): void {
        const successCount = batch.filter(d => d.status === ConnectivityStatus.SUCCESS).length;
        const totalCount = batch.length;
        
        if (currentBatch < totalBatches) {
            // 不是最后一个批次，显示简短状态
            const progressText = document.getElementById('test-progress-text');
            if (progressText) {
                progressText.textContent = `批次 ${currentBatch}/${totalBatches} 完成 - ${successCount}/${totalCount} 成功`;
            }
        }
        
        // 添加批次完成的视觉反馈
        this.addBatchCompleteAnimation(currentBatch, totalBatches);
    }

    /**
     * 添加批次完成动画
     */
    private addBatchCompleteAnimation(currentBatch: number, totalBatches: number): void {
        const progressBar = document.getElementById('test-progress-bar');
        if (progressBar) {
            // 临时高亮进度条
            progressBar.classList.add('animate-pulse');
            setTimeout(() => {
                progressBar.classList.remove('animate-pulse');
            }, 500);
        }
        
        // 如果是最后一个批次，添加完成特效
        if (currentBatch === totalBatches) {
            const container = document.querySelector('.controls-container');
            if (container) {
                container.classList.add('animate-bounce');
                setTimeout(() => {
                    container.classList.remove('animate-bounce');
                }, 1000);
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
     * 测试单个域名连通性（优化版本）
     */
    private async testSingleDomain(domainInfo: DomainInfo): Promise<void> {
        // 添加测试开始的视觉反馈
        this.addTestStartAnimation(domainInfo);
        
        try {
            await this.testDomainWithRetry(domainInfo);
        } finally {
            // 添加测试完成的视觉反馈
            this.addTestCompleteAnimation(domainInfo);
            
            // 更新UI
            this.renderPlatforms();
            this.updateStatistics();
            this.updateProgressBar();
        }
    }

    /**
     * 添加测试开始动画效果
     */
    private addTestStartAnimation(domainInfo: DomainInfo): void {
        // 查找对应的域名元素
        const domainElements = document.querySelectorAll('[data-domain]');
        domainElements.forEach(element => {
            if (element.getAttribute('data-domain') === domainInfo.domain) {
                const parentElement = element.closest('.flex.items-center.justify-between');
                if (parentElement) {
                    // 添加测试中的动画类
                    parentElement.classList.add('animate-pulse', 'bg-blue-50');
                    
                    // 添加涟漪效果
                    this.createRippleEffect(parentElement as HTMLElement);
                }
            }
        });
    }

    /**
     * 添加测试完成动画效果
     */
    private addTestCompleteAnimation(domainInfo: DomainInfo): void {
        // 查找对应的域名元素
        const domainElements = document.querySelectorAll('[data-domain]');
        domainElements.forEach(element => {
            if (element.getAttribute('data-domain') === domainInfo.domain) {
                const parentElement = element.closest('.flex.items-center.justify-between');
                if (parentElement) {
                    // 移除测试中的动画类
                    parentElement.classList.remove('animate-pulse', 'bg-blue-50');
                    
                    // 根据结果添加完成动画
                    let animationClass = '';
                    switch (domainInfo.status) {
                        case ConnectivityStatus.SUCCESS:
                            animationClass = 'animate-bounce';
                            break;
                        case ConnectivityStatus.WARNING:
                            animationClass = 'animate-pulse';
                            break;
                        case ConnectivityStatus.ERROR:
                            animationClass = 'animate-shake';
                            break;
                    }
                    
                    if (animationClass) {
                        parentElement.classList.add(animationClass);
                        setTimeout(() => {
                            parentElement.classList.remove(animationClass);
                        }, 1000);
                    }
                }
            }
        });
    }

    /**
     * 创建涟漪效果
     */
    private createRippleEffect(element: HTMLElement): void {
        const ripple = document.createElement('div');
        ripple.className = 'absolute inset-0 bg-blue-400 opacity-20 rounded-lg animate-ping pointer-events-none';
        
        element.style.position = 'relative';
        element.appendChild(ripple);
        
        setTimeout(() => {
            if (ripple.parentNode) {
                ripple.parentNode.removeChild(ripple);
            }
        }, 1000);
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
        const testBtn = document.getElementById('test-all-btn') as any;
        const refreshBtn = document.getElementById('refresh-btn') as any;

        if (testBtn && testBtn.__onClick) {
            testBtn.removeEventListener('click', testBtn.__onClick);
            delete testBtn.__onClick;
        }
        if (refreshBtn && refreshBtn.__onClick) {
            refreshBtn.removeEventListener('click', refreshBtn.__onClick);
            delete refreshBtn.__onClick;
        }
    }

    /**
     * 延迟函数
     */
    private delay(ms: number): Promise<void> {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * 获取所有域名
     */
    private getAllDomains(): DomainInfo[] {
        const allDomains: DomainInfo[] = [];
        this.platforms.forEach(platform => {
            allDomains.push(...platform.domains);
        });
        return allDomains;
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
        // 重置统计数据
        this.statistics = {
            total: 0,
            success: 0,
            warning: 0,
            error: 0,
            testing: 0,
            pending: 0,
            successRate: 0,
            averageResponseTime: 0,
            lastUpdateTime: new Date()
        };

        let totalResponseTime = 0;
        let responseTimeCount = 0;

        // 统计各种状态的域名数量
        this.platforms.forEach(platform => {
            platform.domains.forEach(domain => {
                this.statistics.total++;
                switch (domain.status) {
                    case ConnectivityStatus.SUCCESS:
                        this.statistics.success++;
                        if (domain.responseTime) {
                            totalResponseTime += domain.responseTime;
                            responseTimeCount++;
                        }
                        break;
                    case ConnectivityStatus.WARNING:
                        this.statistics.warning++;
                        if (domain.responseTime) {
                            totalResponseTime += domain.responseTime;
                            responseTimeCount++;
                        }
                        break;
                    case ConnectivityStatus.ERROR:
                        this.statistics.error++;
                        break;
                    case ConnectivityStatus.TESTING:
                        this.statistics.testing++;
                        break;
                    case ConnectivityStatus.PENDING:
                        this.statistics.pending++;
                        break;
                }
            });
        });

        // 计算成功率
        if (this.statistics.total > 0) {
            const testedCount = this.statistics.total - this.statistics.pending - this.statistics.testing;
            if (testedCount > 0) {
                this.statistics.successRate = Math.round(
                    ((this.statistics.success + this.statistics.warning) / testedCount) * 100
                );
            }
        }

        // 计算平均响应时间
        if (responseTimeCount > 0) {
            this.statistics.averageResponseTime = Math.round(totalResponseTime / responseTimeCount);
        }

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

        // 更新基础统计数字
        Object.entries(elements).forEach(([key, element]) => {
            if (element) {
                const value = this.statistics[key as keyof Statistics];
                element.textContent = value?.toString() || '0';
                
                // 添加动画效果
                element.classList.add('animate-pulse');
                setTimeout(() => {
                    element.classList.remove('animate-pulse');
                }, 300);
            }
        });

        // 同步更新顶部精简总计（仅数字）
        const headerTotalElement = document.getElementById('total-count-header');
        if (headerTotalElement) {
            headerTotalElement.textContent = (this.statistics.total || 0).toString();
            headerTotalElement.classList.add('animate-pulse');
            setTimeout(() => {
                headerTotalElement.classList.remove('animate-pulse');
            }, 300);
        }

        // 更新成功率显示
        const successRateElement = document.getElementById('success-rate');
        if (successRateElement) {
            successRateElement.textContent = `${this.statistics.successRate}%`;
            
            // 根据成功率设置颜色
            successRateElement.className = 'font-bold text-lg';
            if (this.statistics.successRate >= 90) {
                successRateElement.classList.add('text-green-600');
            } else if (this.statistics.successRate >= 70) {
                successRateElement.classList.add('text-yellow-600');
            } else {
                successRateElement.classList.add('text-red-600');
            }
        }

        // 更新平均响应时间
        const avgResponseElement = document.getElementById('avg-response-time');
        if (avgResponseElement) {
            if (this.statistics.averageResponseTime > 0) {
                avgResponseElement.textContent = `${this.statistics.averageResponseTime}ms`;
                
                // 根据响应时间设置颜色
                avgResponseElement.className = 'font-bold text-lg';
                if (this.statistics.averageResponseTime <= 1000) {
                    avgResponseElement.classList.add('text-green-600');
                } else if (this.statistics.averageResponseTime <= 3000) {
                    avgResponseElement.classList.add('text-yellow-600');
                } else {
                    avgResponseElement.classList.add('text-red-600');
                }
            } else {
                avgResponseElement.textContent = '--';
                avgResponseElement.className = 'font-bold text-lg text-gray-400';
            }
        }

        // 更新最后更新时间
        const lastUpdateElement = document.getElementById('last-update-time');
        if (lastUpdateElement && this.statistics.lastUpdateTime) {
            const timeStr = this.statistics.lastUpdateTime.toLocaleTimeString('zh-CN');
            lastUpdateElement.innerHTML = `<i class="fas fa-clock mr-1"></i>最后更新: ${timeStr}`;
        }

        // 更新进度条
        this.updateProgressBar();
    }

    /**
     * 更新进度条
     */
    private updateProgressBar(): void {
        const progressBarElement = document.getElementById('test-progress-bar');
        const progressTextElement = document.getElementById('test-progress-text');
        
        if (progressBarElement && progressTextElement) {
            const testedCount = this.statistics.total - this.statistics.pending;
            const progressPercentage = this.statistics.total > 0 ? 
                Math.round((testedCount / this.statistics.total) * 100) : 0;
            
            // 更新进度条
            progressBarElement.style.width = `${progressPercentage}%`;
            progressTextElement.textContent = `${testedCount}/${this.statistics.total} (${progressPercentage}%)`;
            
            // 根据进度设置颜色
            if (progressPercentage === 100) {
                progressBarElement.className = 'h-full bg-green-500 rounded-full transition-all duration-300';
            } else if (this.statistics.testing > 0) {
                progressBarElement.className = 'h-full bg-blue-500 rounded-full transition-all duration-300';
            } else {
                progressBarElement.className = 'h-full bg-gray-400 rounded-full transition-all duration-300';
            }
        }
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
                const warningCount = platform.domains.filter(d => d.status === ConnectivityStatus.WARNING).length;
                const errorCount = platform.domains.filter(d => d.status === ConnectivityStatus.ERROR).length;
                const testingCount = platform.domains.filter(d => d.status === ConnectivityStatus.TESTING).length;
                const totalCount = platform.domains.length;
                
                // 更新平台特定的统计显示
                const platformElement = document.querySelector(`[data-platform="${name}"]`);
                if (platformElement) {
                    const statsElement = platformElement.querySelector('.platform-stats');
                    if (statsElement) {
                        if (testingCount > 0) {
                            statsElement.innerHTML = `<i class="fas fa-spinner fa-spin mr-1"></i>检测中... ${testingCount}/${totalCount}`;
                            statsElement.className = 'platform-stats text-blue-600 font-medium';
                        } else {
                            const availableCount = successCount + warningCount;
                            const successRate = totalCount > 0 ? Math.round((availableCount / totalCount) * 100) : 0;
                            
                            statsElement.textContent = `${availableCount}/${totalCount} 可用 (${successRate}%)`;
                            
                            // 根据成功率设置颜色
                            if (successRate >= 90) {
                                statsElement.className = 'platform-stats text-green-600 font-medium';
                            } else if (successRate >= 70) {
                                statsElement.className = 'platform-stats text-yellow-600 font-medium';
                            } else {
                                statsElement.className = 'platform-stats text-red-600 font-medium';
                            }
                        }
                    }
                    
                    // 添加平台状态指示器
                    const indicatorElement = platformElement.querySelector('.platform-indicator');
                    if (indicatorElement) {
                        if (testingCount > 0) {
                            indicatorElement.className = 'platform-indicator w-3 h-3 rounded-full bg-blue-500 animate-pulse';
                        } else if (errorCount === totalCount) {
                            indicatorElement.className = 'platform-indicator w-3 h-3 rounded-full bg-red-500';
                        } else if (successCount === totalCount) {
                            indicatorElement.className = 'platform-indicator w-3 h-3 rounded-full bg-green-500';
                        } else {
                            indicatorElement.className = 'platform-indicator w-3 h-3 rounded-full bg-yellow-500';
                        }
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
                const testingCount = this.statistics.testing;
                const totalCount = this.statistics.total;
                const progressText = totalCount > 0 ? ` (${testingCount}/${totalCount})` : '';
                
                button.innerHTML = `<i class="fas fa-stop mr-2"></i>停止测试${progressText}`;
                button.className = 'px-6 py-3 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-all duration-200 font-medium shadow-lg transform hover:scale-105';
                button.disabled = false;
            } else {
                const hasResults = this.statistics.success + this.statistics.warning + this.statistics.error > 0;
                const buttonText = hasResults ? '重新测试' : '开始测试';
                const iconClass = hasResults ? 'fas fa-redo' : 'fas fa-play';
                
                button.innerHTML = `<i class="${iconClass} mr-2"></i>${buttonText}`;
                button.className = 'px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-all duration-200 font-medium shadow-lg transform hover:scale-105';
                button.disabled = false;
            }
        }
        
        // 更新按钮容器的状态指示
        this.updateButtonContainerStatus(isTesting);
    }

    /**
     * 更新按钮容器状态
     */
    private updateButtonContainerStatus(isTesting: boolean): void {
        const container = document.querySelector('.controls-container');
        if (container) {
            if (isTesting) {
                container.classList.add('testing-active');
            } else {
                container.classList.remove('testing-active');
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
     * 获取最快的域名
     */
    private getFastestDomain(): { domain: string; responseTime: number } | null {
        const allDomains = this.getAllDomains();
        const successDomains = allDomains.filter(d => 
            d.status === ConnectivityStatus.SUCCESS && d.responseTime !== undefined
        );
        
        if (successDomains.length === 0) return null;
        
        const fastest = successDomains.reduce((prev: DomainInfo, current: DomainInfo) => 
            (prev.responseTime! < current.responseTime!) ? prev : current
        );
        
        return { domain: fastest.domain, responseTime: fastest.responseTime! };
    }

    /**
     * 获取最慢的域名
     */
    private getSlowestDomain(): { domain: string; responseTime: number } | null {
        const allDomains = this.getAllDomains();
        const successDomains = allDomains.filter(d => 
            d.status === ConnectivityStatus.SUCCESS && d.responseTime !== undefined
        );
        
        if (successDomains.length === 0) return null;
        
        const slowest = successDomains.reduce((prev: DomainInfo, current: DomainInfo) => 
            (prev.responseTime! > current.responseTime!) ? prev : current
        );
        
        return { domain: slowest.domain, responseTime: slowest.responseTime! };
    }

    /**
     * 获取失败的域名列表
     */
    private getFailedDomains(): string[] {
        const allDomains = this.getAllDomains();
        return allDomains
            .filter((d: DomainInfo) => d.status === ConnectivityStatus.ERROR)
            .map((d: DomainInfo) => d.domain);
    }

    /**
     * 创建结果详情弹窗
     */
    private createResultModal(data: {
        total: number;
        success: number;
        warning: number;
        error: number;
        successRate: number;
        averageResponseTime: number;
        fastestDomain: { domain: string; responseTime: number } | null;
        slowestDomain: { domain: string; responseTime: number } | null;
        failedDomains: string[];
    }): HTMLElement {
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 animate-fadeInUp';
        
        const content = document.createElement('div');
        content.className = 'bg-white rounded-lg p-6 max-w-md w-full mx-4 shadow-2xl transform transition-all duration-300';
        
        content.innerHTML = `
            <div class="flex justify-between items-center mb-4">
                <h3 class="text-xl font-bold text-gray-800">📊 检测结果详情</h3>
                <button class="text-gray-500 hover:text-gray-700 text-xl" onclick="this.closest('.fixed').remove()">×</button>
            </div>
            
            <div class="space-y-4">
                <div class="grid grid-cols-2 gap-4">
                    <div class="text-center p-3 bg-green-50 rounded-lg">
                        <div class="text-2xl font-bold text-green-600">${data.success}</div>
                        <div class="text-sm text-green-700">成功</div>
                    </div>
                    <div class="text-center p-3 bg-yellow-50 rounded-lg">
                        <div class="text-2xl font-bold text-yellow-600">${data.warning}</div>
                        <div class="text-sm text-yellow-700">警告</div>
                    </div>
                    <div class="text-center p-3 bg-red-50 rounded-lg">
                        <div class="text-2xl font-bold text-red-600">${data.error}</div>
                        <div class="text-sm text-red-700">失败</div>
                    </div>
                    <div class="text-center p-3 bg-blue-50 rounded-lg">
                        <div class="text-2xl font-bold text-blue-600">${data.successRate}%</div>
                        <div class="text-sm text-blue-700">成功率</div>
                    </div>
                </div>
                
                <div class="border-t pt-4">
                    <div class="text-sm text-gray-600 space-y-2">
                        <div>平均响应时间: <span class="font-semibold">${data.averageResponseTime}ms</span></div>
                        ${data.fastestDomain ? `<div>最快域名: <span class="font-semibold text-green-600">${data.fastestDomain.domain}</span> (${data.fastestDomain.responseTime}ms)</div>` : ''}
                        ${data.slowestDomain ? `<div>最慢域名: <span class="font-semibold text-yellow-600">${data.slowestDomain.domain}</span> (${data.slowestDomain.responseTime}ms)</div>` : ''}
                        ${data.failedDomains.length > 0 ? `<div>失败域名: <span class="font-semibold text-red-600">${data.failedDomains.join(', ')}</span></div>` : ''}
                    </div>
                </div>
                
                <div class="flex justify-end space-x-2 pt-4 border-t">
                    <button onclick="this.closest('.fixed').remove()" class="px-4 py-2 text-gray-600 hover:text-gray-800 transition-colors">关闭</button>
                    <button onclick="window.connectivityChecker.exportTestResults()" class="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 transition-colors">导出结果</button>
                </div>
            </div>
        `;
        
        modal.appendChild(content);
        return modal;
    }

    /**
     * 添加庆祝动画
     */
    private addCelebrationAnimation(domain: DomainInfo): void {
        const domainElement = document.querySelector(`[data-domain="${domain.domain}"]`);
        if (domainElement) {
            domainElement.classList.add('animate-bounce');
            setTimeout(() => {
                domainElement.classList.remove('animate-bounce');
            }, 1000);
        }
    }

    /**
     * 导出测试结果
     */
    private exportTestResults(): void {
        const allDomains = this.getAllDomains();
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        
        const results = {
            timestamp: new Date().toISOString(),
            statistics: this.statistics,
            domains: allDomains.map((domain: DomainInfo) => ({
                platform: this.getPlatformForDomain(domain.domain),
                domain: domain.domain,
                status: domain.status,
                responseTime: domain.responseTime,
                errorMessage: domain.errorMessage
            }))
        };
        
        // 创建并下载JSON文件
        const blob = new Blob([JSON.stringify(results, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `connectivity-test-results-${timestamp}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        // 显示导出成功提示
        this.showTestingToast('结果已导出到下载文件夹 📁', 'success');
    }

    /**
     * 获取域名所属平台
     */
    private getPlatformForDomain(domain: string): string {
        for (const [platformName, platformData] of Object.entries(this.platforms)) {
            if (platformData.domains.some((d: DomainInfo) => d.domain === domain)) {
                return platformName;
            }
        }
        return 'Unknown';
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

// 初始化应用（兜底方法）
function initChecker() {
    // 避免在开发模式/HMR下重复初始化
    if (!(window as any).connectivityChecker) {
        const checker = new HostsConnectivityChecker();
        // 将实例暴露到全局，以便弹窗中的按钮可以调用
        (window as any).connectivityChecker = checker;
    }
}

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
import { createApp } from 'vue';
import App from './App.vue';

// 先挂载 Vue 应用，确保 DOM 节点就绪
const app = createApp(App);
app.mount('#app');

// 根据文档加载状态初始化检查器，确保节点已就绪
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initChecker);
} else {
    initChecker();
}

// 在开发模式下处理 HMR：释放旧实例与事件，避免失效绑定与资源泄漏
if (import.meta && (import.meta as any).hot) {
    (import.meta as any).hot.dispose(() => {
        const w: any = window as any;
        const checker = w.connectivityChecker;
        if (checker && typeof checker.destroy === 'function') {
            try {
                checker.destroy();
            } catch (_) {
                // ignore
            }
        }
        delete w.connectivityChecker;
    });
}