import cplex
from cplex.exceptions import CplexError

# 创建一个简单的线性规划问题
def test_cplex():
    try:
        my_prob = cplex.Cplex()
        
        # 设置目标函数最大化
        my_prob.objective.set_sense(my_prob.objective.sense.maximize)
        
        # 定义变量
        my_obj = [1.0, 2.0, 3.0]
        my_ub = [40.0, cplex.infinity, cplex.infinity]
        my_colnames = ["x1", "x2", "x3"]
        my_prob.variables.add(obj=my_obj, ub=my_ub, names=my_colnames)
        
        # 添加约束
        my_rhs = [20.0, 30.0]
        my_rownames = ["c1", "c2"]
        my_sense = "LL"
        
        rows = [[["x1", "x2", "x3"], [-1.0, 1.0, 1.0]],
                [["x1", "x2", "x3"], [1.0, -3.0, 1.0]]]
        
        my_prob.linear_constraints.add(lin_expr=rows, senses=my_sense,
                                      rhs=my_rhs, names=my_rownames)
        
        # 求解问题
        my_prob.solve()
        
        # 输出结果
        print("Solution status = ", my_prob.solution.get_status(), ":", end=' ')
        print(my_prob.solution.status[my_prob.solution.get_status()])
        print("Solution value  = ", my_prob.solution.get_objective_value())
        
        x = my_prob.solution.get_values()
        for j in range(my_prob.variables.get_num()):
            print(f"Variable {my_prob.variables.get_names(j)}: Value = {x[j]}")
        
        print("CPLEX测试成功！")
        return True
        
    except CplexError as exc:
        print(f"CPLEX错误: {exc}")
        return False

if __name__ == "__main__":
    test_cplex()