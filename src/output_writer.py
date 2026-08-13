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
                 scenario: str = 'natural', variables: List[str] = None,
                 n_layers: int = 1, layer_depths: List[float] = None):
        self.output_dir = Path(output_dir)
        self.output_format = output_format
        self.scenario = scenario
        self.variables = variables  # 输出变量列表 (Q11), None=全部
        # WF2/Q6: 多分层输出 — 列名加层后缀 (如 pH_0_10); 单层列名不变
        self.n_layers = n_layers
        self.layer_depths = layer_depths  # 每层厚度 (cm), 用于后缀命名
        os.makedirs(self.output_dir, exist_ok=True)

        # 存储时间序列数据
        self.time_records = []
        self.data_records = []

    def record_step(self, year: int, month: int, diagnostics: dict):
        """记录单步诊断量 (单层)"""
        self.time_records.append({
            'year': year,
            'month': month,
            'time_decimal': year + (month - 1) / 12.0,
        })
        self.data_records.append(diagnostics.copy())

    def record_multi_step(self, year: int, month: int,
                          layer_diagnostics: List[dict]):
        """记录多分层诊断量 (WF2/Q6: 列名加层深度后缀)

        参数:
            layer_diagnostics: 每层诊断 dict 列表, 长度 = n_layers
        后缀规则: 每层用深度区间命名 (0_10, 10_20, 20_40, 40_60...),
                 列如 pH_0_10, base_saturation_10_20.
        """
        suffixes = self._layer_suffixes()
        merged = {}
        for diag, suffix in zip(layer_diagnostics, suffixes):
            for key, val in diag.items():
                merged[f"{key}_{suffix}"] = val
        self.record_step(year, month, merged)

    def _layer_suffixes(self) -> List[str]:
        """生成每层的深度区间后缀 (如 0_10, 10_20)

        若未提供 layer_depths, 按等分深度假设 (默认各层厚度相同);
        实际由 config 提供 (ROADMAP: 各层默认参数相同)。
        """
        if self.layer_depths and len(self.layer_depths) == self.n_layers:
            bounds = [0.0]
            for d in self.layer_depths:
                bounds.append(bounds[-1] + d)
            return [f"{int(bounds[i])}_{int(bounds[i+1])}"
                    for i in range(self.n_layers)]
        # 兜底: 等分 0~60cm (与默认 4 层一致)
        total = 60.0 if self.n_layers > 1 else 0.0
        step = total / self.n_layers if self.n_layers > 1 else 0.0
        return [f"{int(i*step)}_{int((i+1)*step)}" for i in range(self.n_layers)]


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
        # Q11: 按 config.output.variables 过滤输出列 (保留时间列)
        # WF2/Q6: 多分层时列名带层后缀 (pH_0_10), 基础变量名需前缀匹配
        if self.variables:
            time_cols = [c for c in ('year', 'month', 'time_decimal') if c in df.columns]
            var_cols = []
            for v in self.variables:
                if v in df.columns:
                    var_cols.append(v)
                else:
                    # 层后缀列: pH → pH_0_10, pH_10_20 ...
                    layer_cols = [c for c in df.columns if c.startswith(v + '_')]
                    var_cols.extend(layer_cols)
            df = df[time_cols + var_cols]
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
            keys = [k for k in self.data_records[0].keys()
                    if isinstance(self.data_records[0][k], (int, float))]
            if self.variables:
                # WF2/Q6: 支持层后缀列前缀匹配 (pH → pH_0_10)
                filtered = []
                for k in keys:
                    if k in self.variables:
                        filtered.append(k)
                    elif any(k.startswith(v + '_') for v in self.variables):
                        filtered.append(k)
                keys = filtered
            for key in keys:
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
