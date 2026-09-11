import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import sqlite3
from datetime import datetime

# -----------------------------------------------------------------------------
# 1. 页面基本配置与现代 UI 样式注入
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="👩‍❤️‍👨 Our Portfolio | 情侣实时投资看板",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义 CSS 提升 UI 质感（卡片阴影、渐变色彩、圆形边框）
st.markdown("""
    <style>
    .stApp {
        background-color: #f8f9fa;
    }
    .metric-card {
        background: white;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        border: 1px solid #edf2f7;
        text-align: center;
    }
    .metric-value {
        font-size: 26px;
        font-weight: 700;
        color: #2d3748;
    }
    .metric-label {
        font-size: 14px;
        color: #718096;
        margin-bottom: 8px;
    }
    </style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. 数据库初始化与持久化存储
# -----------------------------------------------------------------------------
def get_db():
    conn = sqlite3.connect("portfolio.db", check_same_thread=False)
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS deposits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    person TEXT,
                    type TEXT,
                    amount REAL,
                    nav REAL,
                    units REAL,
                    date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT,
                    action TEXT,
                    qty REAL,
                    price REAL,
                    date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cash (
                    id INTEGER PRIMARY KEY,
                    balance REAL)''')
    
    # 初始化账户现金（如首次运行设为 0）
    c.execute("SELECT COUNT(*) FROM cash")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO cash VALUES (1, 0.0)")
    conn.commit()

init_db()

# -----------------------------------------------------------------------------
# 3. 实时行情抓取与计算引擎
# -----------------------------------------------------------------------------
@st.cache_data(ttl=60)  # 60秒自动缓存，避免频繁 API 调用
def fetch_realtime_price(ticker):
    try:
        data = yf.Ticker(ticker)
        price = data.fast_info.last_price
        return price if price else 0.0
    except Exception:
        return 0.0

def get_portfolio_summary():
    conn = get_db()
    
    # 算总发行份额与个人份额
    df_dep = pd.read_sql("SELECT * FROM deposits", conn)
    if df_dep.empty:
        total_units = 100.0
        my_units = 50.0
        her_units = 50.0
    else:
        my_units = df_dep[df_dep['person'] == '我']['units'].sum()
        her_units = df_dep[df_dep['person'] == '女友']['units'].sum()
        total_units = my_units + her_units
        if total_units <= 0:
            total_units = 1.0

    # 计算未投资现金
    cash_balance = pd.read_sql("SELECT balance FROM cash WHERE id=1", conn).iloc[0]['balance']
    
    # 计算持仓标的实时价值
    df_trades = pd.read_sql("SELECT * FROM trades", conn)
    holdings = {}
    if not df_trades.empty:
        for _, row in df_trades.iterrows():
            t = row['ticker']
            q = row['qty'] if row['action'] == '买入' else -row['qty']
            holdings[t] = holdings.get(t, 0.0) + q

    stock_val = 0.0
    holdings_detail = []
    for ticker, qty in holdings.items():
        if qty > 0:
            p = fetch_realtime_price(ticker)
            val = qty * p
            stock_val += val
            holdings_detail.append({"代码": ticker, "持仓数量": qty, "实时单价": p, "当前总市值": val})

    total_market_val = cash_balance + stock_val
    current_nav = total_market_val / total_units if total_units > 0 else 1.0
    
    return {
        "total_val": total_market_val,
        "cash_balance": cash_balance,
        "stock_val": stock_val,
        "nav": current_nav,
        "total_units": total_units,
        "my_units": my_units,
        "her_units": her_units,
        "my_equity": my_units * current_nav,
        "her_equity": her_units * current_nav,
        "holdings_df": pd.DataFrame(holdings_detail)
    }

summary = get_portfolio_summary()

# -----------------------------------------------------------------------------
# 4. 顶部核心指标看板 (KPI Cards)
# -----------------------------------------------------------------------------
st.title("👩‍❤️‍👨 Our Capital | 情侣共同资产实时看板")
st.caption("实时拉取全球标的行情 • 自动按基金净值（NAV）折算个人份额")

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.markdown(f'''
    <div class="metric-card">
        <div class="metric-label">💼 组合实时总市值</div>
        <div class="metric-value">￥{summary['total_val']:,.2f}</div>
    </div>
    ''', unsafe_allow_html=True)

with col2:
    st.markdown(f'''
    <div class="metric-card">
        <div class="metric-label">🎯 当前单位净值 (NAV)</div>
        <div class="metric-value">{summary['nav']:.4f}</div>
    </div>
    ''', unsafe_allow_html=True)

with col3:
    st.markdown(f'''
    <div class="metric-card">
        <div class="metric-label">💙 我的权益金额</div>
        <div class="metric-value" style="color:#3182ce;">￥{summary['my_equity']:,.2f}</div>
        <small style="color:#718096;">份额: {summary['my_units']:,.2f}</small>
    </div>
    ''', unsafe_allow_html=True)

with col4:
    st.markdown(f'''
    <div class="metric-card">
        <div class="metric-label">🩷 女友权益金额</div>
        <div class="metric-value" style="color:#d53f8c;">￥{summary['her_equity']:,.2f}</div>
        <small style="color:#718096;">份额: {summary['her_units']:,.2f}</small>
    </div>
    ''', unsafe_allow_html=True)

st.divider()

# -----------------------------------------------------------------------------
# 5. 图表分析与持仓明细
# -----------------------------------------------------------------------------
left_col, right_col = st.columns([1, 1])

with left_col:
    st.subheader("📊 实时资产配置分布")
    chart_data = []
    if summary['cash_balance'] > 0:
        chart_data.append({"类别": "未投资现金", "金额": summary['cash_balance']})
    
    if not summary['holdings_df'].empty:
        for _, row in summary['holdings_df'].iterrows():
            chart_data.append({"类别": row['代码'], "金额": row['当前总市值']})
            
    if chart_data:
        df_pie = pd.DataFrame(chart_data)
        fig = px.pie(df_pie, names='类别', values='金额', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
        fig.update_layout(margin=dict(t=20, b=20, l=20, r=20))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("暂无持仓或现金数据，请在侧边栏新增存付款或买入标的。")

with right_col:
    st.subheader("📋 实时持仓明细")
    if not summary['holdings_df'].empty:
        st.dataframe(
            summary['holdings_df'].style.format({
                "实时单价": "￥{:,.2f}",
                "当前总市值": "￥{:,.2f}",
                "持仓数量": "{:,.4f}"
            }),
            use_container_width=True,
            height=300
        )
    else:
        st.write("目前尚未持有任何股票/ETF/加密货币标的。")

# -----------------------------------------------------------------------------
# 6. 侧边栏交互：存取款与买卖交易操作
# -----------------------------------------------------------------------------
st.sidebar.header("⚙️ 数据录入面板")

action_type = st.sidebar.radio("选择操作类型", ["新增存取款 (Cash In/Out)", "录入买卖标的 (Trade)"])

conn = get_db()
c = conn.cursor()

if action_type == "新增存取款 (Cash In/Out)":
    st.sidebar.subheader("➕ 存取款录入")
    with st.sidebar.form("deposit_form"):
        person = st.selectbox("出资人", ["我", "女友"])
        dep_type = st.selectbox("类型", ["存入", "取出"])
        amount = st.number_input("金额 (￥)", min_value=10.0, step=100.0)
        submitted = st.form_submit_button("确认提交")
        
        if submitted:
            current_nav = summary['nav']
            # 根据当期净值，计算新增/减少份额
            new_units = amount / current_nav if dep_type == "存入" else -(amount / current_nav)
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # 插入流水记录
            c.execute("INSERT INTO deposits (person, type, amount, nav, units, date) VALUES (?, ?, ?, ?, ?, ?)",
                      (person, dep_type, amount if dep_type == "存入" else -amount, current_nav, new_units, date_str))
            
            # 更新账户现金
            new_cash = summary['cash_balance'] + (amount if dep_type == "存入" else -amount)
            c.execute("UPDATE cash SET balance = ? WHERE id = 1", (new_cash,))
            conn.commit()
            st.success(f"成功录入！按当前净值 {current_nav:.4f}，折算份额变化：{new_units:+.2f} 份")
            st.rerun()

elif action_type == "录入买卖标的 (Trade)":
    st.sidebar.subheader("📈 买卖交易录入")
    with st.sidebar.form("trade_form"):
        ticker = st.text_input("交易代码 (例如 AAPL, BTC-USD, 2822.HK)", value="AAPL")
        trade_action = st.selectbox("方向", ["买入", "卖出"])
        trade_qty = st.number_input("交易数量 (股/单位)", min_value=0.0001, step=1.0)
        trade_price = st.number_input("成交单价 (￥/$)", min_value=0.01, step=1.0)
        submitted_trade = st.form_submit_button("确认记录交易")
        
        if submitted_trade:
            total_cost = trade_qty * trade_price
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            if trade_action == "买入" and total_cost > summary['cash_balance']:
                st.error(f"账户现金不足！买入需要 ￥{total_cost:,.2f}，当前可用现金 ￥{summary['cash_balance']:,.2f}")
            else:
                # 记录买卖交易
                c.execute("INSERT INTO trades (ticker, action, qty, price, date) VALUES (?, ?, ?, ?, ?)",
                          (ticker.upper(), trade_action, trade_qty, trade_price, date_str))
                
                # 更新现金余额
                cash_change = -total_cost if trade_action == "买入" else total_cost
                new_cash = summary['cash_balance'] + cash_change
                c.execute("UPDATE cash SET balance = ? WHERE id = 1", (new_cash,))
                conn.commit()
                st.success(f"已记录 {trade_action} {ticker.upper()} {trade_qty} 股，现金变动 ￥{cash_change:+,.2f}")
                st.rerun()
