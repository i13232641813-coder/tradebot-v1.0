# TradeBot V0.1

TradeBot 是一个本地运行的 A 股 / 美股技术分析和个人持仓管理应用。它用于行情展示、技术指标计算和个人交易记录，不执行自动下单，不预测价格，也不提供投资建议。

## 环境要求

- Windows、macOS 或 Linux
- Python 3.11 或 3.12
- 可访问 Yahoo Finance 的网络连接

## 安装

```powershell
cd "C:\Users\Austin\Desktop\tradebot v1.0"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

macOS 或 Linux 激活环境时使用：

```bash
source .venv/bin/activate
```

## 启动

```powershell
python -m streamlit run app.py
```

浏览器通常会自动打开 `http://localhost:8501`。停止应用请在终端按 `Ctrl+C`。修改 Python 模块后应完全停止并重启 Streamlit，不能只依赖页面 Rerun。

## 功能

- A 股和美股代码查询
- Yahoo 最新可用 1 分钟行情，每 10 秒刷新，可能延迟
- 前复权/自动复权日 K、成交量和时间范围选择
- MA、MACD、RSI、KDJ、BOLL、20 日年化历史波动率
- 固定、可解释的技术状态描述
- SQLite 交易新增、筛选、编辑和二次确认删除
- 移动加权平均成本、已实现盈亏和浮动盈亏
- 现金余额、总资产、资产结构和个股盈亏 Dashboard
- 美股通过 Yahoo `CNY=X` 汇率折算为人民币汇总
- 完全独立的 A 股历史日线回放模拟盘，次日开盘撮合、T+1、费用、净值和回撤

K 线周期由页面上的 `1M / 3M / 6M / 1Y` 控件切换，默认 3M。完整历史先计算
均线等指标，再切片为当前周期；价格轴和成交量轴分别根据当前切片重新适配。周期切换复用
缓存行情和指标，不依赖 Plotly 内置 rangeselector，也不会重新请求 Yahoo。

## 历史回放模拟盘

“模拟盘”页面使用独立的 `simulation_accounts`、`simulation_orders` 和
`simulation_daily_snapshots` 表，不读取或修改真实交易与现金。创建账户时可设置初始资金、
历史开始日期、佣金率、最低佣金、卖出税率和滑点。

模拟日收盘后提交的市价订单状态为 `PENDING`，点击“进入下一交易日”后才使用严格下一
交易日的开盘价并加入不利滑点。成交后状态为 `FILLED`；资金、可卖数量或行情不满足时为
`REJECTED`；待处理订单可取消为 `CANCELLED`。买入必须为 100 股整数倍，A 股当日买入数量
在下一交易日才变为可卖。止损和目标条件只作为交易日志记录，不会自动触发订单。

页面行情严格过滤为 `date <= 当前模拟日期`，下一日开盘价只在推进操作的撮合引擎内部读取。
本模式不使用分钟行情、不连接券商、不支持限价单、自动交易或 AI 建议。

历史回放提供与股票分析页一致的技术面视图：MA5/10/20/60、成交量及均量、MACD、
RSI、KDJ、BOLL 和 20 日年化历史波动率。所有滚动指标都在过滤未来行之后计算，因此
指标预热和状态卡同样不会使用当前模拟日期以后的数据。

技术图表会从 1990-01-01 开始请求行情，并展示 Yahoo 对该股票可提供的最早日线至当前
模拟日期的数据，用于上市以来走势和指标预热。Yahoo 缺失的早期行情不会被补造。订单、
现金和净值仍只从模拟账户开始日期计算。

## 证券代码

- 深市：`000938` → `000938.SZ`
- 沪市：`600584` → `600584.SS`
- 北交所：六位代码 → `.BJ`
- 美股：`AAPL`、`TSLA`、`MSFT`、`NVDA`、`BRK-B`

## 行情口径

默认数据源是 Yahoo Finance，AkShare 实现保留为可选 A 股数据源。顶部价格卡优先显示 Yahoo 最新可用的 1 分钟行情，并显示原始时间戳和时区。该数据不保证是交易所级实时行情。

K 线和技术指标使用已完成的日线数据，缓存 30 分钟；分钟行情缓存 10 秒。分钟行情不可用时退回带日期的最近日线收盘。Yahoo 日线不提供成交额时显示 `-`，不会构造数据。

价格单位：A 股为 `¥ / CNY`，美股为 `$ / USD`，成交量为股，涨跌幅为 `%`。持仓汇总以 CNY 为基准，美股按页面显示的最新可用 USD/CNY 汇率换算。

## 持仓计算

买入使用移动加权平均成本：

```text
新平均成本 = (原数量 × 原平均成本 + 买入数量 × 买入价格 + 买入手续费) / 新数量
```

卖出时平均成本保持不变：

```text
已实现盈亏 = 卖出数量 × (卖出价格 - 平均成本) - 卖出手续费
浮动盈亏 = 当前数量 × (最新价格 - 平均成本)
```

编辑或删除交易前会重新验证完整历史。任何时点出现超仓卖出时，操作会被拒绝，数据库不发生变化。

现金余额是用户维护的当前人民币现金，不根据历史交易自动倒推。

## 数据存储

首次打开交易或持仓页面会自动创建项目根目录下的 `tradebot.db`。主要数据表：

- `transactions`：全部买卖记录
- `account_settings`：现金余额

备份时停止应用并复制 `tradebot.db`。删除该文件会清空全部本地交易和现金数据。

## 项目目录

```text
app.py
pages/
  1_stock_analysis.py
  2_portfolio.py
  3_transactions.py
services/
  market_data.py
  indicators.py
  portfolio_service.py
  transaction_service.py
  ai_portfolio_service.py
database/
  db.py
  models.py
components/
  charts.py
  indicator_cards.py
  portfolio_charts.py
  stock_summary.py
utils/
  validators.py
  formatters.py
  logging_config.py
tests/
requirements.txt
```

## 测试

```powershell
python -m pytest -q
```

测试覆盖技术指标预热 NaN、移动平均成本、手续费、超仓卖出、CRUD 原子性、现金持久化、跨币种估值和代码校验。

## 常见问题

### 找不到 requirements.txt

先切换到项目目录：

```powershell
cd "C:\Users\Austin\Desktop\tradebot v1.0"
```

### ImportError: cannot import name

旧 Streamlit 进程仍缓存着修改前模块。终端按 `Ctrl+C` 完全停止，再重新启动，并在浏览器按 `Ctrl+F5`。

### Yahoo 行情不可用

检查网络、代理、防火墙和代码。Yahoo 可能限流或暂时缺少某个市场的数据。程序会显示中文错误并记录详细日志，不会生成替代行情。

### 持仓页无法汇总美股

通常是 `CNY=X` 汇率暂时不可用。为避免把不同币种直接相加，应用会停止跨币种汇总并显示错误。

### 日线日期比分钟行情旧

这是不同数据周期的正常现象。分钟卡展示最新可用分钟记录，指标只使用已经完成的日线。

### 查看日志

详细异常写入项目根目录的 `tradebot.log`，日志自动轮转，单文件最大约 2 MB。

## 风险声明

本应用仅用于数据展示和个人投资记录，不构成任何投资建议。Yahoo Finance、AkShare 和汇率数据均可能延迟、缺失或发生接口变化。应用不连接券商、不自动交易、不预测价格，也不调用大模型生成投资建议。
