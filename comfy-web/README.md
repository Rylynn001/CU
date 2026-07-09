# Comfy Web

Comfy Web 是一个基于 Vue 3、TypeScript 和 Vite 的 ComfyUI 前端工作台，包含图片生成、视频生成、资产管理和导演台等页面。

## 环境

- Node.js：使用本机已安装版本
- 包管理器：npm
- ComfyUI 默认地址：`127.0.0.1:8188`

## 常用命令

```bash
npm install
npm run dev
npm run type-check
npm run build
```

## 目录说明

- `src/api`：后端接口封装
- `src/components`：可复用组件
- `src/composables`：组合式业务逻辑
- `src/router`：前端路由
- `src/services`：跨接口的业务服务
- `src/styles`：全局样式和共享页面样式
- `src/views`：路由页面

## 验证

提交前建议至少执行：

```bash
npm run check
```
