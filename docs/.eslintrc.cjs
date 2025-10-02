module.exports = {
  root: true,
  env: {
    browser: true,
    es2021: true,
    node: true,
  },
  parser: 'vue-eslint-parser',
  parserOptions: {
    parser: '@typescript-eslint/parser',
    ecmaVersion: 'latest',
    sourceType: 'module',
  },
  extends: [
    'plugin:vue/vue3-recommended',
    'plugin:@typescript-eslint/recommended',
    'eslint:recommended',
    'prettier',
  ],
  plugins: ['vue', '@typescript-eslint'],
  ignorePatterns: ['dist', 'node_modules', '.vite'],
  rules: {
    // 允许单词组件名（如 App）
    'vue/multi-word-component-names': 'off',
    // 使用 TS 版本的未使用变量规则，并忽略下划线前缀
    'no-unused-vars': 'off',
    '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_', ignoreRestSiblings: true }],
    // 允许在特定场景使用 any（如 HMR/全局对象）
    '@typescript-eslint/no-explicit-any': 'off',
    // 允许在类型声明中使用 {}（兼容 Vue 声明文件）
    '@typescript-eslint/ban-types': 'off',
    // 由 TS 负责未定义标识符检查
    'no-undef': 'off',
  },
};