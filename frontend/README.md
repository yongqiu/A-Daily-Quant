# A股量化策略监控平台 - 前端

基于 Vue 3 + Vite + Tailwind CSS 的现代化前端项目。

## 技术栈

- **Vue 3** - 渐进式 JavaScript 框架
- **Vite** - 下一代前端构建工具
- **Vue Router** - 官方路由管理器
- **Pinia** - Vue 官方状态管理库
- **Tailwind CSS** - 实用优先的 CSS 框架
- **ECharts** - 强大的图表库
- **Axios** - HTTP 客户端
- **Marked** - Markdown 解析器

## 项目结构

```
frontend/
├── src/
│   ├── assets/           # 静态资源 (样式、图片等)
│   │   └── styles/
│   │       └── main.css  # 全局样式
│   ├── components/       # 可复用组件
│   │   ├── AppHeader.vue
│   │   └── AddHoldingModal.vue
│   ├── composables/      # 组合式函数
│   │   └── useKlineChart.js
│   ├── router/           # 路由配置
│   │   └── index.js
│   ├── stores/           # Pinia 状态管理
│   │   ├── market.js
│   │   └── strategy.js
│   ├── utils/            # 工具函数
│   │   └── api.js
│   ├── views/            # 页面组件
│   │   ├── DashboardView.vue
│   │   └── StrategiesView.vue
│   ├── App.vue           # 根组件
│   └── main.js           # 入口文件
├── index.html            # HTML 模板
├── package.json          # 项目配置
├── vite.config.js        # Vite 配置
├── tailwind.config.js    # Tailwind CSS 配置
└── postcss.config.js     # PostCSS 配置
```

## 开发指南

### 安装依赖

```bash
cd frontend
npm install
```

### 开发模式

```bash
npm run dev
```

前端开发服务器将在 `http://localhost:5173` 启动，并自动代理 API 请求到后端服务器 (`http://localhost:8100`)。

### 构建生产版本

```bash
npm run build
```

构建产物将输出到 `dist/` 目录。

### 预览生产构建

```bash
npm run preview
```

## 样式系统

### 颜色变量

项目使用自定义的 CSS 变量系统，在 `tailwind.config.js` 中定义：

- `navy-deep/mid/light` - 深蓝背景色
- `electric-blue` - 电光蓝主色调
- `gold-primary` - 金色强调色
- `up/down` - A股涨跌色

### 组件类名

- `.glass-card` - 玻璃态卡片
- `.gold-accent-card` - 金色强调卡片
- `.btn-primary` - 主按钮
- `.btn-gold` - 金色按钮
- `.btn-secondary` - 次要按钮
- `.status-indicator` - 状态指示器
- `.badge` - 徽章
- `.input-modern` - 现代化输入框

## API 通信

所有 API 请求通过 `@/utils/api.js` 统一管理：

```javascript
import { apiMethods } from '@/utils/api'

// 获取市场状态
const status = await apiMethods.getStatus()

// 切换监控状态
await apiMethods.toggleMonitor()

// AI 分析流式响应
await apiMethods.analyzeStockStream(
  symbol,
  'multi_agent',
  (data) => console.log('进度:', data),
  (data) => console.log('完成:', data),
  (error) => console.error('错误:', error)
)
```

## 状态管理

使用 Pinia 进行全局状态管理：

### Market Store

```javascript
import { useMarketStore } from '@/stores/market'

const marketStore = useMarketStore()
await marketStore.fetchStatus()
marketStore.toggleMonitor()
```

### Strategy Store

```javascript
import { useStrategyStore } from '@/stores/strategy'

const strategyStore = useStrategyStore()
await strategyStore.fetchStrategies()
```

## 部署说明

1. 构建前端项目：
   ```bash
   npm run build
   ```

2. 后端服务器会自动检测 `frontend/dist/` 目录是否存在：
   - 如果存在，使用 Vue 构建后的静态文件
   - 如果不存在，使用传统的 Jinja2 模板

3. 启动后端服务器：
   ```bash
   python web_server.py
   ```

## 注意事项

- 确保后端 API 服务器在 `http://localhost:8100` 运行
- 开发模式下，Vite 会自动代理 API 请求
- 生产构建后，需要配置 Nginx 或其他反向代理将 API 请求转发到后端
