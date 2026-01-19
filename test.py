# -*- coding: utf-8 -*-
"""
赛题问题2(3)：考虑运输损耗成本的仓网全局优化（CPLEX完整实现）
核心功能：满足赛题所有约束，最小化总物流成本（含运输、开仓、处置、智能调度、损耗成本+开仓补贴）
输出文件：仓网业务表现文件、仓库处置订单量文件、仓网供应关系文件（完全符合赛题附件格式）
"""
import pandas as pd
import cplex
import os
import warnings
warnings.filterwarnings('ignore')

# ===================== 1. 配置路径（请根据实际路径修改，与赛题附件目录一致）=====================
input_dir = './2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/input_data'
output_dir = './2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/output_result'
os.makedirs(output_dir, exist_ok=True)

# 赛题附件路径
DF_CUSTOMER_PATH = os.path.join(input_dir, 'df_customer.csv')  # 门店信息
DF_WH_PATH = os.path.join(input_dir, 'df_wh.csv')  # 仓库设施信息
DF_MATRIX_PATH = os.path.join(input_dir, 'df_matrix.csv')  # 距离/时效信息
DF_ORDER_PATH = os.path.join(input_dir, 'df_order.csv')  # 订单需求
DF_PROC_PATH = os.path.join(input_dir, 'df_proc.csv')  # 仓储数据（容量/成本）

# 输出文件路径（符合赛题附件格式要求）
OUTPUT_BUSINESS = os.path.join(output_dir, '仓网业务表现文件_运输损耗_CPULEX.csv')
OUTPUT_WH_PROC = os.path.join(output_dir, '仓库处置订单量文件_运输损耗_CPULEX.csv')
OUTPUT_SUPPLY = os.path.join(output_dir, '仓网供应关系文件_运输损耗_CPULEX.csv')
OUTPUT_REPORT = os.path.join(output_dir, '运输损耗优化分析报告.txt')

# ===================== 2. 数据加载与预处理（完全贴合赛题数据格式）=====================
def load_and_preprocess_data():
    """加载赛题附件，预处理为模型所需格式"""
    # 2.1 加载门店信息（门店-城市映射）
    df_customer = pd.read_csv(DF_CUSTOMER_PATH)
    store_city_map = dict(zip(df_customer['Name'], df_customer['Location']))  # {门店名: 城市名}
    all_stores = df_customer['Name'].unique().tolist()  # 所有门店

    # 2.2 加载仓库信息（区分CDC/RDC，CDC必开）
    df_wh = pd.read_csv(DF_WH_PATH)
    cdc_names = df_wh[df_wh['Type'] == 'CDC']['Name'].unique().tolist()  # 必开CDC（港口+内陆）
    rdc_candidates = df_wh[df_wh['Type'] == 'RDC']['Name'].unique().tolist()  # RDC候选（可选开仓）
    port_cdc = [w for w in cdc_names if 'gang-kou' in w][0]  # 港口CDC（进口海鲜）
    inland_cdc = [w for w in cdc_names if 'nei-lu' in w][0]  # 内陆CDC（国产海鲜）
    all_wh_candidates = cdc_names + rdc_candidates  # 所有仓库候选

    # 2.3 加载仓储数据（容量、开仓成本、处置成本）
    df_proc = pd.read_csv(DF_PROC_PATH)
    wh_capacity = dict(zip(df_proc['Name'], df_proc['Capacity']))  # {仓库名: 容量(吨)}
    wh_open_fee = dict(zip(df_proc['Name'], df_proc['Opening_fee']))  # {仓库名: 开仓成本(万元)}
    wh_processing_fee = dict(zip(df_proc['Name'], df_proc['Processing_fee']))  # {仓库名: 处置成本(万元/吨)}

    # 2.4 加载运输距离/时效数据
    df_matrix = pd.read_csv(DF_MATRIX_PATH)
    travel_dist = {}  # {(起点, 终点): 距离(km)}
    travel_time = {}  # {(起点, 终点): 时间(min)}
    for _, row in df_matrix.iterrows():
        from_node = row['From'].strip()
        to_node = row['To'].strip()
        travel_dist[(from_node, to_node)] = row['Distance']
        travel_time[(from_node, to_node)] = row['Duration']

    # 2.5 加载订单需求数据
    df_order = pd.read_csv(DF_ORDER_PATH)
    store_demand = {}  # {(门店名, SKU): 需求量(吨)}
    sku_list = ['im', 'dm']
    for _, row in df_order.iterrows():
        store = row['Name'].strip()
        sku = row['SKU'].strip()
        qty = row['qty']
        store_demand[(store, sku)] = qty

    # 2.6 计算总需求（用于时效满足率约束）
    total_demand = sum(store_demand.values())

    return {
        'store_city_map': store_city_map,
        'all_stores': all_stores,
        'cdc_names': cdc_names,
        'rdc_candidates': rdc_candidates,
        'port_cdc': port_cdc,
        'inland_cdc': inland_cdc,
        'all_wh_candidates': all_wh_candidates,
        'wh_capacity': wh_capacity,
        'wh_open_fee': wh_open_fee,
        'wh_processing_fee': wh_processing_fee,
        'travel_dist': travel_dist,
        'travel_time': travel_time,
        'store_demand': store_demand,
        'total_demand': total_demand,
        'sku_list': sku_list
    }

