# 52 — v0.5.3 LayerCascade 重构 + ET 集成（T3）

**What to build:** `LayerCascade` 重构为 VGM 物理：θ_FC=vgm(−100)（与初始 θ 同源）；可排水量_i=max(0,θ_i−θ_FC,i)×depth_i×1e5 (L/ha)；界面通量_i→i+1 = min(可排水量_i, min(K_r(θ_i)·ksat_i, ksat_{i+1})×1e5×n_days)（θ→θ_s 退化为 D3 min(上下层 ksat) 公式）；底部 L4=深层排水；超饱和溢出计入 runoff；新增 `calc_interface_flux(θ_up,θ_dn,ψ_up,ψ_dn,depth_up,depth_dn,mode="downward")` 纯向下（上行恒 0，mode="bidirectional" 预留 v0.6.0）；`LayerCascade.run()` **最前端**集成 `apply_feddes_et`（顺序 ET→入渗→级联）；Green-Ampt θ_i 改用 L1 当前 θ（删除 main.py `theta_i=0.5×θ_s` 魔法数）。

**Blocked by:** 50、51

**Status:** ready-for-agent

- [ ] 纯向下方向约束：任意状态 q≥0 恒成立、干上层无逆向回流、mode="downward" 上行恒 0（S2 专家★2）
- [ ] θ→θ_s 时界面通量 = min(ksat_i,ksat_{i+1})×1e5×n_days（与 D3 精确一致）
- [ ] θ_FC 可排水量：θ≤θ_FC 不排水；θ>θ_FC 可排水 = (θ−θ_FC)×depth×1e5
- [ ] 底部 L4 深层排水 + 超饱和溢出计入 runoff（既有语义保留）
- [ ] run() 最前端 ET：顺序 ET→入渗→级联（v0.5.3水分平衡闭合.txt §4.3）；水分平衡闭合（入渗+径流+ET+深层排水+Δ储水=降水）
- [ ] Green-Ampt θ_i = L1 当前 θ（main.py 50% 魔法数删除）
- [ ] n_layers=1 完全回退（不进入重构路径）
- [ ] 测试（S2 + S5）：全绿
