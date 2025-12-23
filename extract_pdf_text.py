import PyPDF2
import re

def extract_pdf_text(pdf_path, output_path):
    """从PDF文件中提取文本并保存到TXT文件"""
    try:
        with open(pdf_path, 'rb') as file:
            # 创建PDF阅读器对象
            reader = PyPDF2.PdfReader(file)
            
            # 获取PDF页数
            num_pages = len(reader.pages)
            print(f"PDF总页数: {num_pages}")
            
            # 提取所有页面的文本
            text = ""
            for page_num in range(num_pages):
                page = reader.pages[page_num]
                page_text = page.extract_text()
                text += f"\n=== 第{page_num + 1}页 ===\n"
                text += page_text
            
            # 保存文本到文件
            with open(output_path, 'w', encoding='utf-8') as output_file:
                output_file.write(text)
            
            print(f"文本提取完成，保存到: {output_path}")
            print(f"提取的文本长度: {len(text)} 字符")
            
            # 返回前10000个字符作为预览
            return text[:10000]
            
    except Exception as e:
        print(f"提取PDF文本时出错: {e}")
        return None

def extract_key_information(text):
    """从提取的文本中提取关键信息"""
    if not text:
        return
    
    print("\n=== 提取的关键信息 ===")
    
    # 提取赛题标题
    title_match = re.search(r'[\s\S]*?(赛题.*?\d+.*?\n)', text)
    if title_match:
        print(f"赛题标题: {title_match.group(1).strip()}")
    
    # 提取问题描述
    problem_match = re.search(r'(问题描述|赛题描述)[\s\S]*?(目标|要求|约束)', text)
    if problem_match:
        print(f"问题描述: {problem_match.group(0)[:500]}...")
    
    # 提取目标函数
    objective_match = re.search(r'(目标函数|优化目标)[\s\S]*?(约束条件|约束|变量定义)', text)
    if objective_match:
        print(f"优化目标: {objective_match.group(0)[:500]}...")
    
    # 提取约束条件
    constraint_match = re.search(r'(约束条件|约束)[\s\S]*?(变量定义|数据说明|输入数据)', text)
    if constraint_match:
        print(f"约束条件: {constraint_match.group(0)[:500]}...")

# 主程序
if __name__ == "__main__":
    # PDF文件路径
    pdf_path = './2025年中国运筹学会运筹竞赛（数据驱动赛道）赛题/赛题3 生鲜商品仓网配送优化/数据驱动的生鲜商品仓网配送优化.pdf'
    
    # 输出文本文件路径
    output_path = './赛题文本内容.txt'
    
    # 提取PDF文本
    preview_text = extract_pdf_text(pdf_path, output_path)
    
    # 如果提取成功，提取关键信息
    if preview_text:
        extract_key_information(preview_text)
        print("\n完整文本已保存到赛题文本内容.txt")
