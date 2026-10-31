import json
import os
from datetime import datetime

import adsk.core


class FunctionSetsManager:
    def __init__(self):
        self.app = adsk.core.Application.get()
        self.user_settings = self.app.userSettings
        self.function_sets_folder = os.path.join(
            self.user_settings.userDataFolderPath,
            "function_sets"
        )
        os.makedirs(self.function_sets_folder, exist_ok=True)

    def get_available_folders(self):
        return {
            "default": os.path.join(self.function_sets_folder, "default"),
            "parametric": os.path.join(self.function_sets_folder, "parametric"),
            "engineering": os.path.join(self.function_sets_folder, "engineering"),
            "architecture": os.path.join(self.function_sets_folder, "architecture"),
            "art": os.path.join(self.function_sets_folder, "art"),
        }

    def save_function_set(self, name, curves, description="", category="default"):
        folders = self.get_available_folders()
        folder_path = folders.get(category, folders["default"])
        os.makedirs(folder_path, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = f"{name}_{timestamp}"
        filepath = os.path.join(folder_path, f"{safe_name}.json")

        data = {
            "curves": curves,
            "description": description or name,
            "category": category,
            "created_at": timestamp,
            "version": "1.0",
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return filepath

    def get_available_function_sets(self):
        result = []
        for category, folder_path in self.get_available_folders().items():
            if not os.path.isdir(folder_path):
                continue
            for file_name in sorted(os.listdir(folder_path)):
                if not file_name.endswith(".json"):
                    continue
                full_path = os.path.join(folder_path, file_name)
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    result.append({
                        "name": data.get("created_at", file_name[:-5]),
                        "display_name": data.get("description", file_name[:-5]),
                        "filepath": full_path,
                        "category": category,
                    })
                except Exception:
                    continue
        return result

    def load_function_set(self, filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_all_categories(self):
        result = ["default"]
        folders = self.get_available_folders()
        for key in ("parametric", "engineering", "architecture", "art"):
            path = folders[key]
            if os.path.isdir(path) and any(os.listdir(path)):
                result.append(key)
        return result
