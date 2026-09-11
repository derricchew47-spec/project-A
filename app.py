import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
from datetime import datetime
import yfinance as yf

# -----------------------------------------------------------------------------
# 1. 数据库初始化与核心函数 (整合情侣/成员归属字段)
# -----------------------------------------------------------------------------
DB_FILE = "portfolio.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            owner TEXT NOT NULL DEFAULT '👩‍❤️‍👨 共同',
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
    
    # 兼容性检查：若已有旧表则自动升级添加 owner 字段
    c.execute("PRAGMA table_info(transactions)")
    columns = [info[1] for info in c.fetchall()]
    if 'owner' not in columns:
        c.execute("ALTER TABLE transactions ADD COLUMN owner TEXT NOT NULL DEFAULT '👩‍❤️‍👨 共同'")

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

def save_transaction(date, owner, asset_type, platform, symbol, name, tx_type, price, quantity, total_amount, notes):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO transactions (date, owner, asset_type, platform, symbol, name, tx_type, price, quantity, total_amount, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (date, owner, asset_type, platform, symbol, name, tx_type, price, quantity, total_amount, notes))
    conn.commit()
    conn.close()

def update_transaction(tx_id, date, owner, asset_type, platform, symbol, name, tx_type, price, quantity, total_amount, notes):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        UPDATE transactions
        SET date=?, owner=?, asset_type=?, platform=?, symbol=?, name=?, tx_type=?, price=?, quantity=?, total_amount=?, notes=?
        WHERE id=?
    ''', (date, owner, asset_type, platform, symbol, name, tx_type, price, quantity, total_amount, notes, tx_id))
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
# 2. 页面 UI 配置
# -----------------------------------------------------------------------------
st.set_page_config(page_title="👩‍❤️‍👨 Our Portfolio | 情侣资产管理与实时投资看板", layout="wide", initial_sidebar_state="expanded")
init_db()

st.markdown("""
<style>
    .stApp { background-color: #f8f9fa; }
    .metric-card {
        background: white;
        border-radius: 12px;
        padding: 16px 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.04);
        border: 1px solid #edf2f7;
        text-align: center;
    }
    .metric-value { font-size: 24px; font-weight: 700; color: #1a202c; }
    .metric-label { font-size: 13px; color: #718096; margin-bottom: 4px; }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 3. 数据加载与持仓归集逻辑 (区分个人与共同资产)
# -----------------------------------------------------------------------------
menu = st.sidebar.radio("📌 功能导航", ["📊 实时资产配置与智能再平衡", "➕ 标的买卖与资金录入", "📋 交易明细与修改剔除"])

df_tx = load_transactions()
manual_prices = get_manual_prices()

# 区分持有人归集持仓
holdings = {}
if not df_tx.empty:
    for _, row in df_tx.iterrows():
        base_key = row['symbol'] if row['symbol'] and row['symbol'].strip() else row['name']
        owner = row.get('owner', '👩‍❤️‍👨 共同')
        unique_key = (base_key, owner)
        
        if unique_key not in holdings:
            holdings[unique_key] = {
                'base_key': base_key,
                'name': row['name'],
                'symbol': row['symbol'],
                'owner': owner,
                'asset_type': row['asset_type'],
                'platform': row['platform'],
                'quantity': 0.0,
                'total_cost': 0.0
            }
        
        qty = row['quantity']
        amt = row['total_amount']
        
        if row['tx_type'] in ['买入', '存入']:
            holdings[unique_key]['quantity'] += qty
            holdings[unique_key]['total_cost'] += amt
        elif row['tx_type'] in ['卖出', '取出']:
            holdings[unique_key]['quantity'] -= qty
            holdings[unique_key]['total_cost'] -= amt

portfolio_list = []
for (base_key, owner), item in holdings.items():
    if item['quantity'] > 0.0001:
        last_known_price = manual_prices.get(base_key, item['total_cost'] / item['quantity'] if item['quantity'] > 0 else 0)
        current_unit_price = fetch_realtime_price(item['symbol'], item['asset_type'], last_known_price)
        market_value = current_unit_price * item['quantity']
        profit = market_value - item['total_cost']
        profit_rate = (profit / item['total_cost'] * 100) if item['total_cost'] > 0 else 0
        
        portfolio_list.append({
            'unique_key': f"{base_key} ({owner})",
            'base_key': base_key,
            'name': item['name'],
            'symbol': item['symbol'],
            'owner': owner,
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
# 4. 页面 1: 实时资产配置与智能再平衡 (合并情侣维度)
# -----------------------------------------------------------------------------
if menu == "📊 实时资产配置与智能再平衡":
    st.title("👩‍❤️‍👨 情侣实时资产看板与智能调仓")
    
    if df_portfolio.empty:
        st.info("💡 当前暂无持仓数据，请前往『标的买卖与资金录入』页面添加第一笔记录。")
    else:
        # 按持有人计算资产分布
        total_mv = df_portfolio['market_value'].sum()
        total_cost = df_portfolio['total_cost'].sum()
        total_profit = total_mv - total_cost
        total_profit_rate = (total_profit / total_cost * 100) if total_cost > 0 else 0
        
        his_mv = df_portfolio[df_portfolio['owner'] == "👦 男方"]['market_value'].sum()
        her_mv = df_portfolio[df_portfolio['owner'] == "👧 女方"]['market_value'].sum()
        joint_mv = df_portfolio[df_portfolio['owner'] == "👩‍❤️‍👨 共同"]['market_value'].sum()
        
        # 顶部 KPI 概览卡片 (情侣维度)
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            st.markdown(f'<div class="metric-card"><div class="metric-label">👩‍❤️‍👨 双方总资产</div><div class="metric-value">${total_mv:,.2f}</div></div>', unsafe_allow_html=True)
        with c2:
            st.markdown(f'<div class="metric-card"><div class="metric-label">👦 男方资产</div><div class="metric-value">${his_mv:,.2f}</div></div>', unsafe_allow_html=True)
        with c3:
            st.markdown(f'<div class="metric-card"><div class="metric-label">👧 女方资产</div><div class="metric-value">${her_mv:,.2f}</div></div>', unsafe_allow_html=True)
        with c4:
            st.markdown(f'<div class="metric-card"><div class="metric-label">🤝 共同资产</div><div class="metric-value">${joint_mv:,.2f}</div></div>', unsafe_allow_html=True)
        with c5:
            st.markdown(f'<div class="metric-card"><div class="metric-label">📈 总盈亏 (收益率)</div><div class="metric-value" style="color:{"#38a169" if total_profit>=0 else "#e53e3e"}">${total_profit:,.2f} ({total_profit_rate:+.1f}%)</div></div>', unsafe_allow_html=True)
            
        st.divider()
        
        # 三维图表展示：归属分布、资产类别分布、投资平台分布
        g1, g2, g3 = st.columns(3)
        with g1:
            fig_owner = px.pie(df_portfolio, values='market_value', names='owner', title="资产归属比例", hole=0.4,
                               color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig_owner, use_container_width=True)
        with g2:
            fig_type = px.pie(df_portfolio, values='market_value', names='asset_type', title="资产类别分布", hole=0.4)
            st.plotly_chart(fig_type, use_container_width=True)
        with g3:
            fig_platform = px.pie(df_portfolio, values='market_value', names='platform', title="投资平台分布", hole=0.4)
            st.plotly_chart(fig_platform, use_container_width=True)
            
        # 校准无 API 接口标的（TNG 黄金 / MooMoo 货币基金等）
        with st.expander("⚙️ 手动更新非公开接口标的净值/价格（如 TNG 黄金 / MooMoo Maybank MMF）"):
            st.caption("对于无法自动通过美股/港股代码抓取实时价的标的，可在此手动校准最新单价：")
            m_col1, m_col2, m_col3 = st.columns(3)
            non_stock = df_portfolio[df_portfolio['asset_type'].isin(["黄金/贵金属", "货币基金/现金", "其他"])]
            if not non_stock.empty:
                unique_base_keys = list(set(non_stock['base_key'].tolist()))
                selected_key = m_col1.selectbox("选择要校准的标的", unique_base_keys)
                current_val = manual_prices.get(selected_key, float(non_stock[non_stock['base_key']==selected_key]['current_price'].iloc[0]))
                new_val = m_col2.number_input("最新实时单价/净值", value=float(current_val), format="%.4f")
                if m_col3.button("更新该标的市值"):
                    update_manual_price(selected_key, new_val)
                    st.success("最新价格已应用，关联持仓与资产总值已更新！")
                    st.rerun()

        st.divider()
        
        # 永久投资组合智能再平衡模块 (支持在同一页面实时调仓计算)
        st.subheader("⚖️ 永久投资组合 (Permanent Portfolio) 智能再平衡")
        st.write("将情侣双方资产自动归类至四大核心资产，对比目标 25% 配比并计算需买卖金额：")
        
        perm_map = {
            "股票/ETF": "股票 (Stock)",
            "黄金/贵金属": "黄金 (Gold)",
            "货币基金/现金": "现金/货币基金 (Cash/MMF)",
            "加密货币": "股票 (Stock)",
            "其他": "现金/货币基金 (Cash/MMF)"
        }
        
        df_portfolio['perm_category'] = df_portfolio['asset_type'].map(perm_map)
        perm_summary = df_portfolio.groupby('perm_category')['market_value'].sum().reset_index()
        
        all_categories = ["股票 (Stock)", "黄金 (Gold)", "现金/货币基金 (Cash/MMF)", "债券 (Bond)"]
        existing_cats = perm_summary['perm_category'].tolist()
        for cat in all_categories:
            if cat not in existing_cats:
                perm_summary = pd.concat([perm_summary, pd.DataFrame([{'perm_category': cat, 'market_value': 0.0}])], ignore_index=True)
                
        perm_summary['current_ratio'] = perm_summary['market_value'] / total_mv
        perm_summary['target_ratio'] = 0.25
        perm_summary['target_value'] = total_mv * perm_summary['target_ratio']
        perm_summary['rebalance_amount'] = perm_summary['target_value'] - perm_summary['market_value']
        
        rebalance_display = perm_summary.copy()
        rebalance_display['当前市值'] = rebalance_display['market_value'].apply(lambda x: f"${x:,.2f}")
        rebalance_display['当前占比'] = rebalance_display['current_ratio'].apply(lambda x: f"{x*100:.2f}%")
        rebalance_display['目标占比'] = rebalance_display['target_ratio'].apply(lambda x: f"{x*100:.2f}%")
        rebalance_display['目标市值'] = rebalance_display['target_value'].apply(lambda x: f"${x:,.2f}")
        rebalance_display['建议调仓金额'] = rebalance_display['rebalance_amount'].apply(
            lambda x: f"🟢 建议买入 ${x:,.2f}" if x > 0 else (f"🔴 建议卖出 ${abs(x):,.2f}" if x < 0 else "✅ 保持均衡")
        )
        
        st.dataframe(
            rebalance_display[['perm_category', '当前市值', '当前占比', '目标占比', '目标市值', '建议调仓金额']],
            use_container_width=True,
            hide_index=True
        )

# -----------------------------------------------------------------------------
# 5. 页面 2: 标的买卖与资金录入 (支持选择持有人/平台/多资产)
# -----------------------------------------------------------------------------
elif menu == "➕ 标的买卖与资金录入":
    st.title("➕ 标的买卖与资金变动录入")
    st.caption("灵活支持多种资产（股票、TNG e-Mas 黄金、MooMoo Maybank MMF 货基等）及个人/共同资金划分。")
    
    with st.form("trade_entry_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            owner = st.selectbox("1. 资产持有人", ["👦 男方", "👧 女方", "👩‍❤️‍👨 共同"])
            asset_type = st.selectbox("2. 资产类型", ["股票/ETF", "黄金/贵金属", "货币基金/现金", "加密货币", "其他"])
            tx_type = st.selectbox("3. 交易类型", ["买入", "卖出", "存入", "取出"])
            
        with col2:
            platform = st.text_input("4. 投资平台", placeholder="例如: TNG e-Mas, MooMoo, 富途, 银行")
            name = st.text_input("5. 标的名称", placeholder="例如: TNG 黄金, Maybank MMF, 苹果股票")
            symbol = st.text_input("6. 标的代码 (选填)", placeholder="美股/港股填写代码(如 AAPL)，黄金/货基留空")
            
        with col3:
            date_val = st.date_input("7. 交易日期", datetime.now())
            price = st.number_input("8. 成交单价 / 单位净值", min_value=0.0, format="%.4f", value=1.0000)
            quantity = st.number_input("9. 数量 / 克数 / 份额", min_value=0.0, format="%.4f", value=1.0000)
            
        notes = st.text_input("10. 备注 (选填)", placeholder="例如：每月定投、工资存入、发红包扣除等")
        
        calculated_total = price * quantity
        st.info(f"💡 计算成交总金额: **${calculated_total:,.2f}**")
        
        submitted = st.form_submit_button("🚀 保存交易记录", use_container_width=True)
        if submitted:
            if not platform or not name:
                st.error("⚠️ 平台名称与标的名称为必填项！")
            else:
                save_transaction(
                    date_val.strftime("%Y-%m-%d"),
                    owner,
                    asset_type,
                    platform.strip(),
                    symbol.upper().strip() if symbol else "",
                    name.strip(),
                    tx_type,
                    price,
                    quantity,
                    calculated_total,
                    notes
                )
                st.success(f"✅ 成功保存 {owner} 的 {name} ({tx_type}) 记录！看板数据已同步变动。")

# -----------------------------------------------------------------------------
# 6. 页面 3: 交易明细与数据修改 / 剔除 (实时联动变动)
# -----------------------------------------------------------------------------
elif menu == "📋 交易明细与修改剔除":
    st.title("📋 交易明细管理")
    st.caption("在此可按持有人筛选明细，支持任意记录的编辑修改与一键剔除，所有修改将实时同步重新计算全盘资产。")
    
    if df_tx.empty:
        st.info("💡 暂无任何历史交易明细。")
    else:
        # 持有人筛选
        filter_owner = st.radio("筛选持有人", ["全部", "👦 男方", "👧 女方", "👩‍❤️‍👨 共同"], horizontal=True)
        filtered_df = df_tx if filter_owner == "全部" else df_tx[df_tx['owner'] == filter_owner]
        
        st.dataframe(filtered_df, use_container_width=True, hide_index=True)
        st.divider()
        
        c_edit, c_del = st.columns(2)
        tx_ids = df_tx['id'].tolist()
        
        with c_del:
            st.subheader("🗑️ 剔除指定交易记录")
            delete_id = st.selectbox("选择要剔除的交易 ID", tx_ids, key="del_select")
            row_d = df_tx[df_tx['id'] == delete_id].iloc[0]
            
            st.warning(f"准备删除: ID {delete_id} | {row_d['owner']} | {row_d['platform']} - {row_d['name']} | {row_d['tx_type']} ${row_d['total_amount']:,.2f}")
            if st.button("确认一键剔除", type="primary"):
                delete_transaction(delete_id)
                st.success(f"✅ 交易 ID {delete_id} 已彻底剔除，系统全盘数据已重新联动计算！")
                st.rerun()

        with c_edit:
            st.subheader("✏️ 修改指定交易记录")
            edit_id = st.selectbox("选择要修改的交易 ID", tx_ids, key="edit_select")
            row_e = df_tx[df_tx['id'] == edit_id].iloc[0]
            
            with st.form("edit_form"):
                e_owner = st.selectbox("持有人", ["👦 男方", "👧 女方", "👩‍❤️‍👨 共同"], index=["👦 男方", "👧 女方", "👩‍❤️‍👨 共同"].index(row_e['owner']) if row_e['owner'] in ["👦 男方", "👧 女方", "👩‍❤️‍👨 共同"] else 2)
                e_date = st.date_input("日期", datetime.strptime(row_e['date'], "%Y-%m-%d"))
                e_asset_type = st.selectbox("资产类型", ["股票/ETF", "黄金/贵金属", "货币基金/现金", "加密货币", "其他"], index=["股票/ETF", "黄金/贵金属", "货币基金/现金", "加密货币", "其他"].index(row_e['asset_type']) if row_e['asset_type'] in ["股票/ETF", "黄金/贵金属", "货币基金/现金", "加密货币", "其他"] else 0)
                e_platform = st.text_input("平台", value=row_e['platform'])
                e_name = st.text_input("标的名称", value=row_e['name'])
                e_symbol = st.text_input("代码", value=row_e['symbol'] if row_e['symbol'] else "")
                e_tx_type = st.selectbox("交易类型", ["买入", "卖出", "存入", "取出"], index=["买入", "卖出", "存入", "取出"].index(row_e['tx_type']) if row_e['tx_type'] in ["买入", "卖出", "存入", "取出"] else 0)
                e_price = st.number_input("单价", value=float(row_e['price']), format="%.4f")
                e_qty = st.number_input("数量", value=float(row_e['quantity']), format="%.4f")
                e_notes = st.text_input("备注", value=row_e['notes'] if row_e['notes'] else "")
                
                if st.form_submit_button("保存更新"):
                    update_transaction(
                        edit_id,
                        e_date.strftime("%Y-%m-%d"),
                        e_owner,
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
                    st.success(f"✅ ID {edit_id} 修改成功！")
                    st.rerun()
