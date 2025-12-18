"""
抖音团购智能同步工具 - 主程序入口（模块化版本）
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# from src.ui.main_window import App
from src.ui.gradio_ui import create_ui

def main():
    """主函数 - 启动 Gradio 界面"""
    # 启动 Gradio
    ui = create_ui()
    # 开启队列以支持生成器/流式输出（虽然目前主要靠Timer）
    ui.queue().launch(
        server_name="0.0.0.0",
        inbrowser=True,
        show_error=True
    )

if __name__ == "__main__":
    main()
