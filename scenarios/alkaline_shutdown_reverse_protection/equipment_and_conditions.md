# 设备锚点、交互热点与工况草案

## 设备主图

优先采用 TU Clausthal EST 的工业级碱性电解槽测试平台实拍：

- 官方页面：[Discover our cutting-edge water electrolyser test facility in action](https://www.est.tu-clausthal.de/nachrichtendetail/discover-our-cutting-edge-water-electrolyser-test-facility-in-action)
- 页面图片：[工业级测试平台图片](https://www.est.tu-clausthal.de/fileadmin/_processed_/e/b/csm_StaR-Electrolyzer_e878e02cec.png)
- 页面说明该平台最高可测约150 kW、4000 A级堆栈；图片为该研究设施实拍。上线时保留机构与页面署名，并确认该图片对项目网站的再使用许可。不要把图片描述成项目自有设备。
- 可选的中文系统照片：[清华大学可再生能源电解制氢碱性试验平台](https://www.sigs.tsinghua.edu.cn/2025/0604/c7688a272312/page.htm)，可用于核对部件布局；同样需遵守原站图片授权。

## 四个交互热点

| 热点 | 一句话说明 | 关联红线 |
|---|---|---|
| 整流电源与直流母线 | 控制堆电流爬坡、功率骤降和停机断路时序，并同步保存电源输出。 | R03、R04、R08 |
| 双极电解槽堆与单片采集 | 观察堆总压及可用的单片电压/电极电位，识别停机后的反向放电和弱片。 | R03、R07 |
| 碱液循环、换热与温度测点 | 控制电解液流量和降温过程；停机时不能无条件套用“继续循环”或“立即停泵”。 | R06 |
| 气液分离器与H₂/O₂纯度分析 | 监测气体交叉、两侧压力和联锁状态，负荷调度需服从气体纯度边界。 | R01、R02、R05 |

## 六项标准测试工况（用于场景预览，不替代具体设备SOP）

1. **电解液**：碱性KOH；综述常见20–30 wt%，更宽设备范围见来源；记录浓度、补液批次与电导率。
2. **温度**：以设备额定工况为准；文献常见50–80°C。每个决策窗口记录堆入口/出口温度和温差。
3. **负荷与压力**：同步记录额定负荷百分比、电流密度、堆压及H₂/O₂两侧绝对压力/差压；记录单/混合电解液回路状态。
4. **电源与动态输入**：记录可再生功率/调度命令、整流器电流、电压、爬坡率、纹波和时间戳；使用设备可接受的动态输入曲线。
5. **停机状态序列**：生产→降载/待机→整流器断开→电解液泵/冷却/吹扫动作→压力与气体分析确认→再启动；逐步记录状态位及实际动作时刻。
6. **安全与电化学测量**：测H₂-in-O₂、O₂-in-H₂、堆/单片电压、温度、压力、流量；若只在台架设置参比电极，记录Ni阴极电位 vs RHE。EU harmonised protocol给出1 Hz推荐采样率，但快速反向电流诊断应按仪器带宽提高采样率。

## 代表性对比曲线

优先定义为**停机瞬态曲线组**：横轴为断电后的时间；左轴绘制反向电流 `I_rev(t)` 或累计反向电荷 `Q_rev(t)=∫|I_rev|dt`，右轴绘制阴极电位 `E_cathode(t)` vs RHE。对比“现行停机策略”和“受保护/受控停机策略”，并标注0.6 V vs RHE这一Ni材料研究阈值。JACS Au 2022 Figure 3可作为实验设计参考，但该加速电化学测试不是工业堆栈的性能对照。没有现场原始曲线前，网页应显示“指标定义/文献示例”，不要绘制项目优化前后曲线。

## 推荐数据字段

`timestamp_utc, run_id, stack_id, cell_id, command_state, renewable_power_kw, rectifier_current_a, stack_voltage_v, cell_voltage_v, current_density_a_cm2, electrolyte_inlet_temp_c, electrolyte_outlet_temp_c, electrolyte_flow_l_min, koh_wt_pct, h2_pressure_bar_abs, o2_pressure_bar_abs, delta_pressure_bar, h2_in_o2_vol_pct, o2_in_h2_vol_pct, reverse_current_a, cathode_potential_v_rhe, purge_state, pump_state, cooling_state, alarm_code, shutdown_reason, measurement_quality, source_id`。

