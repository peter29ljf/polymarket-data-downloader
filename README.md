# Polymarket Trader

基于 Polymarket CLOB API 的自动化交易系统，提供 **Web UI**、**REST API** 和 **MCP 智能体工具** 三种使用方式。

---

## 目录

- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [REST API 文档](#rest-api-文档)
- [MCP 工具文档](#mcp-工具文档)
- [滑点保护机制](#滑点保护机制)

---

## 快速开始

### 环境要求

- Python 3.12+
- Polygon 钱包（已在 Polymarket 完成 KYC）

### 安装与启动

```bash
cd poly-trader
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python main.py
```

启动后：
- **Web UI**：http://localhost:8000
- **REST API**：http://localhost:8000/api/...
- **MCP SSE**：http://localhost:8001/sse

---

## 配置说明

### 凭据文件 `data/.env`

首次使用需要配置钱包凭据。可通过 Web UI 的「配置」页面自动生成，也可手动创建：

```ini
CLOB_API_KEY=your-api-key
CLOB_SECRET=your-api-secret
CLOB_PASS_PHRASE=your-passphrase
PRIVATE_KEY=your-private-key-hex         # 不含 0x 前缀
WALLET_ADDRESS=0xYourWalletAddress
CLOB_HOST=https://clob.polymarket.com
```

### 交易配置 `data/config.json`

```json
{
  "slippage_pct": 6.0,        // 滑点容忍度（百分比）
  "slippage_mode": "partial", // 超滑点处理：partial=部分成交，cancel=取消整单
  "web_port": 8000,
  "mcp_port": 8001
}
```

---

## REST API 文档

**Base URL**：`http://your-server:8000`

所有请求/响应均为 JSON，已启用 CORS（跨域支持）。

---

### 凭据管理

#### `POST /api/generate-env`

根据钱包私钥自动生成 Polymarket API 凭据并写入 `data/.env`。

**请求体：**
```json
{
  "private_key": "301638e633936d355596b...",
  "wallet_address": "0xCE1001c32c78b62348Ba..."
}
```

**成功响应：**
```json
{
  "success": true,
  "CLOB_API_KEY": "...",
  "CLOB_SECRET": "...",
  "CLOB_PASS_PHRASE": "..."
}
```

**失败响应：**
```json
{
  "success": false,
  "error": "需要 private_key 和 wallet_address"
}
```

---

#### `GET /api/env-status`

检查是否已配置凭据（脱敏展示钱包地址）。

**响应：**
```json
{
  "has_env": true,
  "wallet_preview": "0xCE1001c3...e0b51d4"
}
```

---

### 交易配置

#### `GET /api/config`

获取当前滑点配置。

**响应：**
```json
{
  "slippage_pct": 6.0,
  "slippage_mode": "partial"
}
```

#### `POST /api/config`

更新滑点配置。

**请求体：**
```json
{
  "slippage_pct": 3.0,
  "slippage_mode": "cancel"
}
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `slippage_pct` | float | 滑点容忍百分比，如 `3.0` 表示 3% |
| `slippage_mode` | string | `partial`：部分成交；`cancel`：超出则取消整单 |

---

### 余额查询

#### `GET /api/balance`

查询钱包 USDC.e 余额与授权额度。

**响应：**
```json
{
  "balance": 125.34,
  "allowance": 999999.0
}
```

> `balance` 和 `allowance` 单位均为 USDC（已折算，非链上最小单位）。

---

### 持仓管理

#### `GET /api/positions`

查询当前钱包全部持仓。

**响应：**
```json
{
  "wallet": "0xCE1001c32c78b62348Ba...",
  "positions": [
    {
      "asset": "71321045679252212594626385532706912750332728571942532289631379312455583992563",
      "outcome": "Yes",
      "title": "Will X happen?",
      "size": 150.5,
      "currentValue": 87.3,
      "avgPrice": 0.58
    }
  ]
}
```

---

#### `POST /api/positions/close`

市价卖出指定持仓（平仓）。若传入数量超过实际持仓，自动截断为持仓量。

**请求体：**
```json
{
  "token_id": "71321045679252212594626385532706912750332728571942532289631379312455583992563",
  "amount": 100.0
}
```

**成功响应：**
```json
{
  "success": true,
  "order_id": "0x...",
  "avg_price": 0.58,
  "slippage_pct": 1.2,
  "sold_amount": 100.0,
  "adjusted": false
}
```

---

### 市场查询

#### `GET /api/token-ids?slug={slug}`

通过市场 slug 查询该事件下所有可交易 Token ID。

**示例：**
```
GET /api/token-ids?slug=will-the-fed-cut-rates-in-march-2026
```

**响应：**
```json
{
  "items": [
    {
      "tokenid": "7132104567...",
      "outcome": "Yes",
      "groupItemTitle": "Will the Fed cut rates? (Yes)",
      "baseTitle": "Will the Fed cut rates?",
      "marketSlug": "will-the-fed-cut-rates-in-march-2026",
      "marketId": "0x...",
      "eventSlug": "will-the-fed-cut-rates-in-march-2026"
    },
    {
      "tokenid": "9087654321...",
      "outcome": "No",
      "groupItemTitle": "Will the Fed cut rates? (No)",
      ...
    }
  ],
  "error": ""
}
```

---

#### `GET /api/midpoint?token_id={token_id}`

查询指定 Token 的当前中间价（市场隐含概率）。

**示例：**
```
GET /api/midpoint?token_id=71321045679252...
```

**响应：**
```json
{
  "token_id": "71321045679252...",
  "mid": 0.62
}
```

> `mid` 范围为 0~1，代表该 outcome 当前的隐含概率/价格（如 `0.62` 表示 62¢/share）。

---

### 快速交易

#### `POST /api/trade/buy`

市价买入。

**请求体：**
```json
{
  "token_id": "71321045679252212594...",
  "amount": 50.0
}
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `token_id` | string | Outcome Token ID（由 `/api/token-ids` 获取） |
| `amount` | float | 买入金额，单位 USDC |

**成功响应：**
```json
{
  "success": true,
  "order_id": "0xabc123...",
  "avg_price": 0.63,
  "slippage_pct": 1.59,
  "amount_usdc": 50.0,
  "adjusted": false
}
```

**滑点触发（partial 模式）响应：**
```json
{
  "success": true,
  "order_id": "0xabc123...",
  "avg_price": 0.64,
  "amount_usdc": 32.5,
  "adjusted": true
}
```

**滑点触发（cancel 模式）响应：**
```json
{
  "success": false,
  "error": "滑点超出 3%（实际 4.20%），已取消整单",
  "avg_price": 0.67,
  "slippage_pct": 4.2
}
```

---

#### `POST /api/trade/sell`

市价卖出。

**请求体：**
```json
{
  "token_id": "71321045679252212594...",
  "amount": 80.0
}
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `token_id` | string | Outcome Token ID |
| `amount` | float | 卖出数量，单位 shares |

**成功响应：**
```json
{
  "success": true,
  "order_id": "0xdef456...",
  "avg_price": 0.61,
  "slippage_pct": 1.61,
  "sold_amount": 80.0,
  "adjusted": false
}
```

---

### 交易记录

#### `GET /api/trades?limit={n}`

获取历史交易记录，默认返回最近 200 条。

**示例：**
```
GET /api/trades?limit=50
```

**响应（数组）：**
```json
[
  {
    "time": "2026-03-12T07:49:13Z",
    "side": "buy",
    "token_id": "71321045...",
    "amount_usdc": 50.0,
    "status": "filled",
    "avg_price": 0.63,
    "order_id": "0xabc123..."
  },
  {
    "time": "2026-03-12T08:10:05Z",
    "side": "sell",
    "token_id": "71321045...",
    "amount_shares": 80.0,
    "status": "filled",
    "avg_price": 0.71,
    "order_id": "0xdef456..."
  }
]
```

| `status` 值 | 含义 |
|------------|------|
| `filled` | 完全成交 |
| `partial_filled` | 部分成交（触发 partial 滑点） |
| `adjusted_filled` | 持仓不足后截断成交 |
| `cancelled` | 触发 cancel 滑点，整单取消 |
| `failed` | 其他原因失败 |

---

## MCP 工具文档

**MCP SSE 端点**：`http://your-server:8001/sse`

本服务基于 [FastMCP](https://gofastmcp.com) 实现，兼容所有支持 MCP 协议的 AI 客户端（Claude Desktop、Cursor、Continue 等）。

### 接入配置

在 AI 客户端的 MCP 配置中添加：

```json
{
  "mcpServers": {
    "polymarket-trader": {
      "url": "http://205.198.89.197:8001/sse",
      "transport": "sse"
    }
  }
}
```

---

### 工具列表

#### `get_token_ids`

从市场 slug 获取可交易的 Token ID 列表。**交易前必须先调用此工具获取 token_id。**

| 参数 | 类型 | 说明 |
|------|------|------|
| `slug` | string | 市场 slug，从 Polymarket URL 中获取 |

**示例调用：**
```
get_token_ids(slug="will-the-fed-cut-rates-in-march-2026")
```

**返回：**
```json
{
  "items": [
    {
      "tokenid": "71321045679252...",
      "outcome": "Yes",
      "groupItemTitle": "Will the Fed cut rates? (Yes)"
    },
    {
      "tokenid": "90876543219876...",
      "outcome": "No",
      "groupItemTitle": "Will the Fed cut rates? (No)"
    }
  ],
  "error": ""
}
```

---

#### `get_midpoint`

查询指定 Token 的当前中间价（市场隐含概率）。

| 参数 | 类型 | 说明 |
|------|------|------|
| `token_id` | string | Outcome Token ID |

**返回：**
```json
{
  "token_id": "71321045679252...",
  "mid": 0.62
}
```

---

#### `get_balance`

查询钱包 USDC.e 余额与合约授权额度。

**无需参数。**

**返回：**
```json
{
  "balance": 125.34,
  "allowance": 999999.0
}
```

---

#### `get_positions`

查询当前钱包全部持仓（包含灰尘持仓，前端可自行过滤 `currentValue <= 2` 的项）。

**无需参数。**

**返回：**
```json
{
  "wallet": "0xCE1001c32c78b...",
  "positions": [
    {
      "asset": "71321045...",
      "outcome": "Yes",
      "size": 150.5,
      "currentValue": 87.3
    }
  ]
}
```

---

#### `market_buy`

市价买入。按 USDC 金额下 FOK 市价单，内置滑点保护（使用 `data/config.json` 中的配置）。

| 参数 | 类型 | 说明 |
|------|------|------|
| `token_id` | string | Outcome Token ID |
| `amount` | float | 买入金额，单位 USDC |

**成功返回：**
```json
{
  "success": true,
  "order_id": "0xabc123...",
  "avg_price": 0.63,
  "slippage_pct": 1.59,
  "amount_usdc": 50.0,
  "adjusted": false
}
```

**失败返回：**
```json
{
  "success": false,
  "error": "滑点超出 6%（实际 7.30%），已取消整单"
}
```

---

#### `market_sell`

市价卖出。按 shares 数量下 FOK 市价卖单。若传入数量超过持仓会自动截断，内置滑点保护。

| 参数 | 类型 | 说明 |
|------|------|------|
| `token_id` | string | Outcome Token ID |
| `amount` | float | 卖出数量，单位 shares |

**成功返回：**
```json
{
  "success": true,
  "order_id": "0xdef456...",
  "avg_price": 0.71,
  "slippage_pct": 1.41,
  "sold_amount": 80.0,
  "adjusted": false
}
```

---

### AI 助手使用示例

以下是与支持 MCP 的 AI 助手对话的典型工作流：

```
用户：帮我查一下美联储 3 月降息市场的当前价格。

AI：好的，先获取 token_id…
[调用 get_token_ids(slug="fed-rate-cut-march-2026")]
[调用 get_midpoint(token_id="71321045...")]

当前 Yes 价格为 0.34（即市场认为 3 月降息概率为 34%）。

用户：买 100 USDC 的 Yes。

AI：[调用 market_buy(token_id="71321045...", amount=100)]
买入成功！订单 ID: 0xabc123...，成交均价 $0.35，滑点 2.9%。
```

---

## 滑点保护机制

系统在下单前会模拟订单簿成交，检测实际成交均价与当前中间价的偏差：

| 模式 | 行为 |
|------|------|
| `partial`（默认） | 超出滑点阈值时，只买/卖订单簿中价格合理的部分，剩余放弃 |
| `cancel` | 超出滑点阈值时，取消整笔订单，不成交 |

**调整滑点容忍度：**

```bash
# REST API
curl -X POST http://localhost:8000/api/config \
  -H "Content-Type: application/json" \
  -d '{"slippage_pct": 3.0, "slippage_mode": "cancel"}'
```

---

## 服务地址

| 服务 | 地址 |
|------|------|
| Web UI | http://205.198.89.197:8000 |
| REST API | http://205.198.89.197:8000/api/... |
| MCP SSE | http://205.198.89.197:8001/sse |
