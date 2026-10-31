import os
import sys
import json
import adsk.core
from datetime import datetime

class FunctionSetManager:
    def __init__(self):
        self.app = adsk.core.Application.get()
        self.user_settings = self.app.userSettings
        self.function_sets_folder = os.path.join(
            self.user_settings.userDataFolderPath, 
            'function_sets'
        )
        if not os.path.exists(self.function_sets_folder):
            os.makedirs(self.function_sets_folder)
    
    def save_function_set(self, name, curves, description='', category=''):
        folder_path = os.path.join(self.function_sets_folder, category if category else 'default')
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_name = f"{name}_{timestamp}"
        filepath = os.path.join(folder_path, f"{safe_name}.json")
        
        data = {
            'curves': curves,
            'description': description,
            'category': category,
            'created_at': timestamp,
            'version': '1.0'
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return filepath
    
    def load_function_sets(self):
        """Returns list of available function sets (filenames only for display)"""
        folders = [
            'default',
            os.path.join(self.function_sets_folder, 'engineering'),
            os.path.join(self.function_sets_folder, 'architecture'),
            os.path.join(self.function_sets_folder, 'art')
        ]
        
        result = []
        for folder in folders:
            if os.path.exists(folder):
                items = os.listdir(folder)
                json_files = [f[:-5] for f in items if f.endswith('.json')]
                for name in sorted(json_files):
                    full_path = os.path.join(folder, f'{name}.json')
                    try:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            result.append({
                                'name': data.get('created_at', name),
                                'display_name': data.get('description', name),
                                'filepath': full_path,
                                'category': os.path.basename(folder) if folder != self.function_sets_folder else 'default'
                            })
                    except:
                        pass
        
        return result
    
    def load_function_set(self, filepath):
        """Loads a function set from file"""
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def get_all_categories(self):
        """Returns list of categories available"""
        folders = [
            '',  # default
            'engineering',
            'architecture',
            'art'
        ]
        result = ['default']
        for folder in folders[1:]:
            path = os.path.join(self.function_sets_folder, folder)
            if os.path.exists(path) and os.path.isdir(path):
                if not any(os.listdir(path)):  # has items
                    result.append(folder)
        return result


# Global instance
function_set_manager = FunctionSetManager()

__all__ = ['FunctionSetManager', 'function_set_manager']