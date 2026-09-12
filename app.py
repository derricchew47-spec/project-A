import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
from datetime import datetime
import yfinance as yf
import os

# -----------------------------------------------------------------------------
# 1. 数据库路径锁定 (保证数据永不丢失)
# -----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "portfolio_pool_cute.db")

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

def update_capital(tx_id, date, member, type_val, amount, notes):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("UPDATE capital_ledger SET date=?, member=?, type=?, amount=?, notes=? WHERE id=?",
              (date, member, type_val, amount, notes, tx_id))
    conn.commit()
    conn.close()

def delete_capital(tx_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM capital_ledger WHERE id=?", (tx_id,))
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

def update_tx(tx_id, date, asset_type, platform, symbol, name, tx_type, price, quantity, total_amount, notes):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        UPDATE pool_transactions 
        SET date=?, asset_type=?, platform=?, symbol=?, name=?, tx_type=?, price=?, quantity=?, total_amount=?, notes=?
        WHERE id=?
    ''', (date, asset_type, platform, symbol, name, tx_type, price, quantity, total_amount, notes, tx_id))
    conn.commit()
    conn.close()

def delete_tx(tx_id):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("DELETE FROM pool_transactions WHERE id=?", (tx_id,))
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
# 2. UI 主题与样式 (大幅增加卡片高度)
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
    
    /* 大号正方形拉长卡片按钮样式 */
    div[data-testid="stSidebar"] div.stButton > button {
        height: 1000px !important;            /* 高度从85调高至130 */
        width: 100% !important;
        border-radius: 20px !important;
        font-size: 14px !important;
        font-weight: 700 !important;
        white-space: pre-line !important;     /* 严格换行 */
        word-break: break-all !important;
        line-height: 1.4 !important;
        padding: 10px 4px !important;
        box-shadow: 0 6px 16px rgba(255, 182, 193, 0.25);
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 3. 侧边栏：大号拉长正方形 (2x2) 卡片导航
# -----------------------------------------------------------------------------
if 'current_menu' not in st.session_state:
    st.session_state.current_menu = "🍰 共享资金池总览"

with st.sidebar:
    st.markdown("### 🌸 导航菜单")
    
    # 将 Icon 与标题竖向排列，保证完美显示不挤压
    nav_items = [
        ("🍰\n共享资金池\n总览", "🍰 共享资金池总览"),
        ("💵\n资金存入\n与取出", "💵 资金存入/取出"),
        ("📈\n买卖标的\n记账", "📈 买卖标的记账"),
        ("📜\n交易明细\n与日志", "📜 交易明细与记录")
    ]
    
    # 第一行 2 个正方形大卡片
    col1, col2 = st.columns(2)
    with col1:
        label, page_name = nav_items[0]
        btn_type = "primary" if st.session_state.current_menu == page_name else "secondary"
        if st.button(label, key="btn_nav_1", type=btn_type, use_container_width=True):
            st.session_state.current_menu = page_name
            st.rerun()
            
    with col2:
        label, page_name = nav_items[1]
        btn_type = "primary" if st.session_state.current_menu == page_name else "secondary"
        if st.button(label, key="btn_nav_2", type=btn_type, use_container_width=True):
            st.session_state.current_menu = page_name
            st.rerun()

    st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)

    # 第二行 2 个正方形大卡片
    col3, col4 = st.columns(2)
    with col3:
        label, page_name = nav_items[2]
        btn_type = "primary" if st.session_state.current_menu == page_name else "secondary"
        if st.button(label, key="btn_nav_3", type=btn_type, use_container_width=True):
            st.session_state.current_menu = page_name
            st.rerun()
            
    with col4:
        label, page_name = nav_items[3]
        btn_type = "primary" if st.session_state.current_menu == page_name else "secondary"
        if st.button(label, key="btn_nav_4", type=btn_type, use_container_width=True):
            st.session_state.current_menu = page_name
            st.rerun()

    menu = st.session_state.current_menu

    st.markdown("---")
    st.markdown("### 💾 数据库保存与备份")
    st.caption(f"存储位置：\n`{DB_FILE}`")
    
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "rb") as fp:
            st.download_button(
                label="📥 备份并下载数据库",
                data=fp,
                file_name=f"portfolio_backup_{datetime.now().strftime('%Y%m%d')}.db",
                mime="application/x-sqlite3",
                use_container_width=True
            )
            
    uploaded_db = st.file_uploader("📤 导入还原备份数据库 (.db)", type=["db"])
    if uploaded_db is not None:
        with open(DB_FILE, "wb") as f:
            f.write(uploaded_db.getbuffer())
        st.success("✅ 数据恢复成功！")
        st.rerun()

# -----------------------------------------------------------------------------
# 4. 核心数据汇总与逻辑计算
# -----------------------------------------------------------------------------
COLORS_ASSETS = ['#FF9AA2', '#FFB7B2', '#FFDAC1', '#E2F0CB', '#B5EAD7', '#C7CEEA']
COLORS_PLATFORMS = ['#A8DADC', '#F4A261', '#E76F51', '#2A9D8F', '#E9C46A']

df_cap = load_capital()
df_tx = load_tx()
manual_prices = get_manual_prices()

capital_summary = {'👦 男方': 0.0, '👧 女方': 0.0}
if not df_cap.empty:
    for _, r in df_cap.iterrows():
        m, amt = r['member'], r['amount']
        if r['type'] in ['注资/存入本金', '存入']:
            capital_summary[m] += amt
        elif r['type'] in ['撤资/提取本金', '取出']:
            capital_summary[m] -= amt

total_capital = sum(capital_summary.values())

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
        profit = mv - item['cost']
        profit_pct = (profit / item['cost'] * 100) if item['cost'] > 0 else 0.0
        portfolio.append({
            'key': k, 'name': item['name'], 'type': item['type'], 'plat': item['plat'],
            'qty': item['qty'], 'price': cp, 'cost': item['cost'], 'mv': mv, 'profit': profit, 'profit_pct': profit_pct
        })

df_portfolio = pd.DataFrame(portfolio)
cash_balance = total_capital - cash_spent
total_net_worth = cash_balance + total_assets_mv
total_profit = total_net_worth - total_capital
profit_pct = (total_profit / total_capital * 100) if total_capital > 0 else 0.0

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
# 5. 页面内容渲染
# -----------------------------------------------------------------------------
if menu == "🍰 共享资金池总览":
    st.title("🌸 小情侣的资金池资产看板")
    
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(f'<div class="cute-card"><div class="cute-title">🏦 资金池总资产</div><div class="cute-value">${total_net_worth:,.2f}</div></div>', unsafe_allow_html=True)
    with k2:
        st.markdown(f'<div class="cute-card"><div class="cute-title">💵 可用现金余额</div><div class="cute-value" style="color:#2a9d8f;">${cash_balance:,.2f}</div></div>', unsafe_allow_html=True)
    with k3:
        st.markdown(f'<div class="cute-card"><div class="cute-title">📈 标的总市值</div><div class="cute-value" style="color:#e76f51;">${total_assets_mv:,.2f}</div></div>', unsafe_allow_html=True)
    with k4:
        profit_color = "#2a9d8f" if total_profit >= 0 else "#e76f51"
        pct_str = f"+{profit_pct:.2f}%" if total_profit >= 0 else f"{profit_pct:.2f}%"
        st.markdown(f'''
            <div class="cute-card">
                <div class="cute-title">✨ 累计盈亏</div>
                <div class="cute-value" style="color:{profit_color};">
                    ${total_profit:,.2f} <span style="font-size:14px; font-weight:600;">({pct_str})</span>
                </div>
            </div>
        ''', unsafe_allow_html=True)

    st.markdown("---")

    col_e1, col_e2 = st.columns([3, 2])
    with col_e1:
        st.subheader("👩‍❤️‍👨 两人出资与权益份额")
        st.dataframe(df_equity, use_container_width=True, hide_index=True)
    with col_e2:
        color_map_members = {'👦 男方': '#4EA8DE', '👧 女方': '#FF85A1'}
        fig_mem = px.pie(
            df_equity, values=[capital_summary['👦 男方'], capital_summary['👧 女方']], 
            names=['👦 男方', '👧 女方'], hole=0.55, color='成员',
            color_discrete_map=color_map_members, title="💕 本金出资比例"
        )
        fig_mem.update_traces(textinfo='percent+label', marker=dict(line=dict(color='#ffffff', width=3)))
        fig_mem.update_layout(showlegend=False, margin=dict(t=30, b=0, l=0, r=0))
        st.plotly_chart(fig_mem, use_container_width=True)

    st.markdown("---")

    st.subheader("🎨 资产配置与分布可视化")
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

    st.subheader("📦 当前投资标的概览")
    if df_portfolio.empty:
        st.info("💡 目前池子里都是现金哦，还没有买入任何投资标的～")
    else:
        c_list = st.columns(3)
        for idx, r in df_portfolio.iterrows():
            with c_list[idx % 3]:
                is_profitable = r['profit'] >= 0
                item_profit_color = "#2a9d8f" if is_profitable else "#e76f51"
                card_bg = "#e8f5e9" if is_profitable else "#fff0f3"
                card_border = "#2a9d8f" if is_profitable else "#ff758f"
                
                asset_pct = (r['mv'] / total_net_worth * 100) if total_net_worth > 0 else 0.0
                asset_pct_str = f"+{asset_pct:.1f}%" if asset_pct >= 0 else f"{asset_pct:.1f}%"
                item_pct_str = f"+{r['profit_pct']:.2f}%" if is_profitable else f"{r['profit_pct']:.2f}%"

                st.markdown(f"""
                <div style="background:{card_bg}; border-radius:12px; padding:12px; border-left:5px solid {card_border}; margin-bottom:8px;">
                    <div style="display:flex; justify-content:space-between; font-weight:700;">
                        <span>{r['name']} ({r['plat']})</span>
                        <span>${r['mv']:,.2f} <span style="font-size:12px; font-weight:600; color:{item_profit_color};">({asset_pct_str})</span></span>
                    </div>
                    <div style="font-size:12px; color:#666; margin-top:4px;">
                        数量: {r['qty']:.2f} | 现价: ${r['price']:.2f} | 盈亏: <b style="color:{item_profit_color};">${r['profit']:,.2f} ({item_pct_str})</b>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        with st.expander("⚙️ 手动更新净值/单价 (如 TNG 黄金 / MooMoo 货币基金)"):
            m_col1, m_col2, m_col3 = st.columns(3)
            selected_key = m_col1.selectbox("选择标的", df_portfolio['key'].tolist())
            curr_v = manual_prices.get(selected_key, float(df_portfolio[df_portfolio['key']==selected_key]['price'].iloc[0]))
            new_v = m_col2.number_input("最新单价/净值", value=float(curr_v), format="%.4f")
            if m_col3.button("✨ 更新单价"):
                update_manual_price(selected_key, new_v)
                st.success("已更新价格！")
                st.rerun()

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

elif menu == "📜 交易明细与记录":
    st.title("📜 交易明细与历史日志")
    st.markdown("在此处可以查看所有历史记账，进行**修改编辑**或**直接删除**，修改后所有图表和资产数据均会自动同步刷新。")

    tab_cap, tab_tx = st.tabs(["💵 本金存取明细 Log", "📈 标的交易明细 Log"])

    with tab_cap:
        if df_cap.empty:
            st.info("尚无本金存取记录")
        else:
            st.dataframe(df_cap[['id', 'date', 'member', 'type', 'amount', 'notes']], use_container_width=True, hide_index=True)
            st.markdown("---")
            st.subheader("🛠️ 编辑 / 删除资金记录")
            
            cap_id_list = df_cap['id'].tolist()
            selected_cap_id = st.selectbox("选择要编辑/删除的资金记录 ID", cap_id_list, key="sel_cap")
            row_cap = df_cap[df_cap['id'] == selected_cap_id].iloc[0]

            with st.form("edit_cap_form"):
                ec1, ec2 = st.columns(2)
                with ec1:
                    e_member = st.selectbox("出资人", ["👦 男方", "👧 女方"], index=0 if row_cap['member']=="👦 男方" else 1)
                    e_type = st.selectbox("类型", ["注资/存入本金", "撤资/提取本金"], index=0 if "存入" in row_cap['type'] else 1)
                with ec2:
                    e_date = st.date_input("日期", datetime.strptime(row_cap['date'], "%Y-%m-%d"))
                    e_amount = st.number_input("金额 ($)", min_value=1.0, value=float(row_cap['amount']))
                e_notes = st.text_input("备注", value=str(row_cap['notes'] or ''))

                col_btn1, col_btn2 = st.columns(2)
                with col_btn1:
                    btn_update_cap = st.form_submit_button("✏️ 保存修改", use_container_width=True)
                with col_btn2:
                    btn_del_cap = st.form_submit_button("🗑️ 删除此笔记录", use_container_width=True)

                if btn_update_cap:
                    update_capital(selected_cap_id, e_date.strftime("%Y-%m-%d"), e_member, e_type, e_amount, e_notes)
                    st.success("已更新资金记录并刷新数据！")
                    st.rerun()

                if btn_del_cap:
                    delete_capital(selected_cap_id)
                    st.success("记录已成功删除并重新计算面板！")
                    st.rerun()

    with tab_tx:
        if df_tx.empty:
            st.info("尚无标的交易记录")
        else:
            st.dataframe(df_tx[['id', 'date', 'asset_type', 'platform', 'symbol', 'name', 'tx_type', 'price', 'quantity', 'total_amount', 'notes']], use_container_width=True, hide_index=True)
            st.markdown("---")
            st.subheader("🛠️ 编辑 / 删除标的交易记录")

            tx_id_list = df_tx['id'].tolist()
            selected_tx_id = st.selectbox("选择要编辑/删除的交易 ID", tx_id_list, key="sel_tx")
            row_tx = df_tx[df_tx['id'] == selected_tx_id].iloc[0]

            with st.form("edit_tx_form"):
                et1, et2, et3 = st.columns(3)
                asset_options = ["股票/ETF", "黄金/贵金属", "货币基金/现金", "加密货币", "其他"]
                with et1:
                    e_asset_type = st.selectbox("资产类型", asset_options, index=asset_options.index(row_tx['asset_type']) if row_tx['asset_type'] in asset_options else 0)
                    e_tx_type = st.selectbox("交易类型", ["买入", "卖出"], index=0 if row_tx['tx_type']=="买入" else 1)
                    e_tx_date = st.date_input("日期", datetime.strptime(row_tx['date'], "%Y-%m-%d"))
                with et2:
                    e_platform = st.text_input("投资平台", value=str(row_tx['platform']))
                    e_name = st.text_input("标的名称", value=str(row_tx['name']))
                    e_symbol = st.text_input("代码 (选填)", value=str(row_tx['symbol'] or ''))
                with et3:
                    e_price = st.number_input("单价", min_value=0.0001, value=float(row_tx['price']), format="%.4f")
                    e_quantity = st.number_input("数量 / 份额", min_value=0.0001, value=float(row_tx['quantity']), format="%.4f")
                    e_tx_notes = st.text_input("备注", value=str(row_tx['notes'] or ''))

                e_tot = e_price * e_quantity
                st.markdown(f"**💰 计算总额: ${e_tot:,.2f}**")

                col_tx_btn1, col_tx_btn2 = st.columns(2)
                with col_tx_btn1:
                    btn_update_tx = st.form_submit_button("✏️ 保存修改", use_container_width=True)
                with col_tx_btn2:
                    btn_del_tx = st.form_submit_button("🗑️ 删除此笔记录", use_container_width=True)

                if btn_update_tx:
                    update_tx(selected_tx_id, e_tx_date.strftime("%Y-%m-%d"), e_asset_type, e_platform, e_symbol.upper().strip(), e_name.strip(), e_tx_type, e_price, e_quantity, e_tot, e_tx_notes)
                    st.success("修改已保存并重新联动更新看板！")
                    st.rerun()

                if btn_del_tx:
                    delete_tx(selected_tx_id)
                    st.success("已成功删除记录并实时刷新所有数据！")
                    st.rerun()
