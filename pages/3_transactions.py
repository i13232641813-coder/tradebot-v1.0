"""Transaction entry and CRUD page."""

from datetime import date
import logging

import pandas as pd
import streamlit as st

from database.db import DatabaseError, TransactionRepository
from database.models import Transaction
from services.market_data import MarketDataError, YahooMarketDataProvider, default_history_range
from services.portfolio_service import PortfolioValidationError, calculate_positions
from services.transaction_service import TransactionService
from utils.validators import validate_security_symbol
from utils.logging_config import configure_logging
from utils.i18n import language_selector, tr

configure_logging()
LOGGER = logging.getLogger(__name__)
st.set_page_config(page_title="交易记录 | TradeBot", page_icon="🧾", layout="wide")
service = TransactionService(TransactionRepository())


def resolve_name(code: str, supplied_name: str) -> str:
    if supplied_name.strip():
        return supplied_name.strip()
    start, end = default_history_range()
    return YahooMarketDataProvider().get_stock_history(code, start, end).name


def transaction_form(prefix: str, existing: Transaction | None = None) -> Transaction | None:
    with st.form(f"{prefix}_form", clear_on_submit=existing is None):
        columns = st.columns(3)
        code = columns[0].text_input(tr("证券代码","Ticker"), value=existing.stock_code if existing else "")
        name = columns[1].text_input(tr("股票名称（留空自动获取）","Name (blank for auto lookup)"), value=existing.stock_name if existing else "")
        trade_type = columns[2].selectbox(tr("类型","Type"), ["BUY", "SELL"], index=0 if not existing or existing.trade_type == "BUY" else 1)
        columns = st.columns(4)
        trade_price = columns[0].number_input(tr("成交价格","Trade Price"), min_value=0.0, value=float(existing.price) if existing else 0.0, step=0.01)
        quantity = columns[1].number_input(tr("数量（股）","Quantity (shares)"), min_value=1, value=existing.quantity if existing else 100, step=1)
        trade_date = columns[2].date_input(tr("交易日期","Trade Date"), value=existing.trade_date if existing else date.today(), max_value=date.today())
        fee = columns[3].number_input(tr("手续费","Fee"), min_value=0.0, value=float(existing.fee) if existing else 0.0, step=0.01)
        note = st.text_input(tr("备注（可选）","Note (optional)"), value=existing.note if existing else "")
        submitted = st.form_submit_button(tr("保存修改","Save Changes") if existing else tr("添加交易","Add Transaction"), type="primary")
    if not submitted:
        return None
    normalized = validate_security_symbol(code)
    return Transaction(
        id=existing.id if existing else None, created_at=existing.created_at if existing else None,
        stock_code=normalized, stock_name=resolve_name(normalized, name), trade_type=trade_type,
        price=float(trade_price), quantity=int(quantity), trade_date=trade_date, fee=float(fee), note=note.strip(),
    )


with st.sidebar:
    st.markdown("## TradeBot")
    language_selector()
st.title(tr("交易记录", "Transactions"))
st.caption(tr("支持A股和美股，持仓按移动加权平均成本法计算。", "Supports A-shares and US stocks. Positions use moving weighted-average cost."))

try:
    with st.expander(tr("添加交易", "Add Transaction"), expanded=not service.list_all()):
        created = transaction_form("add")
        if created:
            service.add(created)
            st.success(f"已添加：{created.stock_code} {created.trade_type} {created.quantity} 股")
            st.rerun()

    transactions = service.list_all()
    if not transactions:
        st.info(tr("暂无交易记录，请添加第一笔交易。", "No transactions yet. Add your first transaction."))
        st.stop()

    st.subheader(tr("全部交易", "All Transactions"))
    filters = st.columns(3)
    code_filter = filters[0].text_input(tr("按代码筛选","Filter by ticker")).strip().upper()
    type_filter = filters[1].selectbox(tr("按类型筛选","Filter by type"), ["全部", "BUY", "SELL"], format_func=lambda value: tr("全部","All") if value=="全部" else value)
    descending = filters[2].toggle(tr("日期倒序","Newest first"), value=True)
    filtered = [item for item in transactions if (not code_filter or code_filter in item.stock_code) and (type_filter == "全部" or item.trade_type == type_filter)]
    filtered.sort(key=lambda item: (item.trade_date, item.id or 0), reverse=descending)
    frame = pd.DataFrame([{
        "ID": item.id, tr("日期","Date"): item.trade_date, tr("代码","Ticker"): item.stock_code, tr("名称","Name"): item.stock_name,
        tr("类型","Type"): item.trade_type, tr("成交价格","Trade Price"): item.price, tr("数量(股)","Quantity"): item.quantity,
        tr("手续费","Fee"): item.fee, tr("备注","Note"): item.note,
    } for item in filtered])
    st.dataframe(frame, width="stretch", hide_index=True)

    ids = [item.id for item in transactions if item.id is not None]
    selected_id = st.selectbox(tr("选择要编辑或删除的交易 ID", "Select transaction ID to edit or delete"), ids)
    selected = next(item for item in transactions if item.id == selected_id)
    edit_tab, delete_tab = st.tabs([tr("编辑", "Edit"), tr("删除", "Delete")])
    with edit_tab:
        updated = transaction_form(f"edit_{selected_id}", selected)
        if updated:
            service.update(updated)
            st.success("交易已更新，持仓和盈亏已重新计算。")
            st.rerun()
    with delete_tab:
        st.warning(tr("删除后会重新计算全部持仓和盈亏，此操作不可撤销。","Deleting recalculates all positions and P&L. This cannot be undone."))
        confirm = st.checkbox(tr("我确认删除这笔交易","I confirm deletion"), key=f"confirm_{selected_id}")
        if st.button(tr("永久删除","Delete Permanently"), disabled=not confirm, type="primary"):
            service.delete(selected_id)
            st.success("交易已删除，持仓和盈亏已重新计算。")
            st.rerun()

    st.subheader(tr("当前持仓计算预览", "Current Position Preview"))
    positions = calculate_positions(transactions)
    if positions:
        st.dataframe(pd.DataFrame([{
            "代码": p.stock_code, "名称": p.stock_name, "数量(股)": p.quantity,
            "平均成本": round(p.average_cost, 4), "已实现盈亏": round(p.realized_pnl, 2),
        } for p in positions]), width="stretch", hide_index=True)
    else:
        st.info("当前没有未平仓持仓。历史交易仍已保留。")
except (ValueError, PortfolioValidationError, DatabaseError, MarketDataError) as exc:
    st.error(str(exc))
except Exception:
    LOGGER.exception("Unexpected transaction page error")
    st.error("交易页面处理失败，详细错误已记录。")