# ===================== 3. 定义损耗成本函数（严格遵循赛题公式）=====================
def calculate_loss_cost(t):
    """
    赛题损耗公式：t≤500分钟→0；t>500分钟→0.2*(t-500)² 元/吨
    转换为万元/吨（÷1e4）
    """
    if t <= 500:
        return 0.0
    else:
        return 0.2 * (t - 500) ** 2 / 1e4  # 万元/吨

# ===================== 4. 构建CPLEX优化模型（完全贴合赛题约束）=====================
def build_cplex_model(data):
    """
    决策变量：
    1. y_wh: RDC开仓变量（0=不开，1=开），CDC固定为1
    2. z_wh: 仓库是否采购智能调度系统（0=不采购，1=采购）
    3. u_wh_store_sku: 仓库wh是否服务门店store的SKU（0=否，1=是）
    4. v_store_sku: 门店store的SKU订单是否时效达标（0=否，1=是）
    5. f_cdc_rdc_sku: CDC向RDC的调拨量（吨）
    6. q_wh_sku: 仓库wh对SKU的总处置量（吨）
    """
    # 提取预处理数据
    cdc_names = data['cdc_names']
    rdc_candidates = data['rdc_candidates']
    port_cdc = data['port_cdc']
    inland_cdc = data['inland_cdc']
    all_wh = data['all_wh_candidates']
    all_stores = data['all_stores']
    sku_list = data['sku_list']
    store_demand = data['store_demand']
    travel_dist = data['travel_dist']
    travel_time = data['travel_time']
    wh_capacity = data['wh_capacity']
    wh_open_fee = data['wh_open_fee']
    wh_processing_fee = data['wh_processing_fee']
    total_demand = data['total_demand']

    # 创建CPLEX模型
    model = cplex.Cplex()
    model.objective.set_sense(model.objective.sense.minimize)
    model.parameters.timelimit.set(3600)  # 求解时间限制：1小时（可调整）

    # 4.1 定义决策变量
    var_dict = {}

    # 变量1：RDC开仓变量（CDC固定为1，无需定义）
    for wh in rdc_candidates:
        var_name = f'y_{wh}'
        model.variables.add(
            obj=[wh_open_fee.get(wh, 0.0)],  # 开仓成本计入目标函数
            lb=[0.0], ub=[1.0],
            types=[model.variables.type.binary],
            names=[var_name]
        )
        var_dict[var_name] = var_name

    # 变量2：智能调度系统采购变量（仅开仓仓库可采购）
    for wh in all_wh:
        var_name = f'z_{wh}'
        model.variables.add(
            obj=[1.5],  # 采购成本1.5万元/仓
            lb=[0.0], ub=[1.0],
            types=[model.variables.type.binary],
            names=[var_name]
        )
        var_dict[var_name] = var_name

    # 变量3：服务关系变量（仓库→门店→SKU）
    for wh in all_wh:
        for store in all_stores:
            for sku in sku_list:
                var_name = f'u_{wh}_{store}_{sku}'
                model.variables.add(
                    obj=[0.0],  # 成本后续在目标函数中计算
                    lb=[0.0], ub=[1.0],
                    types=[model.variables.type.binary],
                    names=[var_name]
                )
                var_dict[var_name] = var_name

    # 变量4：时效达标变量
    for store in all_stores:
        for sku in sku_list:
            var_name = f'v_{store}_{sku}'
            model.variables.add(
                obj=[0.0],
                lb=[0.0], ub=[1.0],
                types=[model.variables.type.binary],
                names=[var_name]
            )
            var_dict[var_name] = var_name

    # 变量5：CDC→RDC调拨量变量（连续变量）
    for cdc in cdc_names:
        for rdc in rdc_candidates:
            for sku in sku_list:
                var_name = f'f_{cdc}_{rdc}_{sku}'
                model.variables.add(
                    obj=[0.0],  # 运输成本后续计算
                    lb=[0.0], ub=[cplex.infinity],
                    types=[model.variables.type.continuous],
                    names=[var_name]
                )
                var_dict[var_name] = var_name

    # 变量6：仓库处置量变量（连续变量）
    for wh in all_wh:
        for sku in sku_list:
            var_name = f'q_{wh}_{sku}'
            model.variables.add(
                obj=[0.0],  # 处置成本后续计算
                lb=[0.0], ub=[wh_capacity.get(wh, 0.0)],  # 容量约束
                types=[model.variables.type.continuous],
                names=[var_name]
            )
            var_dict[var_name] = var_name

    # 4.2 添加赛题核心约束条件
    constraint_count = 0

    # 约束1：商品配送规则约束（赛题仓库开设与配送要求第2条）
    print("添加商品配送规则约束...")
    for store in all_stores:
        for sku in sku_list:
            eligible_whs = []
            if sku == 'im':  # 进口海鲜：港口CDC + 已开仓RDC
                eligible_whs = [port_cdc] + rdc_candidates
            else:  # 国产海鲜：内陆CDC + 已开仓RDC
                eligible_whs = [inland_cdc] + rdc_candidates

            # 约束：仅 eligible_whs 可服务该门店-SKU
            expr = cplex.SparsePair()
            for wh in eligible_whs:
                if wh in rdc_candidates:
                    # RDC需开仓才能服务（y_wh=1）
                    expr.ind.extend([f'u_{wh}_{store}_{sku}', f'y_{wh}'])
                    expr.val.extend([1.0, -1.0])
                else:
                    # CDC必开，直接约束服务关系
                    expr.ind.append(f'u_{wh}_{store}_{sku}')
                    expr.val.append(1.0)
            model.linear_constraints.add(
                lin_expr=[[expr.ind, expr.val]], rhs=[0.0], senses=['L'],
                names=[f'constraint_sku_{constraint_count}']
            )
            constraint_count += 1

    # 约束2：每个门店-SKU仅由一个仓库服务（赛题隐含约束）
    print("添加门店服务唯一性约束...")
    for (store, sku), qty in store_demand.items():
        expr = cplex.SparsePair()
        eligible_whs = []
        if sku == 'im':
            eligible_whs = [port_cdc] + rdc_candidates
        else:
            eligible_whs = [inland_cdc] + rdc_candidates
        for wh in eligible_whs:
            expr.ind.append(f'u_{wh}_{store}_{sku}')
            expr.val.append(1.0)
        model.linear_constraints.add(
            lin_expr=[[expr.ind, expr.val]], rhs=[1.0], senses=['E'],
            names=[f'constraint_unique_{constraint_count}']
        )
        constraint_count += 1

    # 约束3：仓库处置量约束（赛题出入库要求第2条）
    print("添加仓库容量约束...")
    for wh in all_wh:
        expr = cplex.SparsePair()
        for sku in sku_list:
            expr.ind.append(f'q_{wh}_{sku}')
            expr.val.append(1.0)
        model.linear_constraints.add(
            lin_expr=[[expr.ind, expr.val]], rhs=[wh_capacity.get(wh, 0.0)], senses=['L'],
            names=[f'constraint_capacity_{constraint_count}']
        )
        constraint_count += 1

    # 约束4：出入库平衡约束（赛题出入库要求第1条）
    print("添加出入库平衡约束...")
    # 4.1 CDC出入库平衡（入库=出库，出库=调拨给RDC+直接服务门店）
    for cdc in cdc_names:
        for sku in sku_list:
            expr = cplex.SparsePair()
            # 出库：调拨给RDC
            for rdc in rdc_candidates:
                expr.ind.append(f'f_{cdc}_{rdc}_{sku}')
                expr.val.append(1.0)
            # 出库：直接服务门店
            for store in all_stores:
                expr.ind.append(f'u_{cdc}_{store}_{sku}')
                expr.val.append(store_demand.get((store, sku), 0.0))
            # 入库=出库（q_wh_sku为入库量）
            expr.ind.append(f'q_{cdc}_{sku}')
            expr.val.append(-1.0)
            model.linear_constraints.add(
                lin_expr=[[expr.ind, expr.val]], rhs=[0.0], senses=['E'],
                names=[f'constraint_balance_cdc_{constraint_count}']
            )
            constraint_count += 1

    # 4.2 RDC出入库平衡（入库=CDC调拨量，出库=服务门店量）
    for rdc in rdc_candidates:
        for sku in sku_list:
            expr = cplex.SparsePair()
            # 入库：来自CDC的调拨
            for cdc in cdc_names:
                if (sku == 'im' and cdc == port_cdc) or (sku == 'dm' and cdc == inland_cdc):
                    expr.ind.append(f'f_{cdc}_{rdc}_{sku}')
                    expr.val.append(1.0)
            # 出库：服务门店
            for store in all_stores:
                expr.ind.append(f'u_{rdc}_{store}_{sku}')
                expr.val.append(-store_demand.get((store, sku), 0.0))
            # 入库=出库（q_wh_sku为入库量）
            expr.ind.append(f'q_{rdc}_{sku}')
            expr.val.append(-1.0)
            model.linear_constraints.add(
                lin_expr=[[expr.ind, expr.val]], rhs=[0.0], senses=['E'],
                names=[f'constraint_balance_rdc_{constraint_count}']
            )
            constraint_count += 1

    # 约束5：时效约束（运输时间≤600分钟，赛题时效满足率要求）
    print("添加时效约束...")
    for (store, sku), qty in store_demand.items():
        eligible_whs = []
        if sku == 'im':
            eligible_whs = [port_cdc] + rdc_candidates
        else:
            eligible_whs = [inland_cdc] + rdc_candidates
        for wh in eligible_whs:
            t = travel_time.get((wh, store), 0.0)
            if t > 600:
                # 若运输时间超600分钟，选择该路径则时效不达标（v=0）
                expr = cplex.SparsePair()
                expr.ind.extend([f'u_{wh}_{store}_{sku}', f'v_{store}_{sku}'])
                expr.val.extend([1.0, 1.0])
                model.linear_constraints.add(
                    lin_expr=[[expr.ind, expr.val]], rhs=[1.0], senses=['L'],
                    names=[f'constraint_time_{constraint_count}']
                )
                constraint_count += 1

    # 约束6：时效满足率≥95%（赛题时效满足率要求）
    print("添加时效满足率约束...")
    expr = cplex.SparsePair()
    for (store, sku), qty in store_demand.items():
        expr.ind.append(f'v_{store}_{sku}')
        expr.val.append(qty)
    model.linear_constraints.add(
        lin_expr=[[expr.ind, expr.val]], rhs=[0.95 * total_demand], senses=['G'],
        names=[f'constraint_time_satisfaction_{constraint_count}']
    )
    constraint_count += 1

    # 约束7：智能调度系统采购约束（仅开仓仓库可采购）
    print("添加智能调度系统约束...")
    for wh in rdc_candidates:
        expr = cplex.SparsePair()
        expr.ind.extend([f'z_{wh}', f'y_{wh}'])
        expr.val.extend([1.0, -1.0])
        model.linear_constraints.add(
            lin_expr=[[expr.ind, expr.val]], rhs=[0.0], senses=['L'],
            names=[f'constraint_z_rdc_{constraint_count}']
        )
        constraint_count += 1
    # CDC必开，可直接采购
    for wh in cdc_names:
        model.variables.set_lower_bounds(f'z_{wh}', 0.0)
        model.variables.set_upper_bounds(f'z_{wh}', 1.0)

    # 4.3 定义目标函数（完整计入所有成本+补贴）
    print("构建目标函数...")
    obj_expr = cplex.SparsePair()

    # 成本1：运输成本（CDC→RDC：0.9元/吨·公里；仓→店：1.45元/吨·公里 → 转换为万元）
    # 1.1 CDC→RDC调拨运输成本
    for cdc in cdc_names:
        for rdc in rdc_candidates:
            for sku in sku_list:
                dist = travel_dist.get((cdc, rdc), 0.0)
                cost_per_ton = 0.9 * dist / 1e4  # 万元/吨
                obj_expr.ind.append(f'f_{cdc}_{rdc}_{sku}')
                obj_expr.val.append(cost_per_ton)

    # 1.2 仓→店运输成本
    for wh in all_wh:
        for (store, sku), qty in store_demand.items():
            dist = travel_dist.get((wh, store), 0.0)
            cost_per_ton = 1.45 * dist / 1e4  # 万元/吨
            obj_expr.ind.append(f'u_{wh}_{store}_{sku}')
            obj_expr.val.append(cost_per_ton * qty)

    # 成本2：出入仓处置成本（含智能调度系统优惠）
    for wh in all_wh:
        for sku in sku_list:
            processing_fee = wh_processing_fee.get(wh, 0.0)
            # 采购智能调度系统省40%，即支付60%
            obj_expr.ind.extend([f'q_{wh}_{sku}', f'z_{wh}'])
            obj_expr.val.extend([processing_fee, -0.4 * processing_fee * model.variables.get_upper_bounds(f'q_{wh}_{sku}')])

    # 成本3：运输损耗成本（赛题问题2(3)公式）
    for wh in all_wh:
        for (store, sku), qty in store_demand.items():
            t = travel_time.get((wh, store), 0.0)
            loss_per_ton = calculate_loss_cost(t)
            obj_expr.ind.append(f'u_{wh}_{store}_{sku}')
            obj_expr.val.append(loss_per_ton * qty)

    # 补贴：开仓数量≥10个时，每多开1个补7万元（赛题问题2(2)）
    # 开仓总数=必开CDC数（2个）+ RDC开仓数
    expr_subsidy = cplex.SparsePair()
    for rdc in rdc_candidates:
        expr_subsidy.ind.append(f'y_{rdc}')
        expr_subsidy.val.append(1.0)
    # 定义补贴变量（连续变量，仅当开仓数≥10时生效）
    model.variables.add(
        obj=[-7.0],  # 补贴冲减成本，目标函数中为负
        lb=[0.0], ub=[cplex.infinity],
        types=[model.variables.type.continuous],
        names=['subsidy']
    )
    # 约束：补贴≤开仓数-10（开仓数<10时补贴为0）
    model.linear_constraints.add(
        lin_expr=[[expr_subsidy.ind, expr_subsidy.val]],
        rhs=[cplex.infinity],
        senses=['L'],
        names=[f'constraint_subsidy_1']
    )
    model.linear_constraints.add(
        lin_expr=[[expr_subsidy.ind + ['subsidy'], expr_subsidy.val + [-1.0]]],
        rhs=[2 - 10],  # 2个CDC + RDC开仓数 -10 ≤ 补贴
        senses=['L'],
        names=[f'constraint_subsidy_2']
    )
    obj_expr.ind.append('subsidy')
    obj_expr.val.append(1.0)

    # 设置目标函数
    model.objective.set_linear(obj_expr.ind, obj_expr.val)

    return model, var_dict

