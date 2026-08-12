import os
import sys
from pathlib import Path

# 确保项目根在 sys.path 且为工作目录 (相对路径配置依赖)
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))
os.chdir(_ROOT)

import pytest
from src.input_reader import InputReader
from src.soil_database import SoilDatabase
from src.precip_chemistry import PrecipChemistry


@pytest.fixture(scope="session")
def profile():
    reader = InputReader("data/soil_survey.csv", "data/exchangeable_ions.csv")
    return reader.build_soil_profile()


@pytest.fixture(scope="session")
def soil_info():
    db = SoilDatabase(json_path="config/soil_mineral_db.json",
                      tbl_path="config/soil_mineral.tbl")
    return db.get_soil_info("red_soil")


@pytest.fixture(scope="session")
def precip_chem():
    return PrecipChemistry()
