# -*- coding: utf-8 -*-
"""实验 L6: 逐层参数覆盖 vs 等参基线 — 真实剖面约束下的 fertilizer 行为诊断

   对比两个 4 层 fertilizer 长期模拟:
     - baseline: 等参 4 层 (各层默认参数相同, 现状行为)
     - real:     L6 layer_overrides 真实剖面 (表层薄+低pH+高CEC+高有机质+富铁氧化物
                 / 底层厚+紧实+高pCO₂)

   输出图片标注 **good influence (绿色) 与 bad influence (红色)**:
     - good:  真实剖面使 AlX₃ 耗尽推迟 / pH 突升延后或幅度降低 (缓冲增强)
     - bad:   真实剖面某层 AlX₃ 更早耗尽 / pH 酸化加剧 (薄层缓冲小 / 高 pCO₂)

   用法 (从项目根运行):
     python tools/plot_L6_layer_overrides.py [--years 30] [--layers 4] [--out output/...png]
"""
import sys
import argparse
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, '.')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from src.input_reader import InputReader
from src.soil_database import SoilDatabase, apply_mineral_overrides
from src.config_manager import LayerOverrideConfig
from src.phreeqc_engine import PhreeqcEngine
from src.climate_forcing import ClimateForcing
from src.scenario_controller import ScenarioController

DEFAULT_DEPTHS = [10, 10, 20, 20]  # 0-10/10-20/20-40/40-60cm
THRESHOLD_ALX3 = 1000.0            # AlX3 耗尽阈值 (mol)


def real_layer_overrides(layers):
    """真实剖面逐层覆盖 (L6 案例): 表层薄+低pH+高CEC+高有机质+富铁氧化物, 底层紧实+高pCO2"""
    o = [
        LayerOverrideConfig(ph=4.5, organic_matter=30.0, cec=15.0,
                            bulk_density=1.1, exch_al=3.0, pCO2=0.020,
                            minerals={"goethite": 0.10}),
        LayerOverrideConfig(),  # 10-20cm 无覆盖
        LayerOverrideConfig(cec=10.0, bulk_density=1.35),
        LayerOverrideConfig(bulk_density=1.5, pCO2=0.030),
    ]
    return o[:layers]


def build_states(engine, reader, profile, info, pco2, depths, overrides):
    """构建初始状态列表: overrides 为 None 时各层默认相同 (等参基线)"""
    layer_pco2s = None
    if overrides:
        states = []
        layer_pco2s = []
        for i, lo in enumerate(overrides):
            depth = depths[i]
            p = reader.apply_layer_override(profile, lo, depth)
            m = (apply_mineral_overrides(info, lo.minerals)
                 if lo.minerals else info)
            pc = lo.pCO2 if lo.pCO2 is not None else pco2
            layer_pco2s.append(pc)
            states.append(engine.build_initial_state(p, m, pc))
        return states, layer_pco2s
    return ([engine.build_initial_state(profile, info, pco2)
             for _ in range(len(depths))], None)


def run_simulation(engine, reader, profile, info, pco2, depths, overrides,
                   n_years, scenario):
    """运行 n 层长期模拟, 返回 (years, per_layer_ph, per_layer_alx3)"""
    states, layer_pco2s = build_states(
        engine, reader, profile, info, pco2, depths, overrides)
    climate = ClimateForcing(1893.0, 25.0, 0.015, 25.0, 0.05,
                             n_years, scenario)
    ctrl = ScenarioController(scenario, {}, {})
    years = []
    per_layer_ph = [[] for _ in range(len(depths))]
    per_layer_alx3 = [[] for _ in range(len(depths))]
    for y in range(n_years):
        for m in range(12):
            forcing = climate.get_monthly_forcing(y, m)
            action = ctrl.get_action(y + 1, m + 1)
            states, _ = engine.run_monthly_multi_layer(
                states, forcing, action, profile, layer_pco2s=layer_pco2s)
        years.append(y + 1)
        for i, s in enumerate(states):
            per_layer_ph[i].append(s.ph)
            per_layer_alx3[i].append(s.exchange.get('AlX3', 0.0))
    return years, per_layer_ph, per_layer_alx3