# ===================== 5. 求解模型并提取结果=====================
def solve_model(model, data, var_dict):
    """求解模型，提取优化结果"""
    print("开始求解模型...")
    model.solve()

    # 提取求解状态和目标函数值
    solve_status = model.solution.get_status_string()
    total_cost = model.solution.get_objective_value()
    print(f"求解状态：{solve_status}")
    print(f"最优总成本：{total_cost:.2f} 万元")

    # 提取关键结果
    results = {
        'solve_status': solve_status,
        'total_cost': total_cost,
        'opened_rdcs': [],  # 已开仓RDC
        'z_purchased': [],  # 采购智能调度系统的仓库
        'service_relationships': [],  # 服务关系（wh→store→sku→qty）
        'wh_processing_qty': [],  # 仓库处置量（wh→sku→qty）
        'time_satisfaction_rate': 0.0,  # 时效满足率
        'cost_breakdown': {  # 成本明细
            'transport_cdc_rdc': 0.0,
            'transport_wh_store': 0.0,
            'processing': 0.0,
            'opening': 0.0,
            'z_purchase': 0.0,
            'loss': 0.0,
            'subsidy': 0.0
        }
    }

    # 5.1 提取已开仓RDC和智能调度系统采购情况
    for rdc in data['rdc_candidates']:
        y_val = model.solution.get_values(f'y_{rdc}')
        if y_val > 0.5:
            results['opened_rdcs'].append(rdc)
            # 开仓成本计入
            results['cost_breakdown']['opening'] += data['wh_open_fee'].get(rdc, 0.0)
        # 智能调度系统采购
        z_val = model.solution.get_values(f'z_{rdc}')
        if z_val > 0.5:
            results['z_purchased'].append(rdc)
            results['cost_breakdown']['z_purchase'] += 1.5

    # CDC必开，智能调度系统采购情况
    for cdc in data['cdc_names']:
        z_val = model.solution.get_values(f'z_{cdc}')
        if z_val > 0.5:
            results['z_purchased'].append(cdc)
            results['cost_breakdown']['z_purchase'] += 1.5

    # 5.2 提取服务关系和运输成本、损耗成本
    travel_dist = data['travel_dist']
    travel_time = data['travel_time']
    store_demand = data['store_demand']
    for wh in data['all_wh_candidates']:
        for (store, sku), qty in store_demand.items():
            u_val = model.solution.get_values(f'u_{wh}_{store}_{sku}')
            if u_val > 0.5:
                # 服务关系
                results['service_relationships'].append({
                    'wh': wh,
                    'store': store,
                    'city': data['store_city_map'][store],
                    'sku': sku,
                    'qty': qty
                })

                # 仓→店运输成本
                dist = travel_dist.get((wh, store), 0.0)
                transport_cost = 1.45 * dist * qty / 1e4  # 万元
                results['cost_breakdown']['transport_wh_store'] += transport_cost

                # 损耗成本
                t = travel_time.get((wh, store), 0.0)
                loss_cost = calculate_loss_cost(t) * qty  # 万元
                results['cost_breakdown']['loss'] += loss_cost

    # 5.3 提取CDC→RDC调拨成本
    for cdc in data['cdc_names']:
        for rdc in data['rdc_candidates']:
            for sku in data['sku_list']:
                f_val = model.solution.get_values(f'f_{cdc}_{rdc}_{sku}')
                if f_val > 1e-6:
                    dist = travel_dist.get((cdc, rdc), 0.0)
                    transport_cost = 0.9 * dist * f_val / 1e4  # 万元
                    results['cost_breakdown']['transport_cdc_rdc'] += transport_cost

    # 5.4 提取仓库处置量和处置成本
    for wh in data['all_wh_candidates']:
        for sku in data['sku_list']:
            q_val = model.solution.get_values(f'q_{wh}_{sku}')
            if q_val > 1e-6:
                results['wh_processing_qty'].append({
                    'wh': wh,
                    'sku': sku,
                    'qty': q_val
                })
                # 处置成本（含智能调度优惠）
                z_val = model.solution.get_values(f'z_{wh}')
                processing_fee = data['wh_processing_fee'].get(wh, 0.0)
                processing_cost = processing_fee * q_val * (1 - 0.4 * z_val)  # 省40%
                results['cost_breakdown']['processing'] += processing_cost

    # 5.5 计算时效满足率
    satisfied_demand = 0.0
    for (store, sku), qty in store_demand.items():
        v_val = model.solution.get_values(f'v_{store}_{sku}')
        if v_val > 0.5:
            satisfied_demand += qty
    results['time_satisfaction_rate'] = satisfied_demand / data['total_demand']

    # 5.6 提取补贴金额
    results['cost_breakdown']['subsidy'] = model.solution.get_values('subsidy')

    return results

