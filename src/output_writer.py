"""
模块: output_writer.py
功能: 输出诊断量时间序列 (CSV / NetCDF)

输入: 诊断量时间序列数组
输出: CSV 或 NetCDF 文件
"""

import os
import numpy as np
import pandas as pd
from pathlib import Path
from typing import List, Dict
from datetime import datetime
from src.logging_config import get_logger

logger = get_logger("output_writer")


class OutputWriter:
    """输出写入器"""

    def __init__(self, output_dir: str, output_format: str = 'csv',
                 scenario: str = 'natural'):
        self.output_dir = Path(output_dir)
        self.output_format = output_format
        self.scenario = scenario
        os.makedirs(self.output_dir, exist_ok=True)

        # 存储时间序列数据
        self.time_records = []
        self.data_records = []

    def record_step(self, year: int, month: int, diagnostics: dict):
        """记录单步诊断量"""
        self.time_records.append({
            'year': year,
            'month': month,
            'time_decimal': year + (month - 1) / 12.0,
        })
        self.data_records.append(diagnostics.copy())

    def save(self):
        """保存输出文件"""
        if self.output_format == 'csv':
            self._save_csv()
        elif self.output_format == 'netcdf':
            self._save_netcdf()

    def _save_csv(self):
        """保存为 CSV"""
        if not self.data_records:
            return

        # 合并时间和数据
        all_data = []
        for t, d in zip(self.time_records, self.data_records):
            row = {**t, **d}
            all_data.append(row)

        df = pd.DataFrame(all_data)
        filename = f"soil_scm_{self.scenario}_output.csv"
        filepath = self.output_dir / filename
        df.to_csv(filepath, index=False, encoding='utf-8')
        logger.info("已保存: %s", filepath)

    def _save_netcdf(self):
        """保存为 NetCDF (需要 netCDF4 库)"""
        try:
            import netCDF4 as nc
        except ImportError:
            logger.warning("netCDF4 未安装，回退到 CSV 格式")
            self._save_csv()
            return

        if not self.data_records:
            return

        filename = f"soil_scm_{self.scenario}_output.nc"
        filepath = self.output_dir / filename

        with nc.Dataset(str(filepath), 'w') as ds:
            # 创建维度
            n_steps = len(self.time_records)
            ds.createDimension('time', n_steps)

            # 创建时间变量
            time_var = ds.createVariable('time', 'f8', ('time',))
            time_var[:] = [t['time_decimal'] for t in self.time_records]
            time_var.units = 'years since 2000-01-01'

            # 创建数据变量
            for key in self.data_records[0].keys():
                if isinstance(self.data_records[0][key], (int, float)):
                    var = ds.createVariable(key, 'f8', ('time',))
                    var[:] = [d.get(key, 0.0) for d in self.data_records]

        logger.info("已保存: %s", filepath)

    def plot_results(self, save_path: str = None):
        """绘制结果图"""
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            logger.warning("matplotlib 未安装，跳过绘图")
            return

        if not self.time_records:
            return

        times = [t['time_decimal'] for t in self.time_records]
        phs = [d.get('pH', 7.0) for d in self.data_records]

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.plot(times, phs, 'b-', linewidth=1.5, label='pH')
        ax.set_xlabel('Time (years)')
        ax.set_ylabel('Soil pH')
        ax.set_title(f'Soil pH Evolution - Scenario: {self.scenario}')
        ax.legend()
        ax.grid(True, alpha=0.3)

        if save_path is None:
            save_path = self.output_dir / f"pH_{self.scenario}.png"
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        plt.close()
        logger.info("已保存: %s", save_path)
