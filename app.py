import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
import numpy as np
from datetime import datetime

# -----------------------------------------------------------------------------
# 1. 页面配置与 CSS 样式注入
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Our Capital | 情侣共同资产与永久投资组合看板",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .stApp {
        background-color: #f8f9fa;
    }
    .metric-card {
        background-color: #ffffff;
        border-radius: 12px;
        padding: 18px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.05);
        border: 1px solid #e9ecef;
        text-align: center;
    }
    .metric-title {
        font-size: 13px;
        color: #6c757d;
        margin-bottom: 6px;
        font-weight: 600;
    }
    .metric-val {
        font-size: 22px;
        font-weight: 700;
        color: #212529;
    }
    .metric-sub {
        font-size: 12px;
        color: #888888;
        margin-top: 4px;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. 数据库初始化与坏数据自愈
# -----------------------------------------------------------------------------
DB_NAME = "portfolio.db"

def get_db():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS deposits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    person TEXT, type TEXT, amount REAL, nav REAL, units REAL, date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT, category TEXT, action TEXT, qty REAL, price REAL, date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cash (
                    id INTEGER PRIMARY KEY, balance REAL)''')
    c.execute("SELECT COUNT(*) FROM cash")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO cash VALUES (1, 0.0)")
    
    # 兼容升级：动态补充 category 资产归类字段
    c.execute("PRAGMA table_info(trades)")
    cols = [col[1] for col in c.fetchall()]
    if 'category' not in cols and len(cols) > 0:
        try:
            c.execute("ALTER TABLE trades ADD COLUMN category TEXT DEFAULT '股票'")
        except:
            pass
    conn.commit()

init_db()

# 数据库自动修复（清理引发 nan / inf 的历史数据）
def auto_repair_data():
    conn = get_db()
    c = conn.cursor()
    df_dep = pd.read_sql("SELECT * FROM deposits", conn)
    if not df_dep.empty:
        has_bad = False
        for _, r in df_dep.iterrows():
            u = r['units']
            n = r['nav']
            if pd.isna(u) or np.isinf(u) or pd.isna(n) or n <= 0:
                has_bad = True
                break
        if has_bad:
            c.execute("DELETE FROM deposits WHERE units IS NULL OR nav <= 0 OR units = 'inf' OR units = 'nan'")
            conn.commit()

auto_repair_data()

# -----------------------------------------------------------------------------
# 3. 核心计算与行情获取
# -----------------------------------------------------------------------------
@st.cache_data(ttl=300)
def fetch_realtime_price(ticker):
    try:
        t = yf.Ticker(ticker)
        price = t.fast_info.last_price
        if price is None or price <= 0 or np.isnan(price):
            hist = t.history(period="1d")
            price = hist['Close'].iloc[-1] if not hist.empty else 0.0
        return float(price) if not np.isnan(price) else 0.0
    except Exception:
        return 0.0

def get_portfolio_summary():
    conn = get_db()
    df_dep = pd.read_sql("SELECT * FROM deposits", conn)
    
    total_principal = 0.0
    my_principal = 0.0
    her_principal = 0.0
    total_units = 0.0
    my_units = 0.0
    her_units = 0.0
    
    if not df_dep.empty:
        for _, r in df_dep.iterrows():
            amt = r['amount'] if r['type'] == '存入' else -r['amount']
            u = r['units'] if r['type'] == '存入' else -r['units']
            if np.isinf(u) or np.isnan(u):
                u = amt  # 安全降级防错
            
            total_principal += amt
            total_units += u
            if r['person'] == '我':
                my_principal += amt
                my_units += u
            else:
                her_principal += amt
                her_units += u

    if total_units <= 0 or np.isinf(total_units) or np.isnan(total_units):
        total_units = 0.0
        my_units = 0.0
        her_units = 0.0

    # 获取未投资现金余额
    cash_df = pd.read_sql("SELECT balance FROM cash WHERE id=1", conn)
    cash_balance = cash_df.iloc[0]['balance'] if not cash_df.empty else 0.0

    # 计算持仓标的市值与分类
    df_trades = pd.read_sql("SELECT * FROM trades", conn)
    holdings = {}
    
    if not df_trades.empty:
        for _, r in df_trades.iterrows():
            t = r['ticker'].upper()
            cat = r.get('category', '股票')
            if pd.isna(cat) or not cat:
                cat = '股票'
            q = r['qty'] if r['action'] == '买入' else -r['qty']
            
            if t not in holdings:
                holdings[t] = {"qty": 0.0, "category": cat}
            holdings[t]["qty"] += q

    stock_val = 0.0
    category_val = {"股票": 0.0, "债券": 0.0, "黄金": 0.0, "现金": cash_balance, "其他": 0.0}
    holdings_detail = []

    for ticker, info in holdings.items():
        qty = info["qty"]
        cat = info["category"]
        if qty > 0.0001:
            p = fetch_realtime_price(ticker)
            val = qty * p
            stock_val += val
            category_val[cat] = category_val.get(cat, 0.0) + val
            holdings_detail.append({
                "代码": ticker,
                "资产分类": cat,
                "持仓数量": qty,
                "实时单价 ($)": p,
                "当前市值 ($/￥)": val
            })

    total_market_val = cash_balance + stock_val
    
    # 核心 NAV 防除以零计算（彻底解决 NaN / inf）
    if total_units <= 0:
        current_nav = 1.0
    else:
        current_nav = total_market_val / total_units
        if np.isnan(current_nav) or np.isinf(current_nav) or current_nav <= 0:
            current_nav = 1.0

    # 计算个人权益金额
    if total_units > 0:
        my_equity = my_units * current_nav
        her_equity = her_units * current_nav
    else:
        my_equity = 0.0
        her_equity = 0.0

    # 计算整体累计收益与收益率
    total_profit = total_market_val - total_principal
    roi = (total_profit / total_principal * 100.0) if total_principal > 0 else 0.0

    return {
        "total_val": total_market_val,
        "cash_balance": cash_balance,
        "stock_val": stock_val,
        "total_principal": total_principal,
        "total_profit": total_profit,
        "roi": roi,
        "nav": current_nav,
        "my_equity": my_equity,
        "her_equity": her_equity,
        "my_units": my_units,
        "her_units": her_units,
        "my_principal": my_principal,
        "her_principal": her_principal,
        "holdings_df": pd.DataFrame(holdings_detail),
        "category_val": category_val
    }

summary = get_portfolio_summary()

# -----------------------------------------------------------------------------
# 4. 侧边栏（数据录入 & 管理）
# -----------------------------------------------------------------------------
st.sidebar.title("⚙️ 数据录入面板")
action = st.sidebar.radio("选择操作类型", ["新增存取款 (Cash In/Out)", "录入买卖标的 (Trade)", "🧹 坏数据修复与清空"])

conn = get_db()
c = conn.cursor()

if action == "新增存取款 (Cash In/Out)":
    st.sidebar.subheader("➕ 存取款录入")
    with st.sidebar.form("dep_form"):
        person = st.selectbox("出资人", ["我", "女友"])
        d_type = st.selectbox("类型", ["存入", "取出"])
        amt = st.number_input("金额 (￥/$)", min_value=1.0, value=1000.0, step=100.0)
        
        if st.form_submit_button("确认提交"):
            c_nav = summary['nav']
            if c_nav <= 0 or np.isnan(c_nav) or np.isinf(c_nav):
                c_nav = 1.0
                
            units = amt / c_nav if d_type == "存入" else -(amt / c_nav)
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            c.execute("INSERT INTO deposits (person, type, amount, nav, units, date) VALUES (?, ?, ?, ?, ?, ?)",
                      (person, d_type, amt if d_type == "存入" else -amt, c_nav, units, date_str))
            
            new_cash = summary['cash_balance'] + (amt if d_type == "存入" else -amt)
            c.execute("UPDATE cash SET balance = ? WHERE id = 1", (new_cash,))
            conn.commit()
            st.sidebar.success("✅ 存取款成功录入！")
            st.rerun()

elif action == "录入买卖标的 (Trade)":
    st.sidebar.subheader("📈 标的买卖录入")
    with st.sidebar.form("trade_form"):
        ticker = st.text_input("代码 (如 NVDA, TLT, GLD, AAPL)", value="NVDA")
        cat = st.selectbox("资产分类 (用于永久组合对比)", ["股票", "债券", "黄金", "其他"])
        t_action = st.selectbox("交易方向", ["买入", "卖出"])
        t_qty = st.number_input("持仓数量", min_value=0.0001, value=1.0, step=1.0)
        t_price = st.number_input("成交价格 ($)", min_value=0.01, value=100.0, step=5.0)
        
        if st.form_submit_button("确认提交交易"):
            cost = t_qty * t_price
            if t_action == "买入" and cost > summary['cash_balance']:
                st.sidebar.error("❌ 现金余额不足，无法买入！")
            else:
                date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                c.execute("INSERT INTO trades (ticker, category, action, qty, price, date) VALUES (?, ?, ?, ?, ?, ?)",
                          (ticker.upper().strip(), cat, t_action, t_qty, t_price, date_str))
                
                cash_diff = -cost if t_action == "买入" else cost
                c.execute("UPDATE cash SET balance = ? WHERE id = 1", (summary['cash_balance'] + cash_diff,))
                conn.commit()
                st.sidebar.success("✅ 交易记录成功！")
                st.rerun()

elif action == "🧹 坏数据修复与清空":
    st.sidebar.subheader("🛠️ 数据管理与修剪")
    st.sidebar.write("如页面出现 nan/inf 或历史存取数据录入错误：")
    
    if st.sidebar.button("🧹 一键清除异常 NaN 数据"):
        c.execute("DELETE FROM deposits WHERE units IS NULL OR nav <= 0")
        conn.commit()
        st.sidebar.success("已成功清理！")
        st.rerun()

    if st.sidebar.button("🚨 重置数据库 (清空所有记录)"):
        c.execute("DELETE FROM deposits")
        c.execute("DELETE FROM trades")
        c.execute("UPDATE cash SET balance = 0.0 WHERE id = 1")
        conn.commit()
        st.sidebar.warning("所有历史数据已全额清空！")
        st.rerun()

# -----------------------------------------------------------------------------
# 5. 主看板顶部 Metrics 核心指标展示
# -----------------------------------------------------------------------------
st.title("👩‍❤️‍👨 Our Capital | 情侣共同资产与永久投资组合")
st.caption("实时拉取全球行情 · 自动按基金净值法 (NAV) 折算个人份额 · 永久投资组合智能再平衡")

m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    st.markdown(f'''
    <div class="metric-card">
        <div class="metric-title">💼 组合实时总市值</div>
        <div class="metric-val">￥{summary['total_val']:,.2f}</div>
        <div class="metric-sub">未投资现金: ￥{summary['cash_balance']:,.2f}</div>
    </div>
    ''', unsafe_allow_html=True)

with m2:
    p_color = "#28a745" if summary['total_profit'] >= 0 else "#dc3545"
    st.markdown(f'''
    <div class="metric-card">
        <div class="metric-title">🌱 累计本金 / 收益</div>
        <div class="metric-val" style="color: {p_color}">￥{summary['total_profit']:+,.2f}</div>
        <div class="metric-sub">本金: ￥{summary['total_principal']:,.2f} ({summary['roi']:+.2f}%)</div>
    </div>
    ''', unsafe_allow_html=True)

with m3:
    st.markdown(f'''
    <div class="metric-card">
        <div class="metric-title">🎯 当前单位净值 (NAV)</div>
        <div class="metric-val" style="color: #0d6efd">{summary['nav']:.4f}</div>
        <div class="metric-sub">初始基准: 1.0000</div>
    </div>
    ''', unsafe_allow_html=True)

with m4:
    st.markdown(f'''
    <div class="metric-card">
        <div class="metric-title">💙 我的权益金额</div>
        <div class="metric-val" style="color: #0d6efd">￥{summary['my_equity']:,.2f}</div>
        <div class="metric-sub">持有份额: {summary['my_units']:,.2f}</div>
    </div>
    ''', unsafe_allow_html=True)

with m5:
    st.markdown(f'''
    <div class="metric-card">
        <div class="metric-title">🩷 女友权益金额</div>
        <div class="metric-val" style="color: #d63384">￥{summary['her_equity']:,.2f}</div>
        <div class="metric-sub">持有份额: {summary['her_units']:,.2f}</div>
    </div>
    ''', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 6. 多页签功能区 (Tabs)
# -----------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["📊 实时资产配置", "⚖️ 永久投资组合 (Permanent Portfolio)", "📜 资金与交易明细"])

# TAB 1: 资产配置与持仓
with tab1:
    col_l, col_r = st.columns([1, 1])
    with col_l:
        st.subheader("📊 实时资产分布图")
        chart_data = []
        if summary['cash_balance'] > 0:
            chart_data.append({"类别": "未投资现金", "金额": summary['cash_balance']})
        if not summary['holdings_df'].empty:
            for _, r in summary['holdings_df'].iterrows():
                chart_data.append({"类别": f"{r['代码']} ({r['资产分类']})", "金额": r['当前市值 ($/￥)']})
        
        if chart_data:
            df_pie = pd.DataFrame(chart_data)
            fig_pie = px.pie(df_pie, names='类别', values='金额', hole=0.45,
                             color_discrete_sequence=px.colors.qualitative.Pastel)
            fig_pie.update_traces(textposition='inside', textinfo='percent+label')
            fig_pie.update_layout(margin=dict(t=20, b=20, l=20, r=20), height=380)
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("💡 暂无持仓资产，请在左侧面板录入。")

    with col_r:
        st.subheader("📋 实时持仓明细表")
        if not summary['holdings_df'].empty:
            st.dataframe(
                summary['holdings_df'],
                use_container_width=True,
                height=350
            )
        else:
            st.write("目前暂无股票/标的持仓。")

# TAB 2: 永久投资组合
with tab2:
    st.subheader("⚖️ 哈里·布朗 (Harry Browne) 永久投资组合看板")
    st.markdown("""
    💡 **永久投资组合** 建议将资产划分为四等分（各占 **25%**），以应对任何经济周期：
    - 📈 **股票 (25%)**：经济繁荣期
    - 🏛️ **债券 (25%)**：经济通缩期
    - 🥇 **黄金 (25%)**：高通胀期
    - 💵 **现金 (25%)**：经济衰退/紧缩期
    """)
    
    tot_val = summary['total_val']
    cat_vals = summary['category_val']
    
    if tot_val > 0:
        actual_pct = {
            "股票": (cat_vals.get("股票", 0.0) / tot_val) * 100.0,
            "债券": (cat_vals.get("债券", 0.0) / tot_val) * 100.0,
            "黄金": (cat_vals.get("黄金", 0.0) / tot_val) * 100.0,
            "现金": (cat_vals.get("现金", 0.0) / tot_val) * 100.0,
            "其他": (cat_vals.get("其他", 0.0) / tot_val) * 100.0
        }
    else:
        actual_pct = {"股票": 0.0, "债券": 0.0, "黄金": 0.0, "现金": 100.0, "其他": 0.0}

    df_perm = pd.DataFrame({
        "资产类别": ["股票", "债券", "黄金", "现金"],
        "实际占比 (%)": [actual_pct["股票"], actual_pct["债券"], actual_pct["黄金"], actual_pct["现金"]],
        "目标占比 (%)": [25.0, 25.0, 25.0, 25.0],
        "实际金额": [cat_vals.get("股票",0), cat_vals.get("债券",0), cat_vals.get("黄金",0), cat_vals.get("现金",0)],
        "目标金额": [tot_val * 0.25] * 4
    })

    c_chart, c_rebalance = st.columns([1.2, 1])
    
    with c_chart:
        fig_perm = go.Figure()
        fig_perm.add_trace(go.Bar(
            x=df_perm['资产类别'], y=df_perm['实际占比 (%)'],
            name='当前实际占比', marker_color='#3b82f6'
        ))
        fig_perm.add_trace(go.Bar(
            x=df_perm['资产类别'], y=df_perm['目标占比 (%)'],
            name='目标占比 (25%)', marker_color='#10b981', opacity=0.6
        ))
        fig_perm.update_layout(
            barmode='group',
            title="实际资产配置 vs 永久组合标准配置 (25% x 4)",
            yaxis_title="占比 (%)",
            height=360,
            margin=dict(t=40, b=20, l=20, r=20)
        )
        st.plotly_chart(fig_perm, use_container_width=True)

    with c_rebalance:
        st.subheader("🛠️ 智能再平衡调仓建议")
        if tot_val > 0:
            rebalance_data = []
            for _, r in df_perm.iterrows():
                diff_val = r['目标金额'] - r['实际金额']
                if diff_val > 10:
                    action_text = f"🟢 建议买入 ￥{diff_val:,.2f}"
                elif diff_val < -10:
                    action_text = f"🔴 建议卖出 ￥{abs(diff_val):,.2f}"
                else:
                    action_text = "✨ 完美匹配，无需调整"
                
                rebalance_data.append({
                    "资产类别": r['资产类别'],
                    "当前金额": f"￥{r['实际金额']:,.2f}",
                    "当前占比": f"{r['实际占比 (%)']:.1f}%",
                    "调仓建议": action_text
                })
            st.dataframe(pd.DataFrame(rebalance_data), use_container_width=True)
        else:
            st.info("💡 请先存入资金，即可自动生成调仓再平衡建议。")

# TAB 3: 资金与交易明细
with tab3:
    col_t1, col_t2 = st.columns([1, 1])
    
    with col_t1:
        st.subheader("💳 存取款资金明细")
        df_dep_all = pd.read_sql("SELECT * FROM deposits ORDER BY id DESC", conn)
        if not df_dep_all.empty:
            st.dataframe(
                df_dep_all.rename(columns={
                    "id": "序号", "person": "出资人", "type": "类型",
                    "amount": "金额", "nav": "折算NAV", "units": "折算份额", "date": "时间"
                }),
                use_container_width=True,
                height=400
            )
        else:
            st.write("暂无存取款记录。")

    with col_t2:
        st.subheader("📈 买卖交易明细")
        df_trades_all = pd.read_sql("SELECT * FROM trades ORDER BY id DESC", conn)
        if not df_trades_all.empty:
            st.dataframe(
                df_trades_all.rename(columns={
                    "id": "序号", "ticker": "代码", "category": "分类",
                    "action": "方向", "qty": "数量", "price": "成交单价", "date": "时间"
                }),
                use_container_width=True,
                height=400
            )
        else:
            st.write("暂无买卖交易记录。")
