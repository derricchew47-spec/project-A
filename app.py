import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
from datetime import datetime
import yfinance as yf

# -----------------------------------------------------------------------------
# 1. 数据库初始化与核心函数
# -----------------------------------------------------------------------------
DB_FILE = "portfolio.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            asset_type TEXT NOT NULL,
            platform TEXT NOT NULL,
            symbol TEXT,
            name TEXT NOT NULL,
            tx_type TEXT NOT NULL,
            price REAL NOT NULL,
            quantity REAL NOT NULL,
            total_amount REAL NOT NULL,
            notes TEXT
        )
    ''')
    conn.commit()

    # 初始化自定义标的最新参考价表（用于黄金、货币基金等无法直接通过 yfinance 获取的标的）
    c.execute('''
        CREATE TABLE IF NOT EXISTS manual_prices (
            symbol_or_name TEXT PRIMARY KEY,
            last_price REAL NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def load_transactions():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM transactions ORDER BY date DESC, id DESC", conn)
    conn.close()
    return df

def save_transaction(date, asset_type, platform, symbol, name, tx_type, price, quantity, total_amount, notes):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO transactions (date, asset_type, platform, symbol, name, tx_type, price, quantity, total_amount, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (date, asset_type, platform, symbol, name, tx_type, price, quantity, total_amount, notes))
    conn.commit()
    conn.close()

def update_transaction(tx_id, date, asset_type, platform, symbol, name, tx_type, price, quantity, total_amount, notes):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        UPDATE transactions
        SET date=?, asset_type=?, platform=?, symbol=?, name=?, tx_type=?, price=?, quantity=?, total_amount=?, notes=?
        WHERE id=?
    ''', (date, asset_type, platform, symbol, name, tx_type, price, quantity, total_amount, notes, tx_id))
    conn.commit()
    conn.close()

def delete_transaction(tx_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM transactions WHERE id=?", (tx_id,))
    conn.commit()
    conn.close()

def update_manual_price(key, price):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO manual_prices (symbol_or_name, last_price, updated_at)
        VALUES (?, ?, ?)
    ''', (key, price, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()

def get_manual_prices():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM manual_prices", conn)
    conn.close()
    return dict(zip(df['symbol_or_name'], df['last_price']))

@st.cache_data(ttl=300)
def fetch_realtime_price(symbol, asset_type, default_price):
    """获取实时价格逻辑：股票/ETF调用yfinance，货币基金/黄金使用手动设置或成本价 fallback"""
    if asset_type in ["股票/ETF", "加密货币"] and symbol:
        try:
            ticker = yf.Ticker(symbol)
            fast_info = ticker.fast_info
            if hasattr(fast_info, 'last_price') and fast_info.last_price is not None:
                return float(fast_info.last_price)
            hist = ticker.history(period="1d")
            if not hist.empty:
                return float(hist['Close'].iloc[-1])
        except Exception:
            pass
    return default_price

# -----------------------------------------------------------------------------
# 2. 页面配置与 UI 样式注入
# -----------------------------------------------------------------------------
st.set_page_config(page_title="全资产智能投资看板", layout="wide", initial_sidebar_state="expanded")
init_db()

st.markdown("""
<style>
    .stApp { background-color: #f8f9fa; }
    .metric-card {
        background: white;
        border-radius: 12px;
        padding: 18px 24px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.04);
        border: 1px solid #edf2f7;
        text-align: center;
    }
    .metric-value { font-size: 26px; font-weight: 700; color: #1a202c; }
    .metric-label { font-size: 14px; color: #718096; margin-bottom: 6px; }
    .metric-sub { font-size: 12px; color: #38a169; }
    div[data-testid="stForm"] {
        background: white;
        padding: 24px;
        border-radius: 12px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.03);
        border: 1px solid #edf2f7;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 3. 导航栏与核心计算逻辑
# -----------------------------------------------------------------------------
menu = st.sidebar.radio("导航菜单", ["📊 实时资产配置与智能再平衡", "➕ 标的买卖与资金录入", "📋 交易明细与数据管理"])

df_tx = load_transactions()
manual_prices = get_manual_prices()

# 计算持仓与资产大类逻辑
holdings = {}
if not df_tx.empty:
    for _, row in df_tx.iterrows():
        key = row['symbol'] if row['symbol'] and row['symbol'].strip() else row['name']
        if key not in holdings:
            holdings[key] = {
                'name': row['name'],
                'symbol': row['symbol'],
                'asset_type': row['asset_type'],
                'platform': row['platform'],
                'quantity': 0.0,
                'total_cost': 0.0
            }
        
        qty = row['quantity']
        amt = row['total_amount']
        
        if row['tx_type'] in ['买入', '存入']:
            holdings[key]['quantity'] += qty
            holdings[key]['total_cost'] += amt
        elif row['tx_type'] in ['卖出', '取出']:
            holdings[key]['quantity'] -= qty
            holdings[key]['total_cost'] -= amt

# 汇总有效持仓数据
portfolio_list = []
for key, item in holdings.items():
    if item['quantity'] > 0.0001:
        # 获取实时或自定义单价
        last_known_price = manual_prices.get(key, item['total_cost'] / item['quantity'] if item['quantity'] > 0 else 0)
        current_unit_price = fetch_realtime_price(item['symbol'], item['asset_type'], last_known_price)
        market_value = current_unit_price * item['quantity']
        profit = market_value - item['total_cost']
        profit_rate = (profit / item['total_cost'] * 100) if item['total_cost'] > 0 else 0
        
        portfolio_list.append({
            'key': key,
            'name': item['name'],
            'symbol': item['symbol'],
            'asset_type': item['asset_type'],
            'platform': item['platform'],
            'quantity': item['quantity'],
            'avg_cost': item['total_cost'] / item['quantity'] if item['quantity'] > 0 else 0,
            'current_price': current_unit_price,
            'total_cost': item['total_cost'],
            'market_value': market_value,
            'profit': profit,
            'profit_rate': profit_rate
        })

df_portfolio = pd.DataFrame(portfolio_list)

# -----------------------------------------------------------------------------
# 4. 页面 1: 实时资产配置与智能再平衡
# -----------------------------------------------------------------------------
if menu == "📊 实时资产配置与智能再平衡":
    st.title("📊 实时资产配置与智能调仓")
    
    if df_portfolio.empty:
        st.info("💡 暂无持仓数据，请前往『标的买卖与资金录入』添加第一笔资产。")
    else:
        total_market_value = df_portfolio['market_value'].sum()
        total_cost = df_portfolio['total_cost'].sum()
        total_profit = total_market_value - total_cost
        total_profit_rate = (total_profit / total_cost * 100) if total_cost > 0 else 0
        
        # 顶部 KPI 卡片
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f'<div class="metric-card"><div class="metric-label">资产总市值</div><div class="metric-value">${total_market_value:,.2f}</div></div>', unsafe_allow_html=True)
        with col2:
            st.markdown(f'<div class="metric-card"><div class="metric-label">投入总成本</div><div class="metric-value">${total_cost:,.2f}</div></div>', unsafe_allow_html=True)
        with col3:
            st.markdown(f'<div class="metric-card"><div class="metric-label">未实现总盈亏</div><div class="metric-value" style="color:{"#38a169" if total_profit>=0 else "#e53e3e"}">${total_profit:,.2f}</div></div>', unsafe_allow_html=True)
        with col4:
            st.markdown(f'<div class="metric-card"><div class="metric-label">总收益率</div><div class="metric-value" style="color:{"#38a169" if total_profit_rate>=0 else "#e53e3e"}">{total_profit_rate:+.2f}%</div></div>', unsafe_allow_html=True)
        
        st.divider()
        
        # 可视化图表展示
        c1, c2 = st.columns(2)
        with c1:
            fig_type = px.pie(df_portfolio, values='market_value', names='asset_type', title="按资产类别分布 (含黄金/货币基金/股票)", hole=0.4)
            st.plotly_chart(fig_type, use_container_width=True)
        with c2:
            fig_platform = px.pie(df_portfolio, values='market_value', names='platform', title="按投资平台分布 (TNG/MooMoo/券商)", hole=0.4)
            st.plotly_chart(fig_platform, use_container_width=True)
            
        # 手动更新非实时接口标的价格（如黄金/货基）
        with st.expander("⚙️ 快速更新非自动联动标的（如 TNG 黄金 / MooMoo 货币基金）价格"):
            st.caption("对于无法自动通过美股/港股代码抓取实时价的标的，可在此手动校准最新单价：")
            m_col1, m_col2, m_col3 = st.columns(3)
            non_stock = df_portfolio[df_portfolio['asset_type'].isin(["黄金/贵金属", "货币基金/现金", "其他"])]
            if not non_stock.empty:
                selected_m_asset = m_col1.selectbox("选择要校准的标的", non_stock['key'].tolist())
                current_val = manual_prices.get(selected_m_asset, float(non_stock[non_stock['key']==selected_m_asset]['current_price'].iloc[0]))
                new_val = m_col2.number_input("最新实时单价/单位净值", value=float(current_val), format="%.4f")
                if m_col3.button("更新市值"):
                    update_manual_price(selected_m_asset, new_val)
                    st.success("更新成功！系统已依据最新单价重新计算总资产。")
                    st.rerun()

        st.divider()
        
        # 永久投资组合智能再平衡模块
        st.subheader("⚖️ 永久投资组合 (Permanent Portfolio) 智能再平衡")
        st.write("根据哈利·布朗 (Harry Browne) 经典永久投资组合策略，实时比对当前权重与目标配比，并计算所需买卖金额。")
        
        # 归类资产至 4 大类别
        perm_map = {
            "股票/ETF": "股票 (Stock)",
            "黄金/贵金属": "黄金 (Gold)",
            "货币基金/现金": "现金/货币基金 (Cash/MMF)",
            "加密货币": "股票 (Stock)",
            "其他": "现金/货币基金 (Cash/MMF)"
        }
        
        df_portfolio['perm_category'] = df_portfolio['asset_type'].map(perm_map)
        perm_summary = df_portfolio.groupby('perm_category')['market_value'].sum().reset_index()
        
        # 包含可能缺失的类别
        all_categories = ["股票 (Stock)", "黄金 (Gold)", "现金/货币基金 (Cash/MMF)", "债券 (Bond)"]
        existing_cats = perm_summary['perm_category'].tolist()
        for cat in all_categories:
            if cat not in existing_cats:
                perm_summary = pd.concat([perm_summary, pd.DataFrame([{'perm_category': cat, 'market_value': 0.0}])], ignore_index=True)
                
        perm_summary['current_ratio'] = perm_summary['market_value'] / total_market_value
        perm_summary['target_ratio'] = 0.25  # 默认 25% 均分
        perm_summary['target_value'] = total_market_value * perm_summary['target_ratio']
        perm_summary['rebalance_amount'] = perm_summary['target_value'] - perm_summary['market_value']
        
        # 格式化表格显示
        rebalance_display = perm_summary.copy()
        rebalance_display['当前市值'] = rebalance_display['market_value'].apply(lambda x: f"${x:,.2f}")
        rebalance_display['当前占比'] = rebalance_display['current_ratio'].apply(lambda x: f"{x*100:.2f}%")
        rebalance_display['目标占比'] = rebalance_display['target_ratio'].apply(lambda x: f"{x*100:.2f}%")
        rebalance_display['目标市值'] = rebalance_display['target_value'].apply(lambda x: f"${x:,.2f}")
        rebalance_display['建议调仓金额'] = rebalance_display['rebalance_amount'].apply(
            lambda x: f"🟢 需买入 ${x:,.2f}" if x > 0 else (f"🔴 需卖出 ${abs(x):,.2f}" if x < 0 else "✅ 维持不变")
        )
        
        st.dataframe(
            rebalance_display[['perm_category', '当前市值', '当前占比', '目标占比', '目标市值', '建议调仓金额']],
            use_container_width=True,
            hide_index=True
        )

# -----------------------------------------------------------------------------
# 5. 页面 2: 标的买卖与资金录入
# -----------------------------------------------------------------------------
elif menu == "➕ 标的买卖与资金录入":
    st.title("➕ 标的买卖与资金变动录入")
    st.caption("支持多资产类型录入：股票、黄金 (如 TNG e-Mas)、货币基金 (如 MooMoo Maybank Retail MMF) 及现金增减。")
    
    with st.form("trade_entry_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            asset_type = st.selectbox("1. 资产类型", ["股票/ETF", "黄金/贵金属", "货币基金/现金", "加密货币", "其他"])
            tx_type = st.selectbox("2. 交易类型", ["买入", "卖出", "存入", "取出"])
            date_val = st.date_input("3. 交易日期", datetime.now())
            
        with col2:
            platform = st.text_input("4. 投资平台", placeholder="例如: TNG e-Mas, MooMoo, 富途, Interactive Brokers")
            name = st.text_input("5. 标的名称", placeholder="例如: TNG 黄金, Maybank MMF, 苹果股票")
            symbol = st.text_input("6. 标的代码 (选填)", placeholder="例如: AAPL, 0102.KL, 无代码可留空")
            
        with col3:
            price = st.number_input("7. 成交单价 / 单位净值", min_value=0.0, format="%.4f", value=1.0000)
            quantity = st.number_input("8. 数量 / 克数 / 份额", min_value=0.0, format="%.4f", value=1.0000)
            notes = st.text_area("9. 备注 (选填)", placeholder="例如：每月定投，优惠券扣减等")
            
        calculated_total = price * quantity
        st.markdown(f"**💡 自动计算成交总金额: ${calculated_total:,.2f}**")
        
        submitted = st.form_submit_button("🚀 提交并保存交易记录", use_container_width=True)
        if submitted:
            if not platform or not name:
                st.error("⚠️ 平台名称与标的名称为必填项！")
            else:
                save_transaction(
                    date_val.strftime("%Y-%m-%d"),
                    asset_type,
                    platform,
                    symbol.upper().strip() if symbol else "",
                    name.strip(),
                    tx_type,
                    price,
                    quantity,
                    calculated_total,
                    notes
                )
                st.success(f"✅ 成功录入 {name} {tx_type} 记录！资产配置已同步更新。")

# -----------------------------------------------------------------------------
# 6. 页面 3: 交易明细与数据管理 (编辑/删除)
# -----------------------------------------------------------------------------
elif menu == "📋 交易明细与数据管理":
    st.title("📋 交易明细与数据修改 / 删除")
    st.caption("在此处可实时剔除、修改任何历史交易，系统将自动重算整体持仓与收益率。")
    
    if df_tx.empty:
        st.info("💡 暂无交易记录。")
    else:
        st.subheader("完整历史明细表")
        st.dataframe(df_tx, use_container_width=True, hide_index=True)
        
        st.divider()
        
        # 操作区：剔除或编辑指定记录
        c_edit, c_del = st.columns(2)
        
        with c_del:
            st.subheader("🗑️ 删除指定交易")
            tx_ids = df_tx['id'].tolist()
            delete_id = st.selectbox("选择要剔除的交易 ID", tx_ids, key="del_select")
            
            selected_row = df_tx[df_tx['id'] == delete_id].iloc[0]
            st.warning(f"即将删除: ID {delete_id} | {selected_row['date']} | {selected_row['platform']} - {selected_row['name']} | {selected_row['tx_type']} ${selected_row['total_amount']:,.2f}")
            
            if st.button("确认一键删除该记录", type="primary"):
                delete_transaction(delete_id)
                st.success(f"✅ ID {delete_id} 已成功剔除，资产数据已实时同步变动！")
                st.rerun()

        with c_edit:
            st.subheader("✏️ 编辑指定交易")
            edit_id = st.selectbox("选择要修改的交易 ID", tx_ids, key="edit_select")
            row_e = df_tx[df_tx['id'] == edit_id].iloc[0]
            
            with st.form("edit_form"):
                e_date = st.date_input("日期", datetime.strptime(row_e['date'], "%Y-%m-%d"))
                e_asset_type = st.selectbox("资产类型", ["股票/ETF", "黄金/贵金属", "货币基金/现金", "加密货币", "其他"], index=["股票/ETF", "黄金/贵金属", "货币基金/现金", "加密货币", "其他"].index(row_e['asset_type']) if row_e['asset_type'] in ["股票/ETF", "黄金/贵金属", "货币基金/现金", "加密货币", "其他"] else 0)
                e_platform = st.text_input("平台", value=row_e['platform'])
                e_name = st.text_input("名称", value=row_e['name'])
                e_symbol = st.text_input("代码", value=row_e['symbol'] if row_e['symbol'] else "")
                e_tx_type = st.selectbox("交易类型", ["买入", "卖出", "存入", "取出"], index=["买入", "卖出", "存入", "取出"].index(row_e['tx_type']) if row_e['tx_type'] in ["买入", "卖出", "存入", "取出"] else 0)
                e_price = st.number_input("单价", value=float(row_e['price']), format="%.4f")
                e_qty = st.number_input("数量", value=float(row_e['quantity']), format="%.4f")
                e_notes = st.text_input("备注", value=row_e['notes'] if row_e['notes'] else "")
                
                if st.form_submit_button("保存修改"):
                    update_transaction(
                        edit_id,
                        e_date.strftime("%Y-%m-%d"),
                        e_asset_type,
                        e_platform,
                        e_symbol.upper().strip() if e_symbol else "",
                        e_name.strip(),
                        e_tx_type,
                        e_price,
                        e_qty,
                        e_price * e_qty,
                        e_notes
                    )
                    st.success(f"✅ ID {edit_id} 已成功更新！")
                    st.rerun()
