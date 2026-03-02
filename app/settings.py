"""设置管理管理模块"""
import json
import os
from pathlib import Path
from typing import Dict, Any

from app.config import DATA_DIR, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL

SETTINGS_FILE = DATA_DIR / "settings.json"

class SettingsManager:
    def __init__(self):
        self.settings_file = SETTINGS_FILE
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        if not self.settings_file.exists():
            default_settings = {
                "llm_base_url": LLM_BASE_URL,
                "llm_api_key": LLM_API_KEY,
                "llm_model": LLM_MODEL,
                "embedding_base_url": "",
                "embedding_api_key": "",
                "embedding_model": ""
            }
            self.save_settings(default_settings)

    def get_settings(self) -> Dict[str, str]:
        """获取当前配置"""
        try:
            with open(self.settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                defaults = {
                    "llm_base_url": LLM_BASE_URL,
                    "llm_api_key": LLM_API_KEY,
                    "llm_model": LLM_MODEL,
                    "embedding_base_url": "",
                    "embedding_api_key": "",
                    "embedding_model": ""
                }
                defaults.update(data)
                return defaults
        except Exception as e:
            print(f"读取设置失败: {e}")
            # 返回默认环境变量
            return {
                "llm_base_url": LLM_BASE_URL,
                "llm_api_key": LLM_API_KEY,
                "llm_model": LLM_MODEL,
                "embedding_base_url": "",
                "embedding_api_key": "",
                "embedding_model": ""
            }

    def save_settings(self, settings: Dict[str, str]) -> bool:
        """保存配置到文件"""
        try:
            current_settings = self.get_settings()
            current_settings.update(settings)
            
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(current_settings, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"保存设置失败: {e}")
            return False

# 单例模式
settings_manager = SettingsManager()
