/**
 * 类型与扩展接口定义
 * 目标：统一数据结构，提升可维护性与可扩展性
 */

// 连通性状态枚举
export enum ConnectivityStatus {
  PENDING = 'pending',
  TESTING = 'testing',
  SUCCESS = 'success',
  WARNING = 'warning',
  ERROR = 'error',
}

// 域名信息
export interface DomainInfo {
  domain: string;
  status: ConnectivityStatus;
  responseTime?: number;
  lastChecked?: Date;
  retryCount?: number;
  errorMessage?: string;
}

// 平台信息
export interface PlatformInfo {
  name: string;
  domains: DomainInfo[];
  icon: string;
  color: string;
}

// 统计信息
export interface Statistics {
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

// 检测配置
export interface TestConfig {
  timeout: number;
  maxRetries: number;
  batchSize: number;
  batchDelay: number;
  fastTimeout: number;
  slowTimeout: number;
}

// hosts.json 结构（简化版，适配当前项目）
export type HostsJson = {
  urls?: {
    hosts_file?: string;
    json_api?: string;
  };
  platforms: Record<
    string,
    {
      domains: Array<string | { domain: string }>;
    }
  >;
};

// 预留扩展：数据源接口（便于切换不同来源）
export interface IHostsDataSource {
  load(): Promise<HostsJson>;
}

// 预留扩展：连通性测试策略接口（便于替换不同实现）
export interface IConnectivityTester {
  test(domain: string, signal: AbortSignal): Promise<void>;
}

// 性能监控配置
export interface PerformanceConfig {
  enableMemoryMonitoring: boolean;
  memoryCheckInterval: number;
  maxMemoryUsage: number; // MB
  enablePerformanceLogging: boolean;
}
