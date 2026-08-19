"""测试 v0.6.0 First-Flush 事件输出 (S6 seam, spec 55 Q14)"""

import pandas as pd
from src.output_writer import OutputWriter


def test_event_output_false_no_event_csv(tmp_path):
    """Q14: event_output=false (默认) 不产生事件明细 CSV"""
    ow = OutputWriter(str(tmp_path), scenario="natural")
    ow.record_step(1, 1, {"pH": 5.0})
    ow.save()
    assert not (tmp_path / "event_leaching_natural.csv").exists()


def test_record_event_and_save_csv_columns(tmp_path):
    """Q14: 事件明细 CSV 列结构 (日期/场次/降水/各层淋失/pH)"""
    ow = OutputWriter(str(tmp_path), scenario="natural")
    ow.record_event({"year": 1, "month": 3, "event": 1, "precip_mm": 50.0,
                     "leach_N_L1_mmol": 12.3, "leach_base_L1_mmol": 45.6,
                     "ph_L1": 4.8})
    ow.record_event({"year": 1, "month": 3, "event": 2, "precip_mm": 10.0,
                     "leach_N_L1_mmol": 1.2, "leach_base_L1_mmol": 5.6,
                     "ph_L1": 4.9})
    ow.save()
    fp = tmp_path / "event_leaching_natural.csv"
    assert fp.exists()
    df = pd.read_csv(fp)
    assert list(df.columns) == ["year", "month", "event", "precip_mm",
                                "leach_N_L1_mmol", "leach_base_L1_mmol",
                                "ph_L1"]
    assert len(df) == 2
    assert df["event"].tolist() == [1, 2]
    assert df["precip_mm"].tolist() == [50.0, 10.0]
