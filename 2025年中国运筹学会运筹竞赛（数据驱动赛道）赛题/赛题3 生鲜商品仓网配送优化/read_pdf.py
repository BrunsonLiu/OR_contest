#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
读取PDF内容
"""
import PyPDF2
import sys

def read_pdf_full(pdf_path):
    """读取PDF所有页面"""
    with open(pdf_path, 'rb') as f:
        reader = PyPDF2.PdfReader(f)
        total_pages = len(reader.pages)
        print(f"总页数: {total_pages}\n")
        
        all_text = []
        for i in range(total_pages):
            page = reader.pages[i]
            text = page.extract_text()
            all_text.append(text)
            print(f"=== 第{i+1}页 ===")
            print(text)
            print("\n" + "="*50 + "\n")
        
        return all_text

if __name__ == "__main__":
    pdf_path = "数据驱动的生鲜商品仓网配送优化.pdf"
    read_pdf_full(pdf_path)
