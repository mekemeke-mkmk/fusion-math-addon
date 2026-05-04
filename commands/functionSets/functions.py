"""
Function Sets Management Module
Manages saving, loading, and organizing mathematical function sets
for Autodesk Fusion Sketches add-on.
"""

import os
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional

try:
    import adsk.core
except ImportError:
    pass


class FunctionSetsManager:
    """
    Manages function sets for mathematical curve generation.
    
    Features:
    - Create new function set folders (default, engineering, architecture, art)
    - Save function sets as JSON files
    - Load and preview function sets
    - Category-based organization
    """
    
    def __init__(self):
        self.app = adsk.core.Application.get()
        self.user_settings = self.app.userSettings
        self.function_sets_folder = os.path.join(
            self.user_settings.userDataFolderPath, 
            'function_sets'
        )
        if not os.path.exists(self.function_sets_folder):
            os.makedirs(self.function_sets_folder)
    
    def get_available_folders(self) -> Dict[str, str]:
        """Returns available folder paths."""
        return {
            'default': self.function_sets_folder,
            'engineering': os.path.join(self.function_sets_folder, 'engineering'),
            'architecture': os.path.join(self.function_sets_folder, 'architecture'),
            'art': os.path.join(self.function_sets_folder, 'art')
        }
    
    def create_new_set(self) -> Optional[str]:
        """Create a new function set."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_name = f"New_Set_{timestamp}"
        
        default_path = os.path.join(self.function_sets_folder, 'default')
        if not os.path.exists(default_path):
            os.makedirs(default_path)
        
        filepath = os.path.join(default_path, f"{safe_name}.json")
        try:
            data = {
                'curves': [],
                'description': '',
                'category': 'default',
                'created_at': timestamp,
                'version': '1.0'
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            app = self.app
            ui = app.userInterface
            ui.messageBox(f"Created new function set: {safe_name}")
            
            return filepath
            
        except Exception as e:
            app = self.app
            ui = app.userInterface
            ui.messageBox(f"Error creating function set: {str(e)}")
        
        return None
    
    def save_function_set(self, name: str, curves: List[Dict], 
                         description: str = '', category: str = 'default') -> Optional[str]:
        """
        Save a function set to JSON file.
        
        Args:
            name: Set name (without path)
            curves: List of curve definitions {'name': '...', 'expr': '...', 'step': 0.2, 'enabled': False}
            description: Description text
            category: Folder category (default, engineering, architecture, art)
            
        Returns:
            Filepath of saved function set, or None on error
        """
        try:
            folders = self.get_available_folders()
            
            # Auto-detect category from name if not specified
            if category == 'default':
                for key in ['engineering', 'architecture', 'art']:
                    if key.lower() in name.lower():
                        category = key
            
            folder_path = folders.get(category, folders['default'])
            
            # Ensure folder exists
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)
            
            # Create unique filename with timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            safe_name = f"{name}_{timestamp}"
            
            filepath = os.path.join(folder_path, f"{safe_name}.json")
            
            data = {
                'curves': curves,
                'description': description if description else name,
                'category': category,
                'created_at': timestamp,
                'version': '1.0'
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            app = self.app
            ui = app.userInterface
            ui.messageBox(f"Saved function set to category: {category}")
            
            return filepath
            
        except Exception as e:
            app = self.app
            ui = app.userInterface
            ui.messageBox(f"Error saving function set: {str(e)}")
        
        return None
    
    def get_available_function_sets(self) -> List[Dict]:
        """Returns list of available function sets from all categories."""
        folders = self.get_available_folders()
        result = []
        
        for category, folder_path in folders.items():
            if not os.path.exists(folder_path):
                continue
                
            items = os.listdir(folder_path)
            json_files = [f[:-5] for f in items if f.endswith('.json')]
            
            for filename in sorted(json_files):
                filepath = os.path.join(folder_path, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    result.append({
                        'name': data.get('created_at', filename),
                        'display_name': data.get('description', filename),
                        'filepath': filepath,
                        'category': category if category != 'default' else 'default'
                    })
                except:
                    pass
        
        return result
    
    def load_function_set(self, filepath: str) -> Optional[Dict]:
        """Load a function set from JSON file."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            app = self.app
            ui = app.userInterface
            ui.messageBox(f"Error loading function set: {str(e)}")
            return None
    
    def get_all_categories(self) -> List[str]:
        """Returns list of categories with content."""
        folders = self.get_available_folders()
        result = ['default']
        
        for key in ['engineering', 'architecture', 'art']:
            path = os.path.join(self.function_sets_folder, key)
            if os.path.exists(path) and os.path.isdir(path):
                items = os.listdir(path)
                if len(items) > 0:
                    result.append(key)
        
        return result
"""