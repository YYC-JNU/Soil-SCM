import pytest
from src.config_manager import ConfigManager


@pytest.fixture(scope="module")
def cfg():
    return ConfigManager("config/config.yaml")


def test_default_scenario(cfg):
    assert cfg.config.simulation.scenario == "natural"


def test_default_n_years(cfg):
    assert cfg.config.simulation.n_years > 0


def test_precip_data_loaded(cfg):
    data = cfg.config.precip_chemistry.data
    assert data, "降水数据未加载"
    assert data["pH"] == 5.75
    assert "ions" in data


def test_soil_type(cfg):
    assert cfg.config.soil_data.soil_type == "red_soil"


def test_invalid_n_years(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("simulation:\n  n_years: -1\n", encoding="utf-8")
    with pytest.raises(AssertionError):
        ConfigManager(str(p))


def test_invalid_scenario(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("simulation:\n  n_years: 10\n  scenario: invalid_scen\n",
                 encoding="utf-8")
    with pytest.raises(AssertionError):
        ConfigManager(str(p))


def test_invalid_engine_mode(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("simulation:\n  n_years: 10\n  engine_mode: invalid\n",
                 encoding="utf-8")
    with pytest.raises(AssertionError):
        ConfigManager(str(p))


def test_invalid_output_format(tmp_path):
    p = tmp_path / "bad.yaml"
    p.write_text("simulation:\n  n_years: 10\noutput:\n  format: parquet\n",
                 encoding="utf-8")
    with pytest.raises(AssertionError):
        ConfigManager(str(p))
