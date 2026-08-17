# -*- coding: utf-8 -*-
"""实验3 绘图: 多层(n_layers=4)下 SURFACE 有无对比 (从缓存数据绘制)
   子图1: 有无 surface 下 4 层土壤 pH 变化
   子图2: 有无 surface 下 4 层土壤 Al/K/Mg/Na/Ca 离子浓度变化
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

N_YEARS = 30
IONS = ['Al', 'K', 'Mg', 'Na', 'Ca']
ION_COLORS = {'Al': '#9467bd', 'K': '#2ca02c', 'Mg': '#1f77b4',
              'Na': '#ff7f0e', 'Ca': '#d62728'}

# 从缓存加载
d_off = np.load('output/.exp3_off_hist.npz', allow_pickle=True)
d_on = np.load('output/.exp3_on_hist.npz', allow_pickle=True)
ph_off = d_off['ph_all']   # shape (30, 4)
ion_off = d_off['ion_all'] # shape (30, 4, 5)
ph_on = d_on['ph_all']
ion_on = d_on['ion_all']
months = np.arange(1, N_YEARS + 1)
print(f"缓存加载完成: off={ph_off.shape}, on={ph_on.shape}")
print(f"off 末pH: {ph_off[-1]}, on 末pH: {ph_on[-1]}")

# ---- 绘图: 上下2子图 ----
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(13, 12))
LAYER_STYLES = ['-', '--', '-.', ':']
layer_names = ['Layer 1', 'Layer 2', 'Layer 3', 'Layer 4']

# 子图1: 4层 pH (黑色=off, 红色=on)
for i in range(4):
    ax1.plot(months, ph_off[:, i], LAYER_STYLES[i], lw=1.8, color='k',
             label=f'{layer_names[i]} surface off')
    ax1.plot(months, ph_on[:, i], LAYER_STYLES[i], lw=1.8, color='r',
             label=f'{layer_names[i]} surface on')
ax1.set_xlabel('Time (years)', fontsize=12)
ax1.set_ylabel('pH', fontsize=12)
ax1.grid(True, alpha=0.3)
ax1.legend(loc='upper left', bbox_to_anchor=(1.02, 1.0), fontsize=8, ncol=2)
ax1.set_title(f'Exp3: 4-Layer pH — Surface ON/OFF (natural, {N_YEARS} years)',
              fontsize=13)

# 子图2: 4层离子 (实线=off, 虚线=on)
for k_idx, k in enumerate(IONS):
    for i in range(4):
        ax2.plot(months, ion_off[:, i, k_idx], LAYER_STYLES[i], lw=1.2,
                 color=ION_COLORS[k],
                 label=f'{k} L{i+1} off' if i == 0 else None)
        ax2.plot(months, ion_on[:, i, k_idx], LAYER_STYLES[i], lw=1.2,
                 color=ION_COLORS[k], ls='--',
                 label=f'{k} L{i+1} on' if i == 0 else None)
ax2.set_xlabel('Time (years)', fontsize=12)
ax2.set_ylabel('Ion concentration (mol/kgw, log)', fontsize=12)
ax2.set_yscale('log')
ax2.grid(True, alpha=0.3, which='both')
handles, labels = ax2.get_legend_handles_labels()
ax2.legend(handles, labels, loc='upper left', bbox_to_anchor=(1.02, 1.0),
           fontsize=7, ncol=2)
ax2.set_title('4-Layer Ion Concentrations — Surface ON/OFF (log scale)',
              fontsize=13)

plt.tight_layout(rect=[0, 0, 0.85, 1])
out = 'output/exp3_surface_onoff.png'
fig.savefig(out, dpi=150, bbox_inches='tight')
print(f"[PLOT] 已保存: {out}")

# 数据摘要
print("\n=== 末年 4 层 pH 对比 ===")
print(f"{'层':<8}{'off pH':<10}{'on pH':<10}")
for i in range(4):
    print(f"{layer_names[i]:<8}{ph_off[-1, i]:<10.3f}{ph_on[-1, i]:<10.3f}")
print("\n=== 末年 4 层离子对比 (off / on, mol/kgw) ===")
for i in range(4):
    print(f"{layer_names[i]}:")
    for k_idx, k in enumerate(IONS):
        print(f"  {k:<4} off={ion_off[-1, i, k_idx]:.2e}  "
              f"on={ion_on[-1, i, k_idx]:.2e}")
