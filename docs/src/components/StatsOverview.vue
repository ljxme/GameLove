<template>
  <div class="grid grid-cols-1 md:grid-cols-5 gap-4 mb-8">
    <div class="bg-white rounded-lg shadow-md p-4 border-l-4 border-gray-400">
      <div class="flex items-center justify-between">
        <div>
          <div class="text-2xl font-bold text-gray-700" id="total-count">--</div>
          <div class="text-sm text-gray-600">总计</div>
        </div>
        <i class="fas fa-list text-2xl text-gray-400"></i>
      </div>
    </div>
    <div class="bg-white rounded-lg shadow-md p-4 border-l-4 border-green-500">
      <div class="flex items-center justify-between">
        <div>
          <div class="text-2xl font-bold text-green-600" id="success-count">--</div>
          <div class="text-sm text-gray-600">连通正常</div>
        </div>
        <i class="fas fa-check-circle text-2xl text-green-500"></i>
      </div>
    </div>
    <div class="bg-white rounded-lg shadow-md p-4 border-l-4 border-yellow-500">
      <div class="flex items-center justify-between">
        <div>
          <div class="text-2xl font-bold text-yellow-600" id="warning-count">--</div>
          <div class="text-sm text-gray-600">响应较慢</div>
        </div>
        <i class="fas fa-exclamation-triangle text-2xl text-yellow-500"></i>
      </div>
    </div>
    <div class="bg-white rounded-lg shadow-md p-4 border-l-4 border-red-500">
      <div class="flex items-center justify-between">
        <div>
          <div class="text-2xl font-bold text-red-600" id="error-count">--</div>
          <div class="text-sm text-gray-600">连接失败</div>
        </div>
        <i class="fas fa-times-circle text-2xl text-red-500"></i>
      </div>
    </div>
    <div class="bg-white rounded-lg shadow-md p-4 border-l-4 border-blue-500">
      <div class="flex items-center justify-between">
        <div>
          <div class="text-2xl font-bold text-blue-600" id="testing-count">--</div>
          <div class="text-sm text-gray-600">检测中</div>
        </div>
        <i class="fas fa-spinner text-2xl text-blue-500"></i>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// 保持 ID 以兼容 main.ts 的 UI 更新逻辑
</script>

<style scoped>
</style>