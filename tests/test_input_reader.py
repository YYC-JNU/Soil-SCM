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
