"""
抖音团购智能同步工具 - 主程序入口（模块化版本）
"""
import sys
import os
import tkinter as tk

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ui.main_window import App


def main():
    """主函数"""
    root = tk.Tk()
    app = App(master=root)
    root.mainloop()


if __name__ == "__main__":
    main()
