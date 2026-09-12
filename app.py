# 2. 计算各分类的实际占比与再平衡差额
    cat_names = ["📈 股票/指数", "📜 长期债券", "🥇 黄金/贵金属", "💵 现金/货币"]
    mvs = [pp_stocks, pp_bonds, pp_gold, pp_cash]
    keys = ['stocks', 'bonds', 'gold', 'cash']
    
    target_pct = 25.0
    summary_rows = []

    for name, mv, key in zip(cat_names, mvs, keys):
        curr_pct = (mv / total_net_worth * 100) if total_net_worth > 0 else 0.0
        target_mv = total_net_worth * 0.25
        diff_mv = target_mv - mv  # 正数需买入，负数需卖出
        
        # 触发再平衡门槛与精简文案
        if curr_pct > 30.0:
            status = "⚠️ 偏高 (需卖出)"
            status_color = "#e76f51"
            diff_str = f"-${abs(diff_mv):,.2f}"
        elif curr_pct < 20.0 and total_net_worth > 0:
            status = "💡 偏低 (需买入)"
            status_color = "#2a9d8f"
            diff_str = f"+${diff_mv:,.2f}"
        else:
            status = "✅ 平衡中"
            status_color = "#4a4a4a"
            diff_str = "$0.00"

        summary_rows.append({
            'cat_name': name, 'mv': mv, 'pct': curr_pct,
            'target_pct': target_pct, 'diff_str': diff_str,
            'status': status, 'status_color': status_color, 'key': key
        })

    # --- 总体占比与再平衡决策看板 (Overall Summary) ---
    st.markdown("##### 📊 总体占比与再平衡决策 (Overall Summary)")
    
    # 渲染 4 个核心分类总计卡片
    p_cols = st.columns(4)
    for idx, s in enumerate(summary_rows):
        with p_cols[idx]:
            st.markdown(f"""
            <div class="pp-card">
                <div class="pp-header">{s['cat_name']}</div>
                <div class="pp-stat">{s['pct']:.1f}% <span style="font-size:12px; color:#888; font-weight:normal;">/ 25%</span></div>
                <div class="pp-sub">总额: ${s['mv']:,.2f}</div>
                <div style="font-size:12px; font-weight:700; color:{s['status_color']}; background:#fff5f7; padding:6px; border-radius:8px; text-align:center;">
                    {s['status']}<br>
                    <span style="font-size:11px; font-weight:600; color:#555;">差额: {s['diff_str']}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
