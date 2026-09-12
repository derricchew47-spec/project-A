import streamlit as st
import pandas as pd
import sqlite3
import os
from datetime import datetime
import yfinance as yf
import plotly.express as px

# -----------------------------------------------------------------------------
# 1. 页面配置与手机极速优化配置
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Couple Wealth Hub - 情侣资金管理",
    page_icon="👩‍❤️‍👨",
    layout="wide",
    initial_sidebar_state="collapsed"  # 手机端默认收起侧边栏，提速开屏渲染
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;600;700&display=swap');
    
    .stApp {
        background-color: #0b0e14;
        color: #c9d1d9;
        font-family: 'Fira Code', monospace, -apple-system, sans-serif;
    }
    
    .hub-header {
        font-family: 'Fira Code', monospace;
        font-weight: 700;
        color: #ff79c6;
        text-shadow: 0 0 12px rgba(255, 121, 198, 0.4);
        margin-bottom: 15px;
    }
    
    .hub-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 14px;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.5);
        margin-bottom: 10px;
        position: relative;
    }
    
    .hub-card::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0; height: 2px;
        background: linear-gradient(90deg, #ff79c6, #8be9fd);
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
    }

    .metric-title {
        font-size: 11px;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    .profit-pos {
        font-size: 22px;
        font-weight: 700;
        color: #50fa7b;
        text-shadow: 0 0 8px rgba(80, 250, 123, 0.3);
    }

    .profit-neg {
        font-size: 22px;
        font-weight: 700;
        color: #ff5555;
        text-shadow: 0 0 8px rgba(255, 85, 85, 0.3);
    }

    div.stButton > button {
        background: linear-gradient(135deg, #ff79c6 0%, #8be9fd 100%) !important;
        color: #0b0e14 !important;
        border: none !important;
        font-weight: 700 !important;
        border-radius: 6px !important;
        box-shadow: 0 0 10px rgba(255, 121, 198, 0.3) !important;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. 数据库自动初始化 (对接标准的 3 张核心表)
# -----------------------------------------------------------------------------
DB_FILE = "couple_wealth_hub.db"

def get_db_connection():
    return sqlite3.connect(DB_FILE)

def init_couple_db():
    conn = get_db_connection()
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

init_couple_db()

# -----------------------------------------------------------------------------
# 3. 手机端数据高性能读取与实时市值计算
# -----------------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def load_table_data(table_name):
    conn = get_db_connection()
    df = pd.read_sql_query(f"SELECT * FROM {table_name} ORDER BY id DESC", conn)
    conn.close()
    return df

@st.cache_data(ttl=300, show_spinner=False)
def fetch_live_stock_price(symbol: str):
    """通过 Yahoo Finance 实时抓取股票/ETF最新价，失败则返回 None"""
    if not symbol or not symbol.strip():
        return None
    try:
        t = yf.Ticker(symbol.strip().upper())
        todays_data = t.history(period="1d")
        if not todays_data.empty:
            return float(todays_data['Close'].iloc[-1])
    except Exception:
        pass
    return None

def calculate_portfolio_metrics():
    """计算总投资成本、当前实时市值、各资产大类分布及整体盈亏"""
    conn = get_db_connection()
    df_tx = pd.read_sql_query("SELECT * FROM pool_transactions", conn)
    df_manual = pd.read_sql_query("SELECT * FROM manual_prices", conn)
    conn.close()

    if df_tx.empty:
        return 0.0, 0.0, 0.0, 0.0, {}

    # 建立手动价格字典
    manual_price_map = {}
    if not df_manual.empty:
        for _, row in df_manual.iterrows():
            manual_price_map[str(row['symbol_or_name']).upper().strip()] = float(row['last_price'])

    # 按资产计算持仓数量与总成本
    holding_summary = {}
    asset_category_totals = {}

    for _, row in df_tx.iterrows():
        sym = str(row['symbol']).upper().strip() if row['symbol'] else str(row['name']).strip()
        asset_type = row['asset_type']
        tx_type = row['tx_type']
        qty = float(row['quantity'])
        tot_amt = float(row['total_amount'])

        if sym not in holding_summary:
            holding_summary[sym] = {
                "name": row['name'],
                "asset_type": asset_type,
                "symbol": row['symbol'],
                "net_qty": 0.0,
                "total_cost": 0.0
            }

        if tx_type == "买入":
            holding_summary[sym]["net_qty"] += qty
            holding_summary[sym]["total_cost"] += tot_amt
        elif tx_type == "卖出":
            holding_summary[sym]["net_qty"] -= qty
            holding_summary[sym]["total_cost"] -= tot_amt  # 简化成本扣减

    total_cost = 0.0
    total_market_value = 0.0

    for sym, info in holding_summary.items():
        net_qty = info["net_qty"]
        if net_qty <= 0:
            continue
        
        cost = info["total_cost"]
        total_cost += cost

        # 获取当前最新单价：优先尝试实时行情(针对股票/ETF)，其次查找手动填写的价格，最后用平均成本兜底
        current_price = None
        if info["symbol"] and ("股票" in info["asset_type"] or "ETF" in info["asset_type"]):
            current_price = fetch_live_stock_price(info["symbol"])
        
        if current_price is None:
            current_price = manual_price_map.get(sym, manual_price_map.get(str(info["name"]).upper().strip(), cost / net_qty if net_qty > 0 else 0))

        market_val = net_qty * current_price
        total_market_value += market_val

        cat = info["asset_type"]
        asset_category_totals[cat] = asset_category_totals.get(cat, 0.0) + market_val

    total_pnl = total_market_value - total_cost
    pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0.0

    return total_cost, total_market_value, total_pnl, pnl_pct, asset_category_totals

# -----------------------------------------------------------------------------
# 4. 侧边栏与系统设置
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 👩‍❤️‍👨 成员与导航配置")
    partner_a = st.text_input("成员 A 昵称", value="👦 男方").strip()
    partner_b = st.text_input("成员 B 昵称", value="👧 女方").strip()
    
    st.markdown("---")
    menu = st.radio(
        "导航功能菜单",
        ["💰 共同资金池概览", "📝 注入/提取共同资金", "🛒 交易/投资明细", "💾 备份与恢复数据"]
    )

st.markdown('<h3 class="hub-header">👩‍❤️‍👨 情侣联合资金管理中心</h3>', unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 5. 各功能模块
# -----------------------------------------------------------------------------

# --- 模式 1: 共同资金池概览 (全新盈亏卡片与大类分配看板) ---
if menu == "💰 共同资金池概览":
    st.markdown("### 💰 双方资金池与投资看板")
    
    df_cap = load_table_data("capital_ledger")
    cap_a = df_cap[df_cap['member'].str.contains(partner_a, na=False)]['amount'].sum() if not df_cap.empty else 0.0
    cap_b = df_cap[df_cap['member'].str.contains(partner_b, na=False)]['amount'].sum() if not df_cap.empty else 0.0
    total_pool = cap_a + cap_b

    tot_cost, tot_market_val, tot_pnl, pnl_pct, cat_totals = calculate_portfolio_metrics()

    # 动态盈亏样式与正负号判定
    pnl_sign = "+" if tot_pnl >= 0 else ""
    pnl_class = "profit-pos" if tot_pnl >= 0 else "profit-neg"
    pnl_str = f"{pnl_sign}${tot_pnl:,.2f} ({pnl_sign}{pnl_pct:.2f}%)"

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(f"""
        <div class="hub-card">
            <div class="metric-title">资金池总注入本金</div>
            <div style="font-size:20px; font-weight:700; color:#8be9fd;">${total_pool:,.2f}</div>
        </div>""", unsafe_allow_html=True)
        
    with m2:
        st.markdown(f"""
        <div class="hub-card">
            <div class="metric-title">投资资产当前总价值</div>
            <div style="font-size:20px; font-weight:700; color:#50fa7b;">${tot_market_val:,.2f}</div>
        </div>""", unsafe_allow_html=True)

    with m3:
        st.markdown(f"""
        <div class="hub-card">
            <div class="metric-title">当前总盈亏状况</div>
            <div class="{pnl_class}">{pnl_str}</div>
        </div>""", unsafe_allow_html=True)

    with m4:
        st.markdown(f"""
        <div class="hub-card">
            <div class="metric-title">{partner_a} / {partner_b} 注入比</div>
            <div style="font-size:16px; font-weight:700; color:#ff79c6;">${cap_a:,.2f} / ${cap_b:,.2f}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("---")
    c_chart1, c_chart2 = st.columns(2)
    
    with c_chart1:
        st.markdown("#### 📊 资产大类价值分布 (如何分配)")
        if cat_totals:
            fig_cat = px.pie(
                values=list(cat_totals.values()),
                names=list(cat_totals.keys()),
                title="各类资产持仓占比",
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            fig_cat.update_layout(template="plotly_dark", paper_bgcolor='#0b0e14', plot_bgcolor='#161b22', height=320)
            st.plotly_chart(fig_cat, use_container_width=True, config={'displayModeBar': False})
        else:
            st.info("暂无投资资产明细记录，请先在【交易/投资明细】中添加。")

    with c_chart2:
        st.markdown("#### 👩‍❤️‍👨 双方资金注入比例")
        if total_pool > 0:
            fig_person = px.pie(
                values=[cap_a, cap_b], 
                names=[partner_a, partner_b], 
                title="双方出资占比分布",
                color_discrete_sequence=['#8be9fd', '#ff79c6']
            )
            fig_person.update_layout(template="plotly_dark", paper_bgcolor='#0b0e14', plot_bgcolor='#161b22', height=320)
            st.plotly_chart(fig_person, use_container_width=True, config={'displayModeBar': False})
        else:
            st.info("资金池暂无资金注入。")

# --- 模式 2: 注入/提取共同资金 ---
elif menu == "📝 注入/提取共同资金":
    st.markdown("### 📝 共同资金存取记录")
    
    with st.form(key="capital_entry_form"):
        c1, c2, c3, c4 = st.columns([2, 2, 2, 3])
        with c1:
            tx_date = st.date_input("日期", datetime.now()).strftime("%Y-%m-%d")
        with c2:
            member = st.selectbox("操作人", [partner_a, partner_b])
        with c3:
            tx_type = st.selectbox("变动类型", ["注资/存入本金", "提现/提取本金"])
        with c4:
            amount = st.number_input("金额 ($)", value=100.0, step=50.0)
            
        notes = st.text_input("备注说明", value="定期注入资金池")
        submit_cap = st.form_submit_button("确认写入数据库", use_container_width=True)
        
        if submit_cap:
            conn = get_db_connection()
            c = conn.cursor()
            actual_amount = amount if "注资" in tx_type else -amount
            c.execute(
                "INSERT INTO capital_ledger (date, member, type, amount, notes) VALUES (?, ?, ?, ?, ?)",
                (tx_date, member, tx_type, actual_amount, notes)
            )
            conn.commit()
            conn.close()
            st.cache_data.clear()
            st.success("成功录入资金记录！")
            st.rerun()

    st.markdown("---")
    st.markdown("#### 📜 资金账本流水")
    df_cap = load_table_data("capital_ledger")
    st.dataframe(df_cap, use_container_width=True, hide_index=True)

# --- 模式 3: 交易/投资明细 ---
elif menu == "🛒 交易/投资明细":
    st.markdown("### 🛒 投资与交易记录")
    
    with st.form(key="tx_form"):
        t1, t2, t3, t4 = st.columns([2, 2, 2, 2])
        with t1:
            date_str = st.date_input("交易日期", datetime.now()).strftime("%Y-%m-%d")
        with t2:
            asset_type = st.selectbox("资产类型", ["股票/ETF", "黄金/贵金属", "紧急备用金 (MMF)", "其他资产"])
        with t3:
            platform = st.text_input("平台 (如 Moomoo / TNG)", value="Moomoo")
        with t4:
            tx_type = st.selectbox("买/卖", ["买入", "卖出"])

        t5, t6, t7 = st.columns([2, 2, 2])
        with t5:
            symbol = st.text_input("代码 (Symbol，股票必填)", value="NVDA")
        with t6:
            name = st.text_input("资产名称", value="NVIDIA")
        with t7:
            price = st.number_input("单价 ($)", value=100.0, step=1.0)

        t8, t9 = st.columns([2, 4])
        with t8:
            quantity = st.number_input("数量", value=1.0, step=0.1)
        with t9:
            notes = st.text_input("备注", value="建仓")

        submit_tx = st.form_submit_button("记录交易", use_container_width=True)
        if submit_tx:
            total_amt = price * quantity
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("""
                INSERT INTO pool_transactions 
                (date, asset_type, platform, symbol, name, tx_type, price, quantity, total_amount, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (date_str, asset_type, platform, symbol, name, tx_type, price, quantity, total_amt, notes))
            conn.commit()
            conn.close()
            st.cache_data.clear()
            st.success("成功新增一笔交易明细！")
            st.rerun()

    st.markdown("---")
    st.markdown("#### 📜 历史交易记录")
    df_tx = load_table_data("pool_transactions")
    st.dataframe(df_tx, use_container_width=True, hide_index=True)

# --- 模式 4: 💾 备份与恢复数据 ---
elif menu == "💾 备份与恢复数据":
    st.markdown("### 💾 数据库备份与导入恢复")

    col_bak1, col_bak2 = st.columns(2)

    with col_bak1:
        st.markdown("""
        <div class="hub-card">
            <h4>📤 导出/下载当前备份</h4>
            <p style="font-size:12px; color:#8b949e;">将最新的本地数据库 (.db 文件) 下载保存到手机或电脑，防止数据丢失。</p>
        </div>
        """, unsafe_allow_html=True)
        
        if os.path.exists(DB_FILE):
            with open(DB_FILE, "rb") as f:
                db_bytes = f.read()
            st.download_button(
                label="⬇️ 下载最新的 DB 数据库文件",
                data=db_bytes,
                file_name=f"couple_wealth_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
                mime="application/x-sqlite3",
                use_container_width=True
            )

    with col_bak2:
        st.markdown("""
        <div class="hub-card">
            <h4>📥 导入/还原现有备份</h4>
            <p style="font-size:12px; color:#8b949e;">上传你之前下载保存的 .db 文件，系统会自动覆盖并恢复所有记录。</p>
        </div>
        """, unsafe_allow_html=True)

        uploaded_db = st.file_uploader("选择备份的 .db 文件", type=["db", "sqlite3", "sqlite"])
        if uploaded_db is not None:
            if st.button("🚨 确认用上传文件覆盖当前系统数据", use_container_width=True):
                try:
                    with open(DB_FILE, "wb") as f:
                        f.write(uploaded_db.getbuffer())
                    st.cache_data.clear()
                    st.success("🎉 数据成功覆盖恢复！页面正在刷新...")
                    st.rerun()
                except Exception as e:
                    st.error(f"恢复数据失败: {e}")
