import sys
import os

# 添加当前目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(current_dir))  # 添加Code目录

from auto_answer import AutoAnswer

if __name__ == "__main__":
    auto_answer = AutoAnswer()
    auto_answer.run()