<template>
  <div class="bg-white rounded-xl shadow-lg p-6 mb-8 controls-container">
    <div class="flex flex-col md:flex-row items-center justify-between gap-4 mb-4">
      <div class="flex gap-3">
        <button id="test-all-btn" class="px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-all duration-200 font-medium shadow-lg transform hover:scale-105">
          <i class="fas fa-play mr-2"></i>开始测试
        </button>
        <button id="refresh-btn" class="px-6 py-3 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-all duration-200 font-medium shadow-lg transform hover:scale-105">
          <i class="fas fa-sync-alt mr-2"></i>刷新页面
        </button>
      </div>
      <div class="flex flex-col md:flex-row gap-4 text-sm text-gray-600">
        <span id="last-update-time" class="flex items-center">
          <i class="fas fa-clock mr-1"></i>最后更新: --
        </span>
        <span class="flex items-center">
          <i class="fas fa-list mr-1"></i>
          <span id="total-count-header" class="ml-1 font-semibold">--</span>
        </span>
      </div>
    </div>
    <!-- Progress Bar -->
    <div class="bg-gray-200 rounded-full h-3 mb-2 overflow-hidden">
      <div id="test-progress-bar" class="h-full bg-gray-400 rounded-full transition-all duration-300" style="width: 0%"></div>
    </div>
    <div class="flex justify-between items-center text-xs text-gray-500">
      <span id="test-progress-text">0/0 (0%)</span>
      <div class="flex gap-4">
        <span class="flex items-center">
          <span class="w-2 h-2 bg-green-500 rounded-full mr-1"></span>成功率: <span id="success-rate" class="ml-1 font-bold">--%</span>
        </span>
        <span class="flex items-center">
          <span class="w-2 h-2 bg-blue-500 rounded-full mr-1"></span>平均响应: <span id="avg-response-time" class="ml-1 font-bold">--</span>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// 为保持与现有 TS 逻辑兼容，保留元素 ID 与类名
</script>

<style scoped>
</style>