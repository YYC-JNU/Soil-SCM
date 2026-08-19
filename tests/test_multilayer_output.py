"""
测试 WF2 多分层输出 (OutputWriter.record_multi_step)
  Q6: 列名加层深度后缀; 单层列名不变
"""

from src.output_writer import OutputWriter


def test_record_multi_step_layer_suffixes(tmp_path):
    """WF2/Q6: 多层诊断列名加深度后缀"""
    ow = OutputWriter(str(tmp_path), n_layers=2,
                      layer_depths=[10.0, 20.0])
    ow.record_multi_step(1, 1, [
        {"pH": 5.0, "base_saturation": 30.0},
        {"pH": 5.5, "base_saturation": 40.0},
    ])
    merged = ow.data_records[0]
    assert merged["pH_0_10"] == 5.0
    assert merged["base_saturation_0_10"] == 30.0
    assert merged["pH_10_30"] == 5.5
    assert merged["base_saturation_10_30"] == 40.0
    assert "pH" not in merged  # 无未加后缀的列


def test_record_multi_step_global_columns(tmp_path):
    """v0.5.3 (S6): global_diagnostics 月度全局列不加层后缀"""
    ow = OutputWriter(str(tmp_path), n_layers=2,
                      layer_depths=[10.0, 20.0])
    ow.record_multi_step(1, 1, [
        {"pH": 5.0}, {"pH": 5.5},
    ], global_diagnostics={"aet_mm": 42.0, "et_deficit_mm": 3.5})
    merged = ow.data_records[0]
    assert merged["aet_mm"] == 42.0          # 全局列无后缀
    assert merged["et_deficit_mm"] == 3.5
    assert merged["pH_0_10"] == 5.0          # 层列仍带后缀


def test_record_step_single_layer_unchanged(tmp_path):
    """WF2/Q6: 单层 (record_step) 列名不变"""
    ow = OutputWriter(str(tmp_path))
    ow.record_step(1, 1, {"pH": 5.0, "base_saturation": 30.0})
    assert ow.data_records[0]["pH"] == 5.0
    assert ow.data_records[0]["base_saturation"] == 30.0


def test_layer_suffixes_default_four(tmp_path):
    """WF2/Q6: 默认 4 层 (无 layer_depths) 等分 0~60cm"""
    ow = OutputWriter(str(tmp_path), n_layers=4)
    suffixes = ow._layer_suffixes()
    assert suffixes == ["0_15", "15_30", "30_45", "45_60"]


def test_csv_save_multi_layer(tmp_path):
    """WF2/Q6: 多层 CSV 保存成功且含后缀列"""
    ow = OutputWriter(str(tmp_path), n_layers=2,
                      layer_depths=[10.0, 20.0])
    ow.record_multi_step(1, 1, [
        {"pH": 5.0, "base_saturation": 30.0},
        {"pH": 5.5, "base_saturation": 40.0},
    ])
    ow.save()
    csv_file = tmp_path / "soil_scm_natural_output.csv"
    assert csv_file.exists()
    content = csv_file.read_text(encoding="utf-8")
    assert "pH_0_10" in content
    assert "pH_10_30" in content


def test_csv_save_multi_layer_with_variables_filter(tmp_path):
    """WF2/Q6: 多层 CSV + variables 过滤时, 基础变量名匹配层后缀列"""
    ow = OutputWriter(str(tmp_path), n_layers=2,
                      layer_depths=[10.0, 20.0],
                      variables=["pH", "base_saturation"])
    ow.record_multi_step(1, 1, [
        {"pH": 5.0, "base_saturation": 30.0, "exchangeable_Al": 1.0},
        {"pH": 5.5, "base_saturation": 40.0, "exchangeable_Al": 2.0},
    ])
    ow.save()
    csv_file = tmp_path / "soil_scm_natural_output.csv"
    content = csv_file.read_text(encoding="utf-8")
    # 层后缀列应保留 (pH→pH_0_10, pH_10_30)
    assert "pH_0_10" in content
    assert "pH_10_30" in content
    # 未配置变量 (exchangeable_Al) 的层列不应输出
    assert "exchangeable_Al_0_10" not in content


def test_apply_hydrology_events_month_conservation(profile):
    """v0.6.0 (Q3/Q15): 事件级水文编排 — Σ事件降水=月降水, 入渗+径流=降水"""
    import pytest
    from main import _apply_hydrology_events
    from src.phreeqc_engine import SoilState
    states = [SoilState(theta=0.41)]
    forcing = {"precip": 158.0, "pet": 0.0}
    hydrology, runoff_mm, runoff_extra = _apply_hydrology_events(
        states, [profile], forcing, 0, 0, seed=42, bypass_fraction=0.2)
    # events 键: 每场 precip_mm, Σ = 月降水 (质量守恒)
    assert len(hydrology["events"]) >= 4
    total_ev_precip = sum(e["precip_mm"] for e in hydrology["events"])
    assert total_ev_precip == pytest.approx(158.0, rel=1e-6)
    # 月入渗(mm) + 月径流(mm) = 月降水 (Green-Ampt 守恒)
    total_inf = sum(e["inflows"][0] for e in hydrology["events"]) / 10000.0
    assert total_inf + runoff_mm == pytest.approx(158.0, abs=0.5)
    # 月聚合键 = Σ 各场
    assert hydrology["inflows"][0] == pytest.approx(
        sum(e["inflows"][0] for e in hydrology["events"]))
    assert hydrology["drains"][0] == pytest.approx(
        sum(e["drains"][0] for e in hydrology["events"]))
