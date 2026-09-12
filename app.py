import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
import plotly.express as px

# -----------------------------------------------------------------------------
# 1. 页面配置与赛博暗黑 / 温馨情侣视觉样式
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Couple Wealth Hub - 情侣资金管理",
    page_icon="👩‍❤️‍👨",
    layout="wide",
    initial_sidebar_state="expanded"
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
        margin-bottom: 20px;
    }
    
    .hub-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 16px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
        margin-bottom: 12px;
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
        font-size: 12px;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 1px;
    }

    .metric-value-pink {
        font-size: 22px;
        font-weight: 700;
        color: #ff79c6;
        text-shadow: 0 0 8px rgba(255, 121, 198, 0.3);
    }

    .metric-value-cyan {
        font-size: 22px;
        font-weight: 700;
        color: #8be9fd;
        text-shadow: 0 0 8px rgba(139, 233, 253, 0.3);
    }
    
    .metric-value-green {
        font-size: 22px;
        font-weight: 700;
        color: #50fa7b;
        text-shadow: 0 0 8px rgba(80, 250, 123, 0.3);
    }

    /* 按钮全局覆盖 */
    div.stButton > button {
        background: linear-gradient(135deg, #ff79c6 0%, #8be9fd 100%) !important;
        color: #0b0e14 !important;
        border: none !important;
        font-weight: 700 !important;
        border-radius: 6px !important;
        box-shadow: 0 0 12px rgba(255, 121, 198, 0.3) !important;
        transition: all 0.3s ease;
    }
</style>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# 2. SQLite 数据库初始化 (持久化保存资金与账单)
# -----------------------------------------------------------------------------
DB_FILE = "couple_wealth_hub.db"

def init_couple_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    # 共同资金注入表
    c.execute('''
        CREATE TABLE IF NOT EXISTS capital_pool (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person TEXT,
            amount REAL,
            note TEXT,
            created_at TEXT
        )
    ''')
    # 共同日常消费表
    c.execute('''
        CREATE TABLE IF NOT EXISTS daily_expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            payer TEXT,
            amount REAL,
            category TEXT,
            split_mode TEXT,
            note TEXT,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_couple_db()

# 数据库操作函数
def add_capital(person, amount, note):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO capital_pool (person, amount, note, created_at) VALUES (?, ?, ?, ?)",
              (person, amount, note, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()

def add_expense(payer, amount, category, split_mode, note):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("INSERT INTO daily_expenses (payer, amount, category, split_mode, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
              (payer, amount, category, split_mode, note, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()

def get_capital_data():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM capital_pool ORDER BY id DESC", conn)
    conn.close()
    return df

def get_expense_data():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM daily_expenses ORDER BY id DESC", conn)
    conn.close()
    return df

# -----------------------------------------------------------------------------
# 3. 侧边栏与全局参数配置
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 👩‍❤️‍👨 成员与导航配置")
    partner_a = st.text_input("成员 A 昵称", value="男生").strip()
    partner_b = st.text_input("成员 B 昵称", value="女生").strip()
    
    st.markdown("---")
    menu = st.radio(
        "导航功能菜单",
        ["💰 共同资金池概览", "📝 注入/提取共同资金", "🛒 记一笔日常消费", "📊 账单明细与AA结算"]
    )

# -----------------------------------------------------------------------------
# 4. 模块逻辑处理
# -----------------------------------------------------------------------------

# 数据读取与汇总
df_cap = get_capital_data()
df_exp = get_expense_data()

cap_a = df_cap[df_cap['person'] == partner_a]['amount'].sum() if not df_cap.empty else 0.0
cap_b = df_cap[df_cap['person'] == partner_b]['amount'].sum() if not df_cap.empty else 0.0
total_pool = cap_a + cap_b

exp_total = df_exp['amount'].sum() if not df_exp.empty else 0.0
exp_a_paid = df_exp[df_exp['payer'] == partner_a]['amount'].sum() if not df_exp.empty else 0.0
exp_b_paid = df_exp[df_exp['payer'] == partner_b]['amount'].sum() if not df_exp.empty else 0.0

st.markdown('<h2 class="hub-header">👩‍❤️‍👨 情侣联合资金管理中心</h2>', unsafe_allow_html=True)

# --- 模式 1: 资金池概览 ---
if menu == "💰 共同资金池概览":
    st.markdown("### 💰 双方资金池看板")
    
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(f"""
        <div class="hub-card">
            <div class="metric-title">共同资金池总投入</div>
            <div class="metric-value-green">${total_pool:,.2f}</div>
        </div>""", unsafe_allow_html=True)
        
    with m2:
        st.markdown(f"""
        <div class="hub-card">
            <div class="metric-title">{partner_a} 累计存入</div>
            <div class="metric-value-cyan">${cap_a:,.2f}</div>
        </div>""", unsafe_allow_html=True)

    with m3:
        st.markdown(f"""
        <div class="hub-card">
            <div class="metric-title">{partner_b} 累计存入</div>
            <div class="metric-value-pink">${cap_b:,.2f}</div>
        </div>""", unsafe_allow_html=True)

    with m4:
        st.markdown(f"""
        <div class="hub-card">
            <div class="metric-title">共同支出总额</div>
            <div style="font-size:22px; font-weight:700; color:#ff5555;">${exp_total:,.2f}</div>
        </div>""", unsafe_allow_html=True)

    c_chart, c_info = st.columns([2, 1])
    with c_chart:
        if total_pool > 0:
            fig = px.pie(
                values=[cap_a, cap_b], 
                names=[partner_a, partner_b], 
                title="双方出资比例分布",
                color_discrete_sequence=['#8be9fd', '#ff79c6']
            )
            fig.update_layout(template="plotly_dark", paper_bgcolor='#0b0e14', plot_bgcolor='#161b22')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("资金池暂无资金注入，请在侧边栏切换至【注入/提取共同资金】添加。")

    with c_info:
        st.markdown("#### 💡 资金状态")
        if total_pool > 0:
            ratio_a = (cap_a / total_pool) * 100
            ratio_b = (cap_b / total_pool) * 100
            st.write(f"- **{partner_a} 出资占比**: `{ratio_a:.1f}%`")
            st.write(f"- **{partner_b} 出资占比**: `{ratio_b:.1f}%`")
        st.write(f"- **共同支出笔数**: `{len(df_exp)} 笔`")
        st.write(f"- **注资记录笔数**: `{len(df_cap)} 笔`")

# --- 模式 2: 注入 / 提取共同资金 ---
elif menu == "📝 注入/提取共同资金":
    st.markdown("### 📝 共同资金池存取管理")
    
    with st.form(key="capital_form"):
        c1, c2, c3 = st.columns([2, 2, 3])
        with c1:
            person = st.selectbox("存取人", [partner_a, partner_b])
        with c2:
            amount = st.number_input("金额 ($) (取出请输入负数)", value=100.0, step=50.0)
        with c3:
            note = st.text_input("备注信息", value="定期存入共同基金")
            
        submit_cap = st.form_submit_button("确认提交操作", use_container_width=True)
        if submit_cap:
            add_capital(person, amount, note)
            st.success(f"成功为 {person} 记录一笔资金变动: ${amount}！")
            st.rerun()

    st.markdown("---")
    st.markdown("#### 📜 资金存取历史流水")
    if not df_cap.empty:
        st.dataframe(df_cap, use_container_width=True, hide_index=True)
    else:
        st.caption("暂无存取记录。")

# --- 模式 3: 记一笔日常消费 ---
elif menu == "🛒 记一笔日常消费":
    st.markdown("### 🛒 记一笔日常消费")
    
    with st.form(key="expense_form"):
        e1, e2, e3 = st.columns([2, 2, 2])
        with e1:
            payer = st.selectbox("付款人", [partner_a, partner_b, "共同资金池"])
        with e2:
            exp_amount = st.number_input("消费金额 ($)", value=20.0, step=5.0)
        with e3:
            category = st.selectbox("消费分类", ["餐饮美食", "超市采购", "娱乐休闲", "住房缴费", "数码家电", "旅行外出", "其他"])
            
        e4, e5 = st.columns([2, 4])
        with e4:
            split_mode = st.selectbox("AA 结算模式", ["平摊 (50%-50%)", "无需结算 (个人赠与/全包)", "按资金池出资比例"])
        with e5:
            exp_note = st.text_input("消费备注", value="周末晚餐")
            
        submit_exp = st.form_submit_button("记录消费账单", use_container_width=True)
        if submit_exp:
            add_expense(payer, exp_amount, category, split_mode, exp_note)
            st.success("消费账单记录成功！")
            st.rerun()

# --- 模式 4: 账单明细与 AA 结算 ---
elif menu == "📊 账单明细与AA结算":
    st.markdown("### 📊 日常消费明细与对账")
    
    if not df_exp.empty:
        # 简单结算计算 (按平摊 50-50 计算个人垫付差额)
        df_aa = df_exp[df_exp['split_mode'] == "平摊 (50%-50%)"]
        a_aa_paid = df_aa[df_aa['payer'] == partner_a]['amount'].sum()
        b_aa_paid = df_aa[df_aa['payer'] == partner_b]['amount'].sum()
        
        diff = (a_aa_paid - b_aa_paid) / 2
        
        st.markdown("#### ⚖️ 双方 50-50 AA 结算对账结果")
        c_settle1, c_settle2 = st.columns(2)
        with c_settle1:
            st.info(f"**{partner_a}** 垫付平摊总额: **${a_aa_paid:,.2f}**")
        with c_settle2:
            st.info(f"**{partner_b}** 垫付平摊总额: **${b_aa_paid:,.2f}**")
            
        if diff > 0:
            st.success(f"👉 **结算建议**: 【{partner_b}】 需要转账 **${abs(diff):,.2f}** 给 【{partner_a}】")
        elif diff < 0:
            st.success(f"👉 **结算建议**: 【{partner_a}】 需要转账 **${abs(diff):,.2f}** 给 【{partner_b}】")
        else:
            st.success("👉 **结算建议**: 双方垫付金额完全平衡，无需相互转账！")
            
        st.markdown("---")
        st.markdown("#### 📜 消费账单全量列表")
        st.dataframe(df_exp, use_container_width=True, hide_index=True)
    else:
        st.caption("暂无日常消费记录。")
