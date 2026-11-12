# 第三方代码说明

创作画布使用 Vue Flow，并参考、改编 Toonflow 的节点端口协议、连接校验与节点卡片交互布局。画布存储、资产 ID 引用和现有生成接口的适配由本项目实现。未引入 Toonflow 的文件系统、插件运行时及服务端。

来源：https://github.com/HBAI-Ltd/Toonflow-app

本地参考目录：`Toonflow-app-master/packages/nodeScaffold/src/connection.ts`、`nodeSkeleton.vue` 及 `apps/web/src/pages/workspace/panels/canvas/index.vue`。

MIT License

Copyright (c) 2026 HBAI-Ltd

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
