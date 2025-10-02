<template>
  <footer class="mt-12 text-center text-gray-600">
    <div class="bg-white rounded-xl shadow-game p-6">
      <p class="mb-2">
        <a
          href="https://github.com/artemisia1107/GameLove"
          target="_blank"
          class="text-game-primary hover:text-indigo-700 transition-colors"
        >
          <i class="fab fa-github mr-1"></i>GameLove Hosts 项目
        </a>
        <span class="mx-2">|</span>
        <a
          href="https://raw.githubusercontent.com/artemisia1107/GameLove/main/hosts"
          target="_blank"
          class="text-game-primary hover:text-indigo-700 transition-colors"
        >
          <i class="fas fa-download mr-1"></i>下载 Hosts 文件
        </a>
      </p>
      <p class="text-sm text-gray-500">
        <i class="fas fa-info-circle mr-1"></i>
        提示：此工具仅检测域名的HTTP连通性，实际游戏连接可能需要其他端口和协议
      </p>
    </div>
  </footer>
</template>

<script setup lang="ts">
// 纯展示组件
</script>

<style scoped></style>
