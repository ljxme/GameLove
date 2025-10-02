/**
 * 组合多个 AbortSignal 为一个新的可中止信号。
 * 任一输入信号中止，输出信号即中止。
 */
/**
 * combineAbortSignals
 * 将多个 `AbortSignal` 合并成一个新信号：任一输入信号触发 `abort` 时，新信号同步中止。
 * 用途：
 * - 批量任务：全局取消 + 单任务超时组合
 * - UI 交互：按钮取消与路由切换同时可中止
 * 注意：
 * - 若输入数组中存在已中止的信号，则新信号立即中止。
 */
export function combineAbortSignals(signals: AbortSignal[]): AbortSignal {
  const controller = new AbortController();
  for (const signal of signals) {
    if (!signal) continue;
    if (signal.aborted) {
      controller.abort();
    } else {
      signal.addEventListener('abort', () => controller.abort());
    }
  }
  return controller.signal;
}
