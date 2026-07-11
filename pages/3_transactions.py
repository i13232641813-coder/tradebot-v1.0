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
        code = columns[0].text_input("证券代码", value=existing.stock_code if existing else "")
        name = columns[1].text_input("股票名称（留空自动获取）", value=existing.stock_name if existing else "")
        trade_type = columns[2].selectbox("类型", ["BUY", "SELL"], index=0 if not existing or existing.trade_type == "BUY" else 1)
        columns = st.columns(4)
        trade_price = columns[0].number_input("成交价格", min_value=0.0, value=float(existing.price) if existing else 0.0, step=0.01)
        quantity = columns[1].number_input("数量（股）", min_value=1, value=existing.quantity if existing else 100, step=1)
        trade_date = columns[2].date_input("交易日期", value=existing.trade_date if existing else date.today(), max_value=date.today())
        fee = columns[3].number_input("手续费", min_value=0.0, value=float(existing.fee) if existing else 0.0, step=0.01)
        note = st.text_input("备注（可选）", value=existing.note if existing else "")
        submitted = st.form_submit_button("保存修改" if existing else "添加交易", type="primary")
    if not submitted:
        return None
    normalized = validate_security_symbol(code)
    return Transaction(
        id=existing.id if existing else None, created_at=existing.created_at if existing else None,
        stock_code=normalized, stock_name=resolve_name(normalized, name), trade_type=trade_type,
        price=float(trade_price), quantity=int(quantity), trade_date=trade_date, fee=float(fee), note=note.strip(),
    )


st.title("交易记录")
st.caption("支持 A 股和美股；持仓按移动加权平均成本法从全部历史交易重新计算。")

try:
    with st.expander("添加交易", expanded=not service.list_all()):
        created = transaction_form("add")
        if created:
            service.add(created)
            st.success(f"已添加：{created.stock_code} {created.trade_type} {created.quantity} 股")
            st.rerun()

    transactions = service.list_all()
    if not transactions:
        st.info("暂无交易记录，请添加第一笔交易。")
        st.stop()

    st.subheader("全部交易")
    filters = st.columns(3)
    code_filter = filters[0].text_input("按代码筛选").strip().upper()
    type_filter = filters[1].selectbox("按类型筛选", ["全部", "BUY", "SELL"])
    descending = filters[2].toggle("日期倒序", value=True)
    filtered = [item for item in transactions if (not code_filter or code_filter in item.stock_code) and (type_filter == "全部" or item.trade_type == type_filter)]
    filtered.sort(key=lambda item: (item.trade_date, item.id or 0), reverse=descending)
    frame = pd.DataFrame([{
        "ID": item.id, "日期": item.trade_date, "代码": item.stock_code, "名称": item.stock_name,
        "类型": item.trade_type, "成交价格": item.price, "数量(股)": item.quantity,
        "手续费": item.fee, "备注": item.note,
    } for item in filtered])
    st.dataframe(frame, width="stretch", hide_index=True)

    ids = [item.id for item in transactions if item.id is not None]
    selected_id = st.selectbox("选择要编辑或删除的交易 ID", ids)
    selected = next(item for item in transactions if item.id == selected_id)
    edit_tab, delete_tab = st.tabs(["编辑", "删除"])
    with edit_tab:
        updated = transaction_form(f"edit_{selected_id}", selected)
        if updated:
            service.update(updated)
            st.success("交易已更新，持仓和盈亏已重新计算。")
            st.rerun()
    with delete_tab:
        st.warning("删除后会重新计算全部持仓和盈亏，此操作不可撤销。")
        confirm = st.checkbox("我确认删除这笔交易", key=f"confirm_{selected_id}")
        if st.button("永久删除", disabled=not confirm, type="primary"):
            service.delete(selected_id)
            st.success("交易已删除，持仓和盈亏已重新计算。")
            st.rerun()

    st.subheader("当前持仓计算预览")
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
