"""测试 src/input_reader.py: config 内联字段优先、-1 回退 CSV (v0.2.3)"""

import pytest
from src.input_reader import InputReader

SURVEY_CONFIG = {
    "ph": 5.5, "organic_matter": 25.0, "cec": 14.0, "bulk_density": 1.3,
    "area": 1.0, "effective_depth": 35.0, "available_p": 20.0,
    "available_k": 120.0, "texture": 5, "sand_pct": 40.0,
    "silt_pct": 35.0, "clay_pct": 25.0,
}

EXCH_CONFIG = {
    "exch_ca": 4.0, "exch_mg": 1.0, "exch_k": 0.8, "exch_na": 0.3,
    "exch_al": 1.5, "exch_h": 0.8,
}


def _reader():
    return InputReader("data/soil_survey.csv", "data/exchangeable_ions.csv")


def test_profile_from_csv_default():
    """不传 config 参数 (向后兼容) → 回退 CSV"""
    profile = _reader().build_soil_profile()
    assert profile.ph == 5.0
    assert profile.texture == "壤土"
    assert profile.cec == 12.0
    assert profile.exch_ca == 3.0
    assert profile.exch_al == 2.0


def test_profile_all_minus_one_fallback_csv():
    """全 -1 字段 → 回退 CSV"""
    survey = {k: -1.0 for k in SURVEY_CONFIG}
    exch = {k: -1.0 for k in EXCH_CONFIG}
    survey["texture"] = -1
    profile = _reader().build_soil_profile(
        survey_config=survey, exchangeable_config=exch)
    assert profile.ph == 5.0
    assert profile.texture == "壤土"


def test_profile_from_config():
    """全有效值 → 使用 config 内联字段"""
    profile = _reader().build_soil_profile(
        survey_config=SURVEY_CONFIG, exchangeable_config=EXCH_CONFIG)
    assert profile.ph == 5.5
    assert profile.cec == 14.0
    assert profile.bulk_density == 1.3
    assert profile.effective_depth == 35.0
    assert profile.exch_ca == 4.0
    assert profile.exch_al == 1.5


def test_profile_texture_code_to_name():
    """质地编码 5 → 中壤土 (config/texture_code.json)"""
    profile = _reader().build_soil_profile(
        survey_config=SURVEY_CONFIG, exchangeable_config=EXCH_CONFIG)
    assert profile.texture == "中壤土"


def test_profile_survey_config_exchange_fallback():
    """survey 用 config, exchangeable_ions 全 -1 回退 CSV (Q8 两独立块)"""
    exch = {k: -1.0 for k in EXCH_CONFIG}
    profile = _reader().build_soil_profile(
        survey_config=SURVEY_CONFIG, exchangeable_config=exch)
    assert profile.ph == 5.5            # config
    assert profile.exch_ca == 3.0       # CSV 回退


def test_profile_missing_csv_raises(tmp_path):
    """全 -1 但 CSV 不存在 → FileNotFoundError (Q14)"""
    reader = InputReader(str(tmp_path / "nofile.csv"),
                         str(tmp_path / "nofile2.csv"))
    with pytest.raises(FileNotFoundError):
        reader.build_soil_profile()


def test_profile_config_no_csv_ok(tmp_path):
    """全有效值 + CSV 不存在 → 正常使用 config (不读 CSV)"""
    reader = InputReader(str(tmp_path / "nofile.csv"),
                         str(tmp_path / "nofile2.csv"))
    profile = reader.build_soil_profile(
        survey_config=SURVEY_CONFIG, exchangeable_config=EXCH_CONFIG)
    assert profile.ph == 5.5
    assert profile.exch_ca == 4.0


# ==================== L6 (v0.4.0): 逐层 profile 构建 ====================

from src.config_manager import LayerOverrideConfig


def test_apply_layer_override_partial(profile):
    """L6/T2: 部分覆盖 — 只覆盖指定字段, 其余保持默认; effective_depth 由层深派生"""
    reader = _reader()
    lo = LayerOverrideConfig(cec=15.0, bulk_density=1.1, exch_al=3.0)
    p = reader.apply_layer_override(profile, lo, depth=10.0)
    assert p is not profile
    assert p.cec == 15.0
    assert p.bulk_density == 1.1
    assert p.exch_al == 3.0
    assert p.effective_depth == 10.0
    # 未覆盖字段保持默认
    assert p.ph == profile.ph == 5.0
    assert p.organic_matter == profile.organic_matter
    assert p.exch_ca == profile.exch_ca


def test_apply_layer_override_empty(profile):
    """L6/T2: 空覆盖 → 完全回退默认, 仅 effective_depth 按层深派生; 原对象不变"""
    reader = _reader()
    p = reader.apply_layer_override(profile, LayerOverrideConfig(), depth=20.0)
    assert p.effective_depth == 20.0
    assert p.cec == profile.cec
    assert p.ph == profile.ph
    assert p.exch_al == profile.exch_al
    # 原对象不被修改 (深拷贝语义)
    assert profile.effective_depth != 20.0


def test_apply_layer_override_full(profile):
    """L6/T2: 全字段覆盖 (ph/有机质/CEC/容重/交换性离子×6)"""
    reader = _reader()
    lo = LayerOverrideConfig(ph=4.5, organic_matter=30.0, cec=15.0,
                             bulk_density=1.2, exch_ca=3.5, exch_mg=1.0,
                             exch_k=0.4, exch_na=0.2, exch_al=3.0, exch_h=1.0)
    p = reader.apply_layer_override(profile, lo, depth=10.0)
    assert p.ph == 4.5
    assert p.organic_matter == 30.0
    assert p.cec == 15.0
    assert p.bulk_density == 1.2
    assert p.exch_ca == 3.5
    assert p.exch_mg == 1.0
    assert p.exch_k == 0.4
    assert p.exch_na == 0.2
    assert p.exch_al == 3.0
    assert p.exch_h == 1.0
    assert p.effective_depth == 10.0


def test_apply_mineral_overrides_increment(soil_info):
    """L6/T2: 矿物增量替换 — 只替换指定矿物质量分数, 未覆盖矿物保留, 不归一化"""
    from src.soil_database import apply_mineral_overrides
    orig_goethite = soil_info.minerals["goethite"].mass_fraction
    overridden = apply_mineral_overrides(soil_info, {"goethite": 0.10})
    assert overridden is not soil_info
    assert overridden.minerals["goethite"].mass_fraction == 0.10
    # 未覆盖矿物保留原质量分数
    for name, minfo in soil_info.minerals.items():
        if name != "goethite":
            assert (overridden.minerals[name].mass_fraction
                    == pytest.approx(minfo.mass_fraction))
    # 原对象不变
    assert soil_info.minerals["goethite"].mass_fraction == pytest.approx(orig_goethite)