def depletion_year(alx3_series, threshold=THRESHOLD_ALX3):
    """AlX3 首次低于阈值的一年 (1-based), 未耗尽返回 None"""
    for i, v in enumerate(alx3_series):
        if v < threshold:
            return i + 1
    return None


def impact_tag(base_alx3, real_alx3, threshold=THRESHOLD_ALX3):
    """判定真实剖面相对等参基线的影响 (纯逻辑, 供绘图标注与测试)

    返回 'good' / 'bad' / 'neutral':
      - good: 真实剖面 AlX₃ 未耗尽而基线耗尽, 或真实耗尽年晚于基线 (缓冲增强)
      - bad:  真实剖面耗尽而基线未耗尽, 或真实耗尽年早于基线
      - neutral: 两者耗尽情况一致 (均未耗尽/同年耗尽)
    """
    base_dep = depletion_year(base_alx3, threshold)
    real_dep = depletion_year(real_alx3, threshold)
    if real_dep is None and base_dep is not None:
        return 'good'
    if real_dep is not None and base_dep is None:
        return 'bad'
    if real_dep and base_dep and real_dep > base_dep:
        return 'good'
    if real_dep and base_dep and real_dep < base_dep:
        return 'bad'
    return 'neutral'


def annotate_impact(ax, base_alx3, real_alx3, layer_label):
    """对单层计算并标注 good/bad influence (绿色 good / 红色 bad)"""
    base_dep = depletion_year(base_alx3)
    real_dep = depletion_year(real_alx3)
    tag = impact_tag(base_alx3, real_alx3)
    n_years = len(base_alx3)

    if tag == 'good':
        if real_dep is None and base_dep is not None:
            msg = (f"[GOOD] {layer_label}: AlX3 never depleted "
                   f"(baseline depleted y{base_dep})")
            ax.annotate(msg, xy=(0.42, 0.92), textcoords='axes fraction',
                        color='green', fontsize=10, fontweight='bold')
        else:
            ax.annotate(f"[GOOD] {layer_label}: AlX3 depletion delayed "
                        f"(y{base_dep} -> y{real_dep})",
                        xy=(real_dep, THRESHOLD_ALX3), xytext=(0.45, 0.92),
                        textcoords='axes fraction', color='green',
                        fontsize=10, fontweight='bold',
                        arrowprops=dict(arrowstyle='->', color='green'))
    elif tag == 'bad':
        if base_dep is None:
            msg = (f"[BAD] {layer_label}: AlX3 depleted y{real_dep} "
                   f"(baseline not depleted)")
        else:
            msg = (f"[BAD] {layer_label}: AlX3 depleted earlier "
                   f"(y{real_dep}<y{base_dep})")
        ax.annotate(msg, xy=(real_dep, THRESHOLD_ALX3), xytext=(0.03, 0.85),
                    textcoords='axes fraction', color='red',
                    fontsize=10, fontweight='bold',
                    arrowprops=dict(arrowstyle='->', color='red'))
    return tag


