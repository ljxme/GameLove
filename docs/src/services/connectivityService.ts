/**
 * ConnectivityTester
 * 负责执行域名连通性测试的具体网络请求逻辑。
 * - 提供多种请求方法以提高检测准确性
 * - 作为策略实现，符合 IConnectivityTester 接口
 */
import { IConnectivityTester } from '../types';

export class ConnectivityTester implements IConnectivityTester {
  /**
   * 执行域名连通性测试
   * - 在浏览器的 `no-cors` 模式下，请求通常无法读取响应体/状态码，但能反映网络可达性。
   * - 策略：依次尝试 HEAD、GET `/favicon.ico`、GET 根路径，任一成功即判定为可达。
   * - 注意：即使返回浏览器层面的 `TypeError`，也可能是可达但受 CORS 或 HTTPS 限制；上层应结合耗时进行判定。
   *
   * 参数：
   *  - `domain`: 待测试的域名（不含协议，如 `example.com`）
   *  - `signal`: 用于取消请求的 AbortSignal（支持批量取消/超时）
   *
   * 异常：
   *  - 若所有测试方法都失败，则抛出最后一个错误，上层需根据耗时与错误类型进行解释性处理。
   */
  async test(domain: string, signal: AbortSignal): Promise<void> {
    const testMethods = this.buildTestMethods(domain, signal);

    try {
      // 尝试第一种方法（HEAD）
      await testMethods[0]();
      return;
    } catch (error) {
      // 如果第一种方法失败，依次尝试其他方法
      let lastError: unknown = error;
      for (let i = 1; i < testMethods.length; i++) {
        try {
          await testMethods[i]();
          return; // 任一方法成功即认为可达
        } catch (e) {
          lastError = e;
        }
      }
      throw lastError;
    }
  }

  /**
   * 构建多种检测方法（HEAD / GET favicon / GET 根路径）
   * - 目的：提升在各种服务配置下的覆盖率（部分站点仅 HEAD 可达，部分需要 GET）。
   * - `no-cors`: 保证请求能发出，忽略跨域限制，结合上层耗时与错误处理进行状态推断。
   */
  private buildTestMethods(domain: string, signal: AbortSignal): Array<() => Promise<Response>> {
    const base = `https://${domain}`;
    const commonInit: RequestInit = {
      mode: 'no-cors',
      signal,
      cache: 'no-cache',
    };

    return [
      () => fetch(base, { ...commonInit, method: 'HEAD' }),
      () => fetch(`${base}/favicon.ico`, { ...commonInit, method: 'GET' }),
      () => fetch(base, { ...commonInit, method: 'GET' }),
    ];
  }
}

export default ConnectivityTester;
