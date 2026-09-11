import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
from datetime import datetime
import yfinance as yf

# -----------------------------------------------------------------------------
# 1. 数据库初始化与核心函数 (资金池 + 投资标的双表架构)
# -----------------------------------------------------------------------------
DB_FILE = "portfolio_pool.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # 1. 资金池注资/出金流水表
    c.execute('''
        CREATE TABLE IF NOT EXISTS capital_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            member TEXT NOT NULL,
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            notes TEXT
        )
    ''')
    
    # 2. 资金池投资标的买卖交易表
    c.execute('''
        CREATE TABLE IF NOT EXISTS pool_transactions (
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

    # 3. 自定义标的实时参考价表 (用于 TNG 黄金 / MooMoo 货基等)
    c.execute('''
        CREATE TABLE IF NOT EXISTS manual_prices (
            symbol_or_name TEXT PRIMARY KEY,
            last_price REAL NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# CRUD 资金池流水
def load_capital_ledger():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM capital_ledger ORDER BY date DESC, id DESC", conn)
    conn.close()
    return df

def save_capital_record(date, member, type_val, amount, notes):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO capital_ledger (date, member, type, amount, notes) VALUES (?, ?, ?, ?, ?)",
              (date, member, type_val, amount, notes))
    conn.commit()
    conn.close()

def update_capital_record(cid, date, member, type_val, amount, notes):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE capital_ledger SET date=?, member=?, type=?, amount=?, notes=? WHERE id=?",
              (date, member, type_val, amount, notes, cid))
    conn.commit()
    conn.close()

def delete_capital_record(cid):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM capital_ledger WHERE id=?", (cid,))
    conn.commit()
    conn.close()

# CRUD 资金池投资标的交易
def load_pool_transactions():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM pool_transactions ORDER BY date DESC, id DESC", conn)
    conn.close()
    return df

def save_pool_transaction(date, asset_type, platform, symbol, name, tx_type, price, quantity, total_amount, notes):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO pool_transactions (date, asset_type, platform, symbol, name, tx_type, price, quantity, total_amount, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (date, asset_type, platform, symbol, name, tx_type, price, quantity, total_amount, notes))
    conn.commit()
    conn.close()