def main():
    parser = argparse.ArgumentParser(description='L6 逐层参数覆盖诊断实验')
    parser.add_argument('--years', type=int, default=30)
    parser.add_argument('--layers', type=int, default=4)
    parser.add_argument('--out', type=str,
                        default='output/L6_layer_overrides_good_bad.png')
    parser.add_argument('--scenario', type=str, default='fertilizer')
    args = parser.parse_args()

    n = args.layers
    depths = DEFAULT_DEPTHS[:n]
    reader = InputReader('data/soil_survey.csv', 'data/exchangeable_ions.csv')
    profile = reader.build_soil_profile()
    db = SoilDatabase(json_path='config/soil_mineral_db.json',
                      tbl_path='config/soil_mineral.tbl')
    info = db.get_soil_info('red_soil')
    pco2 = db.get_pCO2('red_soil')

    engine = PhreeqcEngine(database='phreeqc.dat', mode='phreeqc')

    print(f"=== L6: 真实剖面 vs 等参基线 ({args.scenario}, {args.years} 年, {n} 层) ===")
    print("运行等参基线...")
    months_b, ph_b, alx3_b = run_simulation(
        engine, reader, profile, info, pco2, depths, None,
        args.years, args.scenario)
    print("运行真实剖面 (layer_overrides)...")
    months_r, ph_r, alx3_r = run_simulation(
        engine, reader, profile, info, pco2, depths,
        real_layer_overrides(n), args.years, args.scenario)

    # ---- 绘图: 2 子图 ----
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 12))
    base_colors = ['#9e9e9e', '#bdbdbd', '#d6d6d6', '#eeeeee']
    real_colors = ['#1f77b4', '#2ca02c', '#ff7f0e', '#9467bd']

    for i in range(n):
        ax1.plot(months_b, ph_b[i], '-', color=base_colors[i], lw=1.6,
                 label=f'baseline L{i+1}')
        ax1.plot(months_r, ph_r[i], '-', color=real_colors[i], lw=2.4,
                 label=f'real profile L{i+1}')
    ax1.set_xlabel('Time (years)', fontsize=12)
    ax1.set_ylabel('pH', fontsize=12)
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc='best', fontsize=9)
    ax1.set_title(
        f'L6: Layer pH — Equal-parameter baseline vs Real profile overrides '
        f'({args.scenario}, {args.years}y, {n} layers)', fontsize=13)

    for i in range(n):
        ax2.plot(months_b, alx3_b[i], '-', color=base_colors[i], lw=1.6,
                 label=f'baseline L{i+1}')
        ax2.plot(months_r, alx3_r[i], '-', color=real_colors[i], lw=2.4,
                 label=f'real profile L{i+1}')
    ax2.set_yscale('log')
    ax2.set_xlabel('Time (years)', fontsize=12)
    ax2.set_ylabel('AlX3 (mol, log)', fontsize=12)
    ax2.grid(True, alpha=0.3, which='both')
    ax2.axhline(THRESHOLD_ALX3, color='gray', ls='--', lw=1.0,
                label=f'depletion threshold ({THRESHOLD_ALX3:g})')
    ax2.set_title('L6: Layer AlX3 — Equal-parameter baseline vs Real profile '
                  '(good green / bad red annotations)', fontsize=13)
    ax2.legend(loc='upper right', fontsize=9)

    # ---- good/bad influence 标注 (逐层) ----
    impacts = []
    for i in range(n):
        tag = annotate_impact(ax2, alx3_b[i], alx3_r[i], f'Layer {i+1}')
        impacts.append((i + 1, tag))

    # ---- 打印数据摘要 ----
    print("\n=== AlX3 耗尽年对比 (阈值 %.0f mol) ===" % THRESHOLD_ALX3)
    print(f"{'层':<6}{'等参基线':<12}{'真实剖面':<12}{'影响'}")
    for i in range(n):
        b_dep = depletion_year(alx3_b[i])
        r_dep = depletion_year(alx3_r[i])
        b_s = f'y{b_dep}' if b_dep else '未耗尽'
        r_s = f'y{r_dep}' if r_dep else '未耗尽'
        print(f"L{i+1:<5}{b_s:<12}{r_s:<12}{impacts[i][1]}")

    print("\n=== 表层 pH 末年对比 ===")
    print(f"  等参基线表层 pH: {ph_b[0][-1]:.3f}")
    print(f"  真实剖面表层 pH: {ph_r[0][-1]:.3f}")
    if ph_b[0][-1] > 8.0 and ph_r[0][-1] <= ph_b[0][-1]:
        print("  ✅ good: 真实剖面抑制 pH 突升")
    elif ph_b[0][-1] <= 8.0 and ph_r[0][-1] > 8.0:
        print("  ⚠️ bad: 真实剖面导致 pH 突升")

    plt.tight_layout()
    fig.savefig(args.out, dpi=150, bbox_inches='tight')
    print(f"\n[PLOT] 已保存: {args.out}")


if __name__ == '__main__':
    main()

