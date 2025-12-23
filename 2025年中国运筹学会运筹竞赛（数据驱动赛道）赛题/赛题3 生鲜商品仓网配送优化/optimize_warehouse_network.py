# 生鲜商品仓网配送优化
import pandas as pd
import numpy as np
from scipy.optimize import minimize
import pulp

# 读取数据
warehouses_df = pd.read_csv("input_data/df_wh.csv")
customers_df = pd.read_csv("input_data/df_customer.csv")
orders_df = pd.read_csv("input_data/df_order.csv")
matrix_df = pd.read_csv("input_data/df_matrix.csv")
proc_df = pd.read_csv("input_data/df_proc.csv")

# 提取仓库信息
warehouses = warehouses_df["Name"].tolist()
wh_types = warehouses_df["Type"].tolist()
wh_locations = warehouses_df["Location"].tolist()

# 提取客户信息
customers = customers_df["Name"].tolist()
customer_types = customers_df["Type"].tolist()
customer_locations = customers_df["Location"].tolist()

# 提取订单需求
# 按客户汇总总需求
demand_dict = orders_df.groupby("Name")["qty"].sum().to_dict()

# 如果某个客户没有需求，设为0
customer_demand = [demand_dict.get(c, 0) for c in customers]

# 提取仓库处理能力 (需要与warehouses_df匹配)
# 由于warehouses_df和proc_df的仓库可能不完全匹配，我们需要对齐数据
proc_warehouses = proc_df["Name"].tolist()

# 创建仓库能力映射
capacity_map = dict(zip(proc_df["Name"], proc_df["Capacity"]))
processing_fee_map = dict(zip(proc_df["Name"], proc_df["Processing_fee"]))
opening_fee_map = dict(zip(proc_df["Name"], proc_df["Opening_fee"]))

# 为每个仓库获取相应参数，如果不存在则使用默认值
wh_capacity = []
processing_fee = []
opening_fee = []

for wh in warehouses:
    if wh in capacity_map:
        wh_capacity.append(capacity_map[wh])
        processing_fee.append(processing_fee_map[wh])
        opening_fee.append(opening_fee_map[wh])
    else:
        # 对于没有处理能力数据的仓库（如工厂），设置默认值
        # 工厂通常容量大，处理费用低，开启费用可能为0
        if "Factory" in wh:
            wh_capacity.append(5000)  # 假设工厂容量为5000
            processing_fee.append(0.005)  # 假设工厂处理费用较低
            opening_fee.append(0)  # 假设工厂开启费用为0
        else:
            wh_capacity.append(1000)  # 默认容量
            processing_fee.append(0.01)  # 默认处理费用
            opening_fee.append(50)  # 默认开启费用

# 构建距离矩阵
# 创建仓库和客户索引映射
wh_index = {name: i for i, name in enumerate(warehouses)}
cust_index = {name: i for i, name in enumerate(customers)}

# 初始化距离和时间矩阵
n_warehouses = len(warehouses)
n_customers = len(customers)
distance_matrix = np.full((n_warehouses, n_customers), np.inf)
duration_matrix = np.full((n_warehouses, n_customers), np.inf)

# 填充矩阵
for _, row in matrix_df.iterrows():
    from_node = row["From"]
    to_node = row["To"]
    
    if from_node in wh_index and to_node in cust_index:
        wh_idx = wh_index[from_node]
        cust_idx = cust_index[to_node]
        distance_matrix[wh_idx, cust_idx] = row["Distance"]
        duration_matrix[wh_idx, cust_idx] = row["Duration"]

print(f"仓库数量: {n_warehouses}")
print(f"客户数量: {n_customers}")
print(f"总需求量: {sum(customer_demand)}")
print(f"总仓库容量: {sum(wh_capacity)}")

# 使用PuLP建立优化模型
prob = pulp.LpProblem("Warehouse_Allocation", pulp.LpMinimize)

# 决策变量
# x[i][j] 表示仓库i是否服务客户j (二进制变量)
x = []
for i in range(n_warehouses):
    x_row = []
    for j in range(n_customers):
        x_row.append(pulp.LpVariable(f"x_{i}_{j}", cat="Binary"))
    x.append(x_row)

# y[i] 表示仓库i是否开启 (二进制变量)
y = []
for i in range(n_warehouses):
    y.append(pulp.LpVariable(f"y_{i}", cat="Binary"))

# 目标函数: 最小化总成本
# 总成本 = 开启成本 + 处理成本 + 运输成本

# 运输成本系数矩阵 (假设单位距离成本为0.001)
transport_cost_matrix = distance_matrix * 0.001

# 开启成本
opening_cost = pulp.lpSum([opening_fee[i] * y[i] for i in range(n_warehouses)])

# 处理成本
processing_cost = pulp.lpSum([processing_fee[i] * customer_demand[j] * x[i][j] 
                              for i in range(n_warehouses) for j in range(n_customers)])

# 运输成本
transport_cost = pulp.lpSum([transport_cost_matrix[i, j] * x[i][j] * customer_demand[j] 
                             for i in range(n_warehouses) for j in range(n_customers)])

prob += opening_cost + processing_cost + transport_cost

# 约束条件

# 1. 每个客户只能由一个仓库服务
for j in range(n_customers):
    prob += pulp.lpSum([x[i][j] for i in range(n_warehouses)]) == 1

# 2. 仓库服务的总需求不能超过其容量
for i in range(n_warehouses):
    prob += pulp.lpSum([customer_demand[j] * x[i][j] for j in range(n_customers)]) <= wh_capacity[i] * y[i]

# 3. 只有开启的仓库才能服务客户
for i in range(n_warehouses):
    for j in range(n_customers):
        prob += x[i][j] <= y[i]

print("开始求解...")

# 求解问题
prob.solve(pulp.PULP_CBC_CMD(msg=1, timeLimit=300))  # 限制求解时间为5分钟

# 检查求解状态
print("求解状态:", pulp.LpStatus[prob.status])

# 输出结果
if prob.status == 1:  # 1表示找到了最优解
    print("找到最优解")
    print("总成本:", pulp.value(prob.objective))
    
    # 输出仓库开启情况
    print("\n开启的仓库:")
    opened_warehouses = []
    for i in range(n_warehouses):
        if pulp.value(y[i]) > 0.5:  # 二进制变量，大于0.5视为1
            opened_warehouses.append((warehouses[i], wh_capacity[i]))
            print(f"  {warehouses[i]} (容量: {wh_capacity[i]})")
    
    # 输出供应关系
    print("\n供应关系:")
    allocation = []
    for i in range(n_warehouses):
        if pulp.value(y[i]) > 0.5:
            for j in range(n_customers):
                if pulp.value(x[i][j]) > 0.5:
                    allocation.append((warehouses[i], customers[j], customer_demand[j]))
                    print(f"  {warehouses[i]} -> {customers[j]} (需求: {customer_demand[j]})")
    
    # 输出结果到文件
    allocation_df = pd.DataFrame(allocation, columns=["Warehouse", "Customer", "Demand"])
    allocation_df.to_csv("output_result/warehouse_customer_allocation.csv", index=False)
    
    # 输出开启的仓库信息
    opened_df = pd.DataFrame(opened_warehouses, columns=["Warehouse", "Capacity"])
    opened_df.to_csv("output_result/opened_warehouses.csv", index=False)
    
    print("\n结果已保存到 output_result 文件夹")
else:
    print("未能找到最优解或求解超时")
    print("当前目标值:", pulp.value(prob.objective) if prob.status in [0, -1] else "不可行")
