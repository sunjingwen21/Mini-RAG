"""设置管理管理模块"""
import json
import logging
from pathlib import Path
from typing import Dict

from app.config import DATA_DIR, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL

SETTINGS_FILE = DATA_DIR / "settings.json"
logger = logging.getLogger("minirag.settings")

class SettingsManager:
    def __init__(self, settings_file: Path = SETTINGS_FILE):
        self.settings_file = settings_file
        self.settings_file.parent.mkdir(parents=True, exist_ok=True)
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
            self._write_settings(default_settings)

    def _default_settings(self) -> Dict[str, str]:
        return {
            "llm_base_url": LLM_BASE_URL,
            "llm_api_key": LLM_API_KEY,
            "llm_model": LLM_MODEL,
            "embedding_base_url": "",
            "embedding_api_key": "",
            "embedding_model": ""
        }

    def _write_settings(self, settings: Dict[str, str]) -> bool:
        try:
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
            logger.info("Settings saved to %s", self.settings_file)
            return True
        except Exception as e:
            logger.exception("保存设置失败: %s", e)
            return False

    def get_settings(self) -> Dict[str, str]:
        """获取当前配置"""
        try:
            with open(self.settings_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                defaults = self._default_settings()
                defaults.update(data)
                return defaults
        except Exception as e:
            logger.exception("读取设置失败: %s", e)
            # 返回默认环境变量
            return self._default_settings()

    def save_settings(self, settings: Dict[str, str]) -> bool:
        """保存配置到文件"""
        try:
            current_settings = self._default_settings()
            if self.settings_file.exists():
                current_settings = self.get_settings()
            current_settings.update(settings)
            return self._write_settings(current_settings)
        except Exception as e:
            logger.exception("保存设置失败: %s", e)
            return False

# 单例模式
settings_manager = SettingsManager()