def update_pool_transaction(tx_id, date, asset_type, platform, symbol, name, tx_type, price, quantity, total_amount, notes):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        UPDATE pool_transactions
        SET date=?, asset_type=?, platform=?, symbol=?, name=?, tx_type=?, price=?, quantity=?, total_amount=?, notes=?
        WHERE id=?
    ''', (date, asset_type, platform, symbol, name, tx_type, price, quantity, total_amount, notes, tx_id))
    conn.commit()
    conn.close()

def delete_pool_transaction(tx_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM pool_transactions WHERE id=?", (tx_id,))
    conn.commit()
    conn.close()

# 手动净值/参考价读写
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
# 2. 页面配置与 UI 样式
# -----------------------------------------------------------------------------
st.set_page_config(page_title="👩‍❤️‍👨 资金池与情侣投资管理", layout="wide", initial_sidebar_state="expanded")
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
    .metric-value { font-size: 22px; font-weight: 700; color: #1a202c; }
    .metric-label { font-size: 13px; color: #718096; margin-bottom: 4px; }
    .sub-text { font-size: 12px; color: #718096; }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 3. 核心计算引擎：资金池现金、投资标的市值与情侣份额比例
# -----------------------------------------------------------------------------
menu = st.sidebar.radio("📌 功能导航", [
    "📊 资金池与情侣权益总览",
    "💵 资金池注资/出金",
    "📈 资金池标的买卖",
    "📋 资金与交易记录管理"
])

df_cap = load_capital_ledger()
df_tx = load_pool_transactions()
manual_prices = get_manual_prices()

# 1. 计算双方累计注入资金池的本金
capital_summary = {'👦 男方': 0.0, '👧 女方': 0.0}
if not df_cap.empty:
    for _, row in df_cap.iterrows():
        m = row['member']
        amt = row['amount']
        if row['type'] in ['注资/存入本金', '存入']:
            capital_summary[m] += amt
        elif row['type'] in ['撤资/提取本金', '取出']:
            capital_summary[m] -= amt

total_pool_capital = sum(capital_summary.values())

# 2. 计算资金池持有的各个资产标的
holdings = {}
total_cash_spent_on_assets = 0.0

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
        
        if row['tx_type'] == '买入':
            holdings[key]['quantity'] += qty
            holdings[key]['total_cost'] += amt
            total_cash_spent_on_assets += amt
        elif row['tx_type'] == '卖出':
            holdings[key]['quantity'] -= qty
            holdings[key]['total_cost'] -= amt
            total_cash_spent_on_assets -= amt

# 3. 汇总当前有效持仓与市值
portfolio_list = []
total_assets_market_value = 0.0

for key, item in holdings.items():
    if item['quantity'] > 0.0001:
        last_price = manual_prices.get(key, item['total_cost'] / item['quantity'] if item['quantity'] > 0 else 0)
        curr_price = fetch_realtime_price(item['symbol'], item['asset_type'], last_price)
        mv = curr_price * item['quantity']
        total_assets_market_value += mv
        profit = mv - item['total_cost']
        
        portfolio_list.append({
            'key': key,
            'name': item['name'],
            'symbol': item['symbol'],
            'asset_type': item['asset_type'],
            'platform': item['platform'],
            'quantity': item['quantity'],
            'avg_cost': item['total_cost'] / item['quantity'] if item['quantity'] > 0 else 0,
            'current_price': curr_price,
            'total_cost': item['total_cost'],
            'market_value': mv,
            'profit': profit,
            'profit_rate': (profit / item['total_cost'] * 100) if item['total_cost'] > 0 else 0
        })

df_portfolio = pd.DataFrame(portfolio_list)

# 4. 计算资金池可用现金与总净资产
pool_cash_balance = total_pool_capital - total_cash_spent_on_assets
total_pool_net_worth = pool_cash_balance + total_assets_market_value
total_pool_profit = total_pool_net_worth - total_pool_capital
total_pool_profit_rate = (total_pool_profit / total_pool_capital * 100) if total_pool_capital > 0 else 0

# 5. 根据资金池份额比例计算双方的个人权益
equity_list = []
for m in ['👦 男方', '👧 女方']:
    cap = capital_summary[m]
    share_pct = (cap / total_pool_capital * 100) if total_pool_capital > 0 else 0.0
    equity_val = total_pool_net_worth * (share_pct / 100.0)
    member_profit = equity_val - cap
    member_profit_rate = (member_profit / cap * 100) if cap > 0 else 0.0
    
    equity_list.append({
        '成员': m,
        '累计投入本金': cap,
        '资金池占比 (%)': share_pct,
        '当前权益市值': equity_val,
        '累计盈亏': member_profit,
        '个人收益率 (%)': member_profit_rate
    })

df_equity = pd.DataFrame(equity_list)

# -----------------------------------------------------------------------------
# 4. 页面 1: 资金池与情侣权益总览 (包含资产配置与智能再平衡)
# -----------------------------------------------------------------------------
if menu == "📊 资金池与情侣权益总览":
    st.title("👩‍❤️‍👨 共享资金池与情侣权益总览")
    
    # 顶部 KPI 指标
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="metric-card"><div class="metric-label">🏦 资金池总净资产</div><div class="metric-value">${total_pool_net_worth:,.2f}</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="metric-card"><div class="metric-label">💵 资金池可用现金</div><div class="metric-value">${pool_cash_balance:,.2f}</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="metric-card"><div class="metric-label">📊 标的总市值</div><div class="metric-value">${total_assets_market_value:,.2f}</div></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="metric-card"><div class="metric-label">📈 资金池总盈亏 (收益率)</div><div class="metric-value" style="color:{"#38a169" if total_pool_profit>=0 else "#e53e3e"}">${total_pool_profit:,.2f} ({total_pool_profit_rate:+.2f}%)</div></div>', unsafe_allow_html=True)

    st.divider()

    # 双方权益划分表与饼图
    st.subheader("💡 情侣投入本金与当前权益追踪")
    col_eq1, col_eq2 = st.columns([3, 2])
    
    with col_eq1:
        # 格式化输出表格
        disp_eq = df_equity.copy()
        disp_eq['累计投入本金'] = disp_eq['累计投入本金'].apply(lambda x: f"${x:,.2f}")
        disp_eq['资金池占比 (%)'] = disp_eq['资金池占比 (%)'].apply(lambda x: f"{x:.2f}%")
        disp_eq['当前权益市值'] = disp_eq['当前权益市值'].apply(lambda x: f"${x:,.2f}")
        disp_eq['累计盈亏'] = disp_eq['累计盈亏'].apply(lambda x: f"${x:,.2f}")
        disp_eq['个人收益率 (%)'] = disp_eq['个人收益率 (%)'].apply(lambda x: f"{x:+.2f}%")
        
        st.dataframe(disp_eq, use_container_width=True, hide_index=True)
        st.caption("📌 说明：双方将资金打入统一的资金池后，系统按各自累计投入的本金占比分流计算池子总市值与投资盈亏。")

    with col_eq2:
        fig_equity = px.pie(df_equity, values='当前权益市值', names='成员', title="情侣权益市值分布", hole=0.4,
                            color_discrete_sequence=['#3182ce', '#ed64a6'])
        st.plotly_chart(fig_equity, use_container_width=True)

    st.divider()

    # 资金池标的分布与图表
    st.subheader("📦 资金池投资标的明细与资产分布")
    
    # 构造包含“现金”在内的完整资产大类数据表，用于真实呈现配置
    all_asset_types = []
    if pool_cash_balance > 0:
        all_asset_types.append({'asset_type': '货币基金/现金', 'market_value': pool_cash_balance, 'platform': '资金池现金'})
        
    if not df_portfolio.empty:
        for _, r in df_portfolio.iterrows():
            all_asset_types.append({'asset_type': r['asset_type'], 'market_value': r['market_value'], 'platform': r['platform']})
            
    df_all_assets = pd.DataFrame(all_asset_types)

    if not df_portfolio.empty:
        st.dataframe(
            df_portfolio[['name', 'asset_type', 'platform', 'quantity', 'avg_cost', 'current_price', 'total_cost', 'market_value', 'profit', 'profit_rate']].style.format({
                'avg_cost': '${:,.4f}',
                'current_price': '${:,.4f}',
                'total_cost': '${:,.2f}',
                'market_value': '${:,.2f}',
                'profit': '${:,.2f}',
                'profit_rate': '{:+.2f}%'
            }),
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("💡 当前资金池暂未购买投资标的，资金全额留存在资金池现金中。")

    if not df_all_assets.empty:
        g1, g2 = st.columns(2)
        with g1:
            fig_type = px.pie(df_all_assets, values='market_value', names='asset_type', title="全盘资产类别分布 (含资金池现金)", hole=0.4)
            st.plotly_chart(fig_type, use_container_width=True)
        with g2:
            fig_plat = px.pie(df_all_assets, values='market_value', names='platform', title="平台分布 (TNG/MooMoo/券商)", hole=0.4)
            st.plotly_chart(fig_plat, use_container_width=True)

    # 手动净值校准区 (针对 TNG 黄金 / MooMoo Maybank MMF 等)
    with st.expander("⚙️ 手动更新非公开 API 标的单价/净值 (如 TNG e-Mas 黄金 / MooMoo 货币基金)"):
        if not df_portfolio.empty:
            non_api_df = df_portfolio[df_portfolio['asset_type'].isin(["黄金/贵金属", "货币基金/现金", "其他"])]
            if not non_api_df.empty:
                m_col1, m_col2, m_col3 = st.columns(3)
                selected_key = m_col1.selectbox("选择标的", non_api_df['key'].tolist())
                curr_val = manual_prices.get(selected_key, float(non_api_df[non_api_df['key']==selected_key]['current_price'].iloc[0]))
                new_val = m_col2.number_input("最新实时单价 / 净值", value=float(curr_val), format="%.4f")
                if m_col3.button("更新最新单价"):
                    update_manual_price(selected_key, new_val)
                    st.success("净值已校准，资金池总资产与双方权益已同步重算！")
                    st.rerun()

    st.divider()

    # 永久投资组合智能再平衡模块 (整合在同一页面)
    st.subheader("⚖️ 资金池永久投资组合 (Permanent Portfolio) 智能再平衡")
    st.caption("自动归类资金池中的所有资产（含现金与股票/黄金/货基），按标准 25% 目标配比给出买卖决策：")

    perm_map = {
        "股票/ETF": "股票 (Stock)",
        "黄金/贵金属": "黄金 (Gold)",
        "货币基金/现金": "现金/货币基金 (Cash/MMF)",
        "加密货币": "股票 (Stock)",
        "其他": "现金/货币基金 (Cash/MMF)"
    }

    if not df_all_assets.empty:
        df_all_assets['perm_category'] = df_all_assets['asset_type'].map(perm_map)
        perm_summary = df_all_assets.groupby('perm_category')['market_value'].sum().reset_index()
    else:
        perm_summary = pd.DataFrame(columns=['perm_category', 'market_value'])

    all_categories = ["股票 (Stock)", "黄金 (Gold)", "现金/货币基金 (Cash/MMF)", "债券 (Bond)"]
    existing_cats = perm_summary['perm_category'].tolist() if not perm_summary.empty else []
    for cat in all_categories:
        if cat not in existing_cats:
            perm_summary = pd.concat([perm_summary, pd.DataFrame([{'perm_category': cat, 'market_value': 0.0}])], ignore_index=True)

    perm_summary['current_ratio'] = perm_summary['market_value'] / total_pool_net_worth if total_pool_net_worth > 0 else 0
    perm_summary['target_ratio'] = 0.25
    perm_summary['target_value'] = total_pool_net_worth * 0.25
    perm_summary['rebalance_amount'] = perm_summary['target_value'] - perm_summary['market_value']

    reb_df = perm_summary.copy()
    reb_df['当前市值'] = reb_df['market_value'].apply(lambda x: f"${x:,.2f}")
    reb_df['当前占比'] = reb_df['current_ratio'].apply(lambda x: f"{x*100:.2f}%")
    reb_df['目标占比'] = "25.00%"
    reb_df['目标市值'] = reb_df['target_value'].apply(lambda x: f"${x:,.2f}")
    reb_df['建议调仓金额'] = reb_df['rebalance_amount'].apply(
        lambda x: f"🟢 建议买入 ${x:,.2f}" if x > 0 else (f"🔴 建议卖出 ${abs(x):,.2f}" if x < 0 else "✅ 保持均衡")
    )

    st.dataframe(
        reb_df[['perm_category', '当前市值', '当前占比', '目标占比', '目标市值', '建议调仓金额']],
        use_container_width=True,
        hide_index=True
    )

# -----------------------------------------------------------------------------
# 5. 页面 2: 资金池注资/出金 (情侣将现金打入资金池)
# -----------------------------------------------------------------------------
elif menu == "💵 资金池注资/出金":
    st.title("💵 资金池资金打入 / 提取")
    st.caption("记录男方或女方将个人资金存入共享资金池，或从资金池中提取本金的流水。系统将据此实时更变双方的份额比例。")
    
    with st.form("cap_entry_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            member = st.selectbox("1. 操作成员", ["👦 男方", "👧 女方"])
            type_val = st.selectbox("2. 资金流向", ["注资/存入本金", "撤资/提取本金"])
        with col2:
            date_val = st.date_input("3. 变动日期", datetime.now())
            amount = st.number_input("4. 金额", min_value=0.01, value=1000.0, format="%.2f")
        with col3:
            notes = st.text_input("5. 备注 (选填)", placeholder="例如：3月工资定投，发奖金等")
            
        submitted = st.form_submit_button("🚀 提交并更新资金池", use_container_width=True)
        if submitted:
            save_capital_record(date_val.strftime("%Y-%m-%d"), member, type_val, amount, notes)
            st.success(f"✅ 已成功存入 {member} 的 {type_val} 记录 ${amount:,.2f}！共享资金池与份额比例已同步重算。")

# -----------------------------------------------------------------------------
# 6. 页面 3: 资金池标的买卖 (使用资金池中的现金购买资产)
# -----------------------------------------------------------------------------
elif menu == "📈 资金池标的买卖":
    st.title("📈 资金池标的投资交易")
    st.caption("由共享资金池出资买入/卖出各种资产（支持 TNG 黄金、MooMoo 货币基金、美股/港股等）。")
    st.info(f"💡 当前资金池可用现金余额: **${pool_cash_balance:,.2f}**")
    
    with st.form("trade_entry_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            asset_type = st.selectbox("1. 资产类型", ["股票/ETF", "黄金/贵金属", "货币基金/现金", "加密货币", "其他"])
            tx_type = st.selectbox("2. 交易类型", ["买入", "卖出"])
            date_val = st.date_input("3. 交易日期", datetime.now())
            
        with col2:
            platform = st.text_input("4. 投资平台", placeholder="例如: TNG e-Mas, MooMoo, 证券行")
            name = st.text_input("5. 标的名称", placeholder="例如: TNG 黄金, Maybank MMF, 苹果股票")
            symbol = st.text_input("6. 标的代码 (选填)", placeholder="美股/港股代码(如 AAPL)，黄金/货基留空")
            
        with col3:
            price = st.number_input("7. 成交单价 / 单位净值", min_value=0.0, format="%.4f", value=1.0000)
            quantity = st.number_input("8. 数量 / 克数 / 份额", min_value=0.0, format="%.4f", value=1.0000)
            notes = st.text_input("9. 备注 (选填)", placeholder="例如：TNG 促销买入等")
            
        calculated_total = price * quantity
        st.markdown(f"**💡 成交总金额: ${calculated_total:,.2f}**")
        
        submitted = st.form_submit_button("🚀 执行资金池交易并保存", use_container_width=True)
        if submitted:
            if not platform or not name:
                st.error("⚠️ 平台名称与标的名称为必填项！")
            elif tx_type == "买入" and calculated_total > pool_cash_balance:
                st.error(f"⚠️ 资金池可用现金不足！当前余额为 ${pool_cash_balance:,.2f}，需要 ${calculated_total:,.2f}。请先注资。")
            else:
                save_pool_transaction(
                    date_val.strftime("%Y-%m-%d"),
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
                st.success(f"✅ 成功执行资金池交易: {name} ({tx_type}) ${calculated_total:,.2f}！")

# -----------------------------------------------------------------------------
# 7. 页面 4: 资金与交易记录管理 (提供编辑与一键剔除，全局实时联动)
# -----------------------------------------------------------------------------
elif menu == "📋 资金与交易记录管理":
    st.title("📋 资金与交易记录管理")
    st.caption("此处可管理两类流水：1. 情侣注入资金池流水；2. 资金池买卖标的流水。均支持实时编辑与一键剔除，全盘自动联动重新计算。")
    
    tab1, tab2 = st.tabs(["💵 资金池注资/出金记录", "📈 资金池标的交易记录"])
    
    # --- Tab 1: 资金池流水管理 ---
    with tab1:
        if df_cap.empty:
            st.info("💡 暂无资金池注资/出金记录。")
        else:
            st.dataframe(df_cap, use_container_width=True, hide_index=True)
            st.divider()
            
            cap_ids = df_cap['id'].tolist()
            c_cap_edit, c_cap_del = st.columns(2)
            
            with c_cap_del:
                st.subheader("🗑️ 剔除指定资金注资/出金")
                del_c_id = st.selectbox("选择要剔除的资金流水 ID", cap_ids, key="del_cap_sel")
                row_c = df_cap[df_cap['id'] == del_c_id].iloc[0]
                
                st.warning(f"即将剔除: ID {del_c_id} | {row_c['date']} | {row_c['member']} | {row_c['type']} ${row_c['amount']:,.2f}")
                if st.button("确认剔除该记录", key="btn_del_cap", type="primary"):
                    delete_capital_record(del_c_id)
                    st.success(f"✅ 资金流水 ID {del_c_id} 已剔除，系统已重新重算双方本金占比与总资产！")
                    st.rerun()

            with c_cap_edit:
                st.subheader("✏️ 编辑指定资金注资/出金")
                edit_c_id = st.selectbox("选择要修改的资金流水 ID", cap_ids, key="edit_cap_sel")
                row_ce = df_cap[df_cap['id'] == edit_c_id].iloc[0]
                
                with st.form("edit_cap_form"):
                    ec_member = st.selectbox("成员", ["👦 男方", "👧 女方"], index=0 if row_ce['member'] == "👦 男方" else 1)
                    ec_type = st.selectbox("类型", ["注资/存入本金", "撤资/提取本金"], index=0 if row_ce['type'] in ["注资/存入本金", "存入"] else 1)
                    ec_date = st.date_input("日期", datetime.strptime(row_ce['date'], "%Y-%m-%d"))
                    ec_amt = st.number_input("金额", value=float(row_ce['amount']), format="%.2f")
                    ec_notes = st.text_input("备注", value=row_ce['notes'] if row_ce['notes'] else "")
                    
                    if st.form_submit_button("保存修改"):
                        update_capital_record(edit_c_id, ec_date.strftime("%Y-%m-%d"), ec_member, ec_type, ec_amt, ec_notes)
                        st.success(f"✅ 资金流水 ID {edit_c_id} 已成功修改！")
                        st.rerun()

    # --- Tab 2: 标的交易流水管理 ---
    with tab2:
        if df_tx.empty:
            st.info("💡 暂无资金池投资标的买卖记录。")
        else:
            st.dataframe(df_tx, use_container_width=True, hide_index=True)
            st.divider()
            
            tx_ids = df_tx['id'].tolist()
            c_tx_edit, c_tx_del = st.columns(2)
            
            with c_tx_del:
                st.subheader("🗑️ 剔除指定投资标的交易")
                del_t_id = st.selectbox("选择要剔除的交易 ID", tx_ids, key="del_tx_sel")
                row_t = df_tx[df_tx['id'] == del_t_id].iloc[0]
                
                st.warning(f"即将剔除: ID {del_t_id} | {row_t['date']} | {row_t['platform']} - {row_t['name']} | {row_t['tx_type']} ${row_t['total_amount']:,.2f}")
                if st.button("确认剔除该交易", key="btn_del_tx", type="primary"):
                    delete_pool_transaction(del_t_id)
                    st.success(f"✅ 标的交易 ID {del_t_id} 已彻底剔除，全盘现金流与持仓已实时重算！")
                    st.rerun()

            with c_tx_edit:
                st.subheader("✏️ 编辑指定投资标的交易")
                edit_t_id = st.selectbox("选择要修改的交易 ID", tx_ids, key="edit_tx_sel")
                row_te = df_tx[df_tx['id'] == edit_t_id].iloc[0]
                
                with st.form("edit_tx_form"):
                    et_date = st.date_input("日期", datetime.strptime(row_te['date'], "%Y-%m-%d"))
                    et_asset_type = st.selectbox("资产类型", ["股票/ETF", "黄金/贵金属", "货币基金/现金", "加密货币", "其他"],
                                                 index=["股票/ETF", "黄金/贵金属", "货币基金/现金", "加密货币", "其他"].index(row_te['asset_type']) if row_te['asset_type'] in ["股票/ETF", "黄金/贵金属", "货币基金/现金", "加密货币", "其他"] else 0)
                    et_platform = st.text_input("平台", value=row_te['platform'])
                    et_name = st.text_input("标的名称", value=row_te['name'])
                    et_symbol = st.text_input("代码", value=row_te['symbol'] if row_te['symbol'] else "")
                    et_tx_type = st.selectbox("交易类型", ["买入", "卖出"], index=0 if row_te['tx_type'] == "买入" else 1)
                    et_price = st.number_input("单价", value=float(row_te['price']), format="%.4f")
                    et_qty = st.number_input("数量", value=float(row_te['quantity']), format="%.4f")
                    et_notes = st.text_input("备注", value=row_te['notes'] if row_te['notes'] else "")
                    
                    if st.form_submit_button("保存交易修改"):
                        update_pool_transaction(
                            edit_t_id,
                            et_date.strftime("%Y-%m-%d"),
                            et_asset_type,
                            et_platform,
                            et_symbol.upper().strip() if et_symbol else "",
                            et_name.strip(),
                            et_tx_type,
                            et_price,
                            et_qty,
                            et_price * et_qty,
                            et_notes
                        )
                        st.success(f"✅ 标的交易 ID {edit_t_id} 修改成功！")
                        st.rerun()