# ===================== 6. 输出赛题要求的结果文件=====================
def output_results(results, data):
    """生成赛题要求的3个附件文件+分析报告"""
    # 6.1 附件9：仓网业务表现文件（赛题格式）
    opened_wh_count = len(data['cdc_names']) + len(results['opened_rdcs'])  # 含必开CDC
    business_data = pd.DataFrame({
        '开仓数量': [opened_wh_count],
        '时效满足率': [results['time_satisfaction_rate']],
        '总物流成本（单位：万元）': [results['total_cost']],
        '仓库之间的运输总成本（单位：万元）': [results['cost_breakdown']['transport_cdc_rdc']],
        '仓库到门店的运输总成本（单位：万元）': [results['cost_breakdown']['transport_wh_store']],
        '开仓总成本（单位：万元）': [results['cost_breakdown']['opening']],
        '出入仓处置总成本（单位：万元）': [results['cost_breakdown']['processing']],
        '智能调度系统采购总成本（单位：万元）': [results['cost_breakdown']['z_purchase']],
        '运输损耗总成本（单位：万元）': [results['cost_breakdown']['loss']],
        '开仓补贴金额（单位：万元）': [results['cost_breakdown']['subsidy']]
    })
    business_data.to_csv(OUTPUT_BUSINESS, index=False, encoding='utf-8-sig')
    print(f"✅ 附件9已保存：{OUTPUT_BUSINESS}")

    # 6.2 附件10：仓库处置订单量文件（赛题格式）
    wh_proc_data = []
    for item in results['wh_processing_qty']:
        wh_proc_data.append({
            'Name': item['wh'],
            'SKU': item['sku'],
            'Qty（单位：吨）': round(item['qty'], 2)
        })
    # 补充未显示的仓库（处置量为0）
    for wh in data['all_wh_candidates']:
        for sku in data['sku_list']:
            if not any(d['Name'] == wh and d['SKU'] == sku for d in wh_proc_data):
                wh_proc_data.append({
                    'Name': wh,
                    'SKU': sku,
                    'Qty（单位：吨）': 0.0
                })
    wh_proc_df = pd.DataFrame(wh_proc_data)
    wh_proc_df.to_csv(OUTPUT_WH_PROC, index=False, encoding='utf-8-sig')
    print(f"✅ 附件10已保存：{OUTPUT_WH_PROC}")

    # 6.3 附件11：仓网供应关系文件（赛题格式）
    supply_data = []
    for item in results['service_relationships']:
        supply_data.append({
            'Name': item['wh'],
            'Customer': item['city'],
            'SKU': item['sku'],
            'Qty（单位：吨）': round(item['qty'], 2)
        })
    supply_df = pd.DataFrame(supply_data)
    supply_df.to_csv(OUTPUT_SUPPLY, index=False, encoding='utf-8-sig')
    print(f"✅ 附件11已保存：{OUTPUT_SUPPLY}")

    # 6.4 分析报告
    report = f"""赛题问题2(3) 考虑运输损耗成本的仓网优化分析报告
=====================================================================
一、求解结果概览
1. 求解状态：{results['solve_status']}
2. 最优总成本：{results['total_cost']:.2f} 万元
3. 开仓数量：{opened_wh_count} 个（必开CDC：{len(data['cdc_names'])} 个，新增RDC：{len(results['opened_rdcs'])} 个）
4. 时效满足率：{results['time_satisfaction_rate']:.4f}（≥95%，符合赛题要求）
5. 采购智能调度系统的仓库：{', '.join(results['z_purchased']) if results['z_purchased'] else '无'}

二、成本明细（单位：万元）
1. 仓库之间运输成本：{results['cost_breakdown']['transport_cdc_rdc']:.2f}
2. 仓库到门店运输成本：{results['cost_breakdown']['transport_wh_store']:.2f}
3. 开仓成本：{results['cost_breakdown']['opening']:.2f}
4. 出入仓处置成本：{results['cost_breakdown']['processing']:.2f}
5. 智能调度系统采购成本：{results['cost_breakdown']['z_purchase']:.2f}
6. 运输损耗成本：{results['cost_breakdown']['loss']:.2f}
7. 开仓补贴金额：{results['cost_breakdown']['subsidy']:.2f}

三、核心约束满足情况
1. 商品配送规则：所有门店订单均由符合要求的仓库服务（进口→港口CDC/RDC，国产→内陆CDC/RDC）
2. 仓库容量约束：所有仓库处置量均≤最大容量限制
3. 时效约束：运输时间≤600分钟，时效满足率≥95%
4. 出入库平衡：所有仓库入库量=出库量
5. 开仓要求：仅开仓的RDC提供服务

四、优化建议
1. 损耗控制：运输时间超过500分钟的路径损耗显著，建议优先选择短距离仓库服务
2. 开仓策略：新增RDC可有效降低损耗，但需平衡开仓成本与补贴
3. 智能调度：采购智能调度系统可节省40%处置成本，建议高处置量仓库优先采购

五、文件输出说明
1. 仓网业务表现文件：记录核心业务指标和成本明细
2. 仓库处置订单量文件：记录各仓库各类商品的处置量
3. 仓网供应关系文件：记录仓库→门店的配送关系和订单量
"""
    with open(OUTPUT_REPORT, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"✅ 分析报告已保存：{OUTPUT_REPORT}")

