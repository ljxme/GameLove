import type { PerformanceConfig } from '../types';

/**
 * 性能监控工具
 * - 记录简单的性能计时
 * - 可选的内存占用检查（浏览器环境有限）
 */
export class PerformanceMonitor {
  private config: PerformanceConfig;
  private memoryCheckTimer?: number;
  private performanceEntries: Map<string, number> = new Map();

  constructor(config: PerformanceConfig) {
    this.config = config;
    if (config.enableMemoryMonitoring) {
      this.startMemoryMonitoring();
    }
  }

  startMeasure(name: string): void {
    this.performanceEntries.set(name, performance.now());
  }

  endMeasure(name: string): number {
    const start = this.performanceEntries.get(name) || performance.now();
    const duration = performance.now() - start;
    this.performanceEntries.delete(name);
    if (this.config.enablePerformanceLogging) {
      // eslint-disable-next-line no-console
      console.log(`[Perf] ${name}: ${Math.round(duration)} ms`);
    }
    return duration;
  }

  private startMemoryMonitoring(): void {
    if (typeof (performance as any).memory === 'undefined') return;
    this.memoryCheckTimer = window.setInterval(
      () => this.checkMemoryUsage(),
      this.config.memoryCheckInterval
    );
  }

  private checkMemoryUsage(): void {
    const perf: any = performance as any;
    const mem = perf.memory;
    if (!mem) return;
    const usedMB = mem.usedJSHeapSize / 1024 / 1024;
    if (usedMB > this.config.maxMemoryUsage) {
      this.triggerGarbageCollection();
    }
  }

  private triggerGarbageCollection(): void {
    // 浏览器无直接 GC 接口，尝试释放引用
    this.performanceEntries.clear();
  }

  destroy(): void {
    if (this.memoryCheckTimer) {
      clearInterval(this.memoryCheckTimer);
      this.memoryCheckTimer = undefined;
    }
    this.performanceEntries.clear();
  }
}
