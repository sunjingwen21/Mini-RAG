#!/usr/bin/env python3
"""
Mini-RAG 停止脚本
停止运行中的服务器
"""
import subprocess
import sys

def stop_server():
    """停止服务器"""
    print("=" * 50)
    print("🛑 停止 Mini-RAG 服务器")
    print("=" * 50)
    
    try:
        # 在 Windows 上终止 Python 进程
        result = subprocess.run(
            ["taskkill", "/F", "/IM", "python.exe"],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ 服务器已停止")
        else:
            print("ℹ️ 没有找到运行中的服务器进程")
            
    except Exception as e:
        print(f"❌ 停止服务器时出错: {e}")
        sys.exit(1)

if __name__ == "__main__":
    stop_server()