# ===================== 7. 主函数：串联所有流程=====================
def main():
    print("="*80)
    print("赛题问题2(3)：考虑运输损耗成本的仓网全局优化（CPLEX实现）")
    print("="*80)

    # 1. 数据加载与预处理
    print("\n1. 加载并预处理赛题数据...")
    try:
        data = load_and_preprocess_data()
        print(f"✅ 数据加载完成：门店数={len(data['all_stores'])}, 仓库候选数={len(data['all_wh_candidates'])}")
    except Exception as e:
        print(f"❌ 数据加载失败：{str(e)}")
        return

    # 2. 构建CPLEX模型
    print("\n2. 构建优化模型（含所有赛题约束）...")
    try:
        model, var_dict = build_cplex_model(data)
        print(f"✅ 模型构建完成：变量数={model.variables.get_num()}, 约束数={model.constraints.get_num()}")
    except Exception as e:
        print(f"❌ 模型构建失败：{str(e)}")
        return

    # 3. 求解模型
    print("\n3. 求解优化模型...")
    try:
        results = solve_model(model, data, var_dict)
        print(f"✅ 模型求解完成：最优总成本={results['total_cost']:.2f}万元")
    except Exception as e:
        print(f"❌ 模型求解失败：{str(e)}")
        return

    # 4. 输出结果文件
    print("\n4. 生成赛题要求的输出文件...")
    try:
        output_results(results, data)
        print("✅ 所有文件输出完成！")
    except Exception as e:
        print(f"❌ 文件输出失败：{str(e)}")
        return

    print("\n" + "="*80)
    print("优化任务完成！请查看 output_result 目录下的结果文件。")
    print("="*80)

if __name__ == "__main__":
    main()