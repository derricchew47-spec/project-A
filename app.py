import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
from datetime import datetime
import yfinance as yf

# -----------------------------------------------------------------------------
# 1. 数据库与核心数据处理
# -----------------------------------------------------------------------------
DB_FILE = "portfolio_pool_cute.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
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
    c.execute('''
        CREATE TABLE IF NOT EXISTS manual_prices (
            symbol_or_name TEXT PRIMARY KEY,
            last_price REAL NOT NULL,
            updated_at TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

def load_capital():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM capital_ledger ORDER BY date DESC", conn)
    conn.close()
    return df

def save_capital(date, member, type_val, amount, notes):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO capital_ledger (date, member, type, amount, notes) VALUES (?, ?, ?, ?, ?)",
              (date, member, type_val, amount, notes))
    conn.commit()
    conn.close()

def load_tx():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM pool_transactions ORDER BY date DESC", conn)
    conn.close()
    return df

def save_tx(date, asset_type, platform, symbol, name, tx_type, price, quantity, total_amount, notes):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO pool_transactions (date, asset_type, platform, symbol, name, tx_type, price, quantity, total_amount, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (date, asset_type, platform, symbol, name, tx_type, price, quantity, total_amount, notes))
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
def fetch_price(symbol, asset_type, default_price):
    if asset_type in ["股票/ETF", "加密货币"] and symbol:
        try:
            ticker = yf.Ticker(symbol)
            fast_info = ticker.fast_info
            if hasattr(fast_info, 'last_price') and fast_info.last_price is not None:
                return float(fast_info.last_price)
        except Exception:
            pass
    return default_price

# -----------------------------------------------------------------------------
# 2. 可爱风 UI 主题配置
# -----------------------------------------------------------------------------
st.set_page_config(page_title="🌸 Our Money Pool", layout="wide", initial_sidebar_state="expanded")
init_db()

st.markdown("""
<style>
    .stApp { background-color: #fcf8f9; }
    .cute-card {
        background: #ffffff;
        border-radius: 18px;
        padding: 18px;
        box-shadow: 0 8px 20px rgba(255, 182, 193, 0.15);
        border: 2px solid #ffe6ea;
        text-align: center;
        margin-bottom: 12px;
    }
    .cute-title { font-size: 13px; color: #887880; font-weight: 600; }
    .cute-value { font-size: 22px; font-weight: 800; color: #ff5c8a; margin-top: 4px; }
    .asset-chip {
        background: #fff0f3;
        border-radius: 12px;
        padding: 12px;
        border-left: 5px solid #ff758f;
        margin-bottom: 8px;
    }
</style>
""", unsafe_allow_html=True)

# 色彩库：马卡龙柔和系列
COLORS_MEMBERS = ['#FF85A1', '#4EA8DE']  # 娇嫩粉 & 天空蓝
COLORS_ASSETS = ['#FF9AA2', '#FFB7B2', '#FFDAC1', '#E2F0CB', '#B5EAD7', '#C7CEEA'] # 马卡龙彩虹
COLORS_PLATFORMS = ['#A8DADC', '#F4A261', '#E76F51', '#2A9D8F', '#E9C46A'] # 活力糖果

# -----------------------------------------------------------------------------
# 3. 核心数据汇总
# -----------------------------------------------------------------------------
menu = st.sidebar.radio("✨ 导航菜单", ["🍰 共享资金池总览", "💵 资金存入/取出", "📈 买卖标的记账"])

df_cap = load_capital()
df_tx = load_tx()
manual_prices = get_manual_prices()

# 计算投入
capital_summary = {'👦 男方': 0.0, '👧 女方': 0.0}
if not df_cap.empty:
    for _, r in df_cap.iterrows():
        m, amt = r['member'], r['amount']
        if r['type'] in ['注资/存入本金', '存入']:
            capital_summary[m] += amt
        elif r['type'] in ['撤资/提取本金', '取出']:
            capital_summary[m] -= amt

total_capital = sum(capital_summary.values())

# 计算持仓
holdings = {}
cash_spent = 0.0
if not df_tx.empty:
    for _, r in df_tx.iterrows():
        k = r['symbol'] if r['symbol'] and r['symbol'].strip() else r['name']
        if k not in holdings:
            holdings[k] = {'name': r['name'], 'symbol': r['symbol'], 'type': r['asset_type'], 'plat': r['platform'], 'qty': 0.0, 'cost': 0.0}
        
        qty, amt = r['quantity'], r['total_amount']
        if r['tx_type'] == '买入':
            holdings[k]['qty'] += qty
            holdings[k]['cost'] += amt
            cash_spent += amt
        elif r['tx_type'] == '卖出':
            holdings[k]['qty'] -= qty
            holdings[k]['cost'] -= amt
            cash_spent -= amt

portfolio = []
total_assets_mv = 0.0
for k, item in holdings.items():
    if item['qty'] > 0.0001:
        lp = manual_prices.get(k, item['cost'] / item['qty'] if item['qty'] > 0 else 0)
        cp = fetch_price(item['symbol'], item['type'], lp)
        mv = cp * item['qty']
        total_assets_mv += mv
        portfolio.append({
            'key': k, 'name': item['name'], 'type': item['type'], 'plat': item['plat'],
            'qty': item['qty'], 'price': cp, 'cost': item['cost'], 'mv': mv, 'profit': mv - item['cost']
        })

df_portfolio = pd.DataFrame(portfolio)
cash_balance = total_capital - cash_spent
total_net_worth = cash_balance + total_assets_mv
total_profit = total_net_worth - total_capital

# 情侣权益表 (仅保留：成员、累计投入本金、资金池占比、当前权益市值)
equity_data = []
for m in ['👦 男方', '👧 女方']:
    cap = capital_summary[m]
    pct = (cap / total_capital * 100) if total_capital > 0 else 0.0
    equity_val = total_net_worth * (pct / 100.0)
    equity_data.append({
        '成员': m,
        '累计投入本金': f"${cap:,.2f}",
        '资金池占比 (%)': f"{pct:.1f}%",
        '当前权益市值': f"${equity_val:,.2f}"
    })
df_equity = pd.DataFrame(equity_data)

# -----------------------------------------------------------------------------
# 4. 页面 1: 🍰 共享资金池总览
# -----------------------------------------------------------------------------
if menu == "🍰 共享资金池总览":
    st.title("🌸 小情侣的资金池资产看板")
    
    # 顶部 4 个可爱 KPI 卡片
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f'<div class="cute-card"><div class="cute-title">🏦 资金池总资产</div><div class="cute-value">${total_net_worth:,.2f}</div></div>', unsafe_allow_html=True)
    with k2:
        st.markdown(f'<div class="cute-card"><div class="cute-title">💵 可用现金余额</div><div class="cute-value" style="color:#2a9d8f;">${cash_balance:,.2f}</div></div>', unsafe_allow_html=True)
    with k3:
        st.markdown(f'<div class="cute-card"><div class="cute-title">📈 标的总市值</div><div class="cute-value" style="color:#e76f51;">${total_assets_mv:,.2f}</div></div>', unsafe_allow_html=True)
    with k4:
        st.markdown(f'<div class="cute-card"><div class="cute-title">✨ 累计盈亏</div><div class="cute-value" style="color:{"#ff5c8a" if total_profit>=0 else "#2b2d42"};">${total_profit:,.2f}</div></div>', unsafe_allow_html=True)

    st.markdown("---")

    # 情侣出资比重 (删除了个人收益率，极简表格 + 可爱粉蓝饼图)
    col_e1, col_e2 = st.columns([3, 2])
    with col_e1:
        st.subheader("👩‍❤️‍👨 两人出资与权益份额")
        st.dataframe(df_equity, use_container_width=True, hide_index=True)
    with col_e2:
        fig_mem = px.pie(
            df_equity, values=[capital_summary['👦 男方'], capital_summary['👧 女方']], 
            names=['👦 男方', '👧 女方'], hole=0.55,
            color_discrete_sequence=COLORS_MEMBERS, title="💕 本金出资比例"
        )
        fig_mem.update_traces(textinfo='percent+label', marker=dict(line=dict(color='#ffffff', width=3)))
        fig_mem.update_layout(showlegend=False, margin=dict(t=30, b=0, l=0, r=0))
        st.plotly_chart(fig_mem, use_container_width=True)

    st.markdown("---")

    # 可视化图表区 (三个图表完全不同颜色 & 3D 环形感)
    st.subheader("🎨 资产配置与分布可视化")
    
    # 构造全盘资产列表 (含现金)
    all_assets = [{'type': '货币基金/现金', 'mv': cash_balance, 'plat': '资金池现金'}]
    if not df_portfolio.empty:
        for _, r in df_portfolio.iterrows():
            all_assets.append({'type': r['type'], 'mv': r['mv'], 'plat': r['plat']})
    df_all = pd.DataFrame(all_assets)

    g1, g2 = st.columns(2)
    with g1:
        fig_type = px.pie(
            df_all, values='mv', names='type', hole=0.5,
            color_discrete_sequence=COLORS_ASSETS, title="🍰 资产类别占比 (含现金)"
        )
        fig_type.update_traces(textinfo='percent+label', marker=dict(line=dict(color='#ffffff', width=3)))
        st.plotly_chart(fig_type, use_container_width=True)

    with g2:
        fig_plat = px.pie(
            df_all, values='mv', names='plat', hole=0.5,
            color_discrete_sequence=COLORS_PLATFORMS, title="🛍️ 投资平台分布"
        )
        fig_plat.update_traces(textinfo='percent+label', marker=dict(line=dict(color='#ffffff', width=3)))
        st.plotly_chart(fig_plat, use_container_width=True)

    st.markdown("---")

    # 精简版“持仓标的”卡片视图 (去除了大片密密麻麻的表格文字，用可视化卡片呈现)
    st.subheader("📦 当前投资标的概览")
    if df_portfolio.empty:
        st.info("💡 目前池子里都是现金哦，还没有买入任何投资标的～")
    else:
        c_list = st.columns(3)
        for idx, r in df_portfolio.iterrows():
            with c_list[idx % 3]:
                profit_color = "#ff5c8a" if r['profit'] >= 0 else "#2a9d8f"
                st.markdown(f"""
                <div class="asset-chip">
                    <div style="display:flex; justify-content:space-between; font-weight:700;">
                        <span>{r['name']} ({r['plat']})</span>
                        <span style="color:{profit_color};">${r['mv']:,.2f}</span>
                    </div>
                    <div style="font-size:12px; color:#666; margin-top:4px;">
                        数量: {r['qty']:.2f} | 现价: ${r['price']:.2f} | 盈亏: <b style="color:{profit_color};">${r['profit']:,.2f}</b>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        # 非公开 API 校准折叠框
        with st.expander("⚙️ 手动更新净值/单价 (如 TNG 黄金 / MooMoo 货币基金)"):
            m_col1, m_col2, m_col3 = st.columns(3)
            selected_key = m_col1.selectbox("选择标的", df_portfolio['key'].tolist())
            curr_v = manual_prices.get(selected_key, float(df_portfolio[df_portfolio['key']==selected_key]['price'].iloc[0]))
            new_v = m_col2.number_input("最新单价/净值", value=float(curr_v), format="%.4f")
            if m_col3.button("✨ 更新单价"):
                update_manual_price(selected_key, new_v)
                st.success("已更新价格！")
                st.rerun()

    st.markdown("---")

    # ⚖️ 极简永久投资组合调仓
    st.subheader("⚖️ 智能调仓建议 (永久投资组合 25%)")
    perm_map = {"股票/ETF": "股票", "黄金/贵金属": "黄金", "货币基金/现金": "现金", "加密货币": "股票", "其他": "现金"}
    df_all['category'] = df_all['type'].map(perm_map)
    perm_df = df_all.groupby('category')['mv'].sum().reset_index()

    for c in ["股票", "黄金", "现金", "债券"]:
        if c not in perm_df['category'].tolist():
            perm_df = pd.concat([perm_df, pd.DataFrame([{'category': c, 'mv': 0.0}])], ignore_index=True)

    perm_df['target'] = total_net_worth * 0.25
    perm_df['diff'] = perm_df['target'] - perm_df['mv']
    
    reb_list = []
    for _, r in perm_df.iterrows():
        action = f"🟢 买入 ${r['diff']:,.2f}" if r['diff'] > 0 else (f"🔴 卖出 ${abs(r['diff']):,.2f}" if r['diff'] < 0 else "✅ 完美")
        reb_list.append({'类别': r['category'], '当前市值': f"${r['mv']:,.2f}", '目标市值 (25%)': f"${r['target']:,.2f}", '建议操作': action})
    
    st.dataframe(pd.DataFrame(reb_list), use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# 5. 页面 2: 💵 资金存入/取出
# -----------------------------------------------------------------------------
elif menu == "💵 资金存入/取出":
    st.title("💵 个人资金入池 / 提取")
    with st.form("cap_form", clear_on_submit=True):
        f1, f2 = st.columns(2)
        with f1:
            member = st.selectbox("出资人", ["👦 男方", "👧 女方"])
            type_val = st.selectbox("类型", ["注资/存入本金", "撤资/提取本金"])
        with f2:
            date_val = st.date_input("日期", datetime.now())
            amount = st.number_input("金额 ($)", min_value=1.0, value=1000.0)
        notes = st.text_input("备注", placeholder="如：3月工资存入")
        if st.form_submit_button("💗 确认提交", use_container_width=True):
            save_capital(date_val.strftime("%Y-%m-%d"), member, type_val, amount, notes)
            st.success("已成功记录并更新资金池份额！")
            st.rerun()

# -----------------------------------------------------------------------------
# 6. 页面 3: 📈 买卖标的记账
# -----------------------------------------------------------------------------
elif menu == "📈 买卖标的记账":
    st.title("📈 资金池购买投资标的")
    st.info(f"💡 当前资金池剩余现金：**${cash_balance:,.2f}**")
    with st.form("tx_form", clear_on_submit=True):
        t1, t2, t3 = st.columns(3)
        with t1:
            asset_type = st.selectbox("资产类型", ["股票/ETF", "黄金/贵金属", "货币基金/现金", "加密货币", "其他"])
            tx_type = st.selectbox("交易类型", ["买入", "卖出"])
            date_val = st.date_input("日期", datetime.now())
        with t2:
            platform = st.text_input("投资平台", placeholder="如: TNG e-Mas, MooMoo")
            name = st.text_input("标的名称", placeholder="如: TNG 黄金, Maybank MMF")
            symbol = st.text_input("代码 (选填)", placeholder="美股填写代码如 AAPL")
        with t3:
            price = st.number_input("单价", min_value=0.0001, value=1.0000, format="%.4f")
            quantity = st.number_input("数量 / 份额", min_value=0.0001, value=1.0000, format="%.4f")
            notes = st.text_input("备注", placeholder="选填")
            
        tot = price * quantity
        st.markdown(f"**💰 成交总额: ${tot:,.2f}**")
        if st.form_submit_button("🚀 确认记账", use_container_width=True):
            if tx_type == "买入" and tot > cash_balance:
                st.error("⚠️ 现金不足，请先向资金池存入本金！")
            else:
                save_tx(date_val.strftime("%Y-%m-%d"), asset_type, platform, symbol.upper().strip(), name.strip(), tx_type, price, quantity, tot, notes)
                st.success("记账成功！")
                st.rerun()
