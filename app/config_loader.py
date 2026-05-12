import os
import shutil
from pathlib import Path

class ConfigLoader:
    def __init__(self, base_dir="appdata"):
        self.base_dir = os.path.abspath(base_dir)
        self.profiles_dir = os.path.join(self.base_dir, "profiles")
        self.settings_path = os.path.join(self.base_dir, "ebrake.toml")
        
        # Ensure directories exist
        os.makedirs(self.profiles_dir, exist_ok=True)

    def _get_abs_path(self, rel_path):
        target = os.path.abspath(os.path.join(self.profiles_dir, rel_path))
        if not os.path.commonpath([self.profiles_dir, target]) == self.profiles_dir:
            raise PermissionError("Access denied")
        return target

    def get_profile_tree(self):
        def walk(path):
            tree = []
            for name in sorted(os.listdir(path)):
                full_path = os.path.join(path, name)
                if os.path.isdir(full_path):
                    tree.append({
                        'name': name,
                        'type': 'dir',
                        'children': walk(full_path)
                    })
                elif name.endswith(('.toml', '.ebrake')):
                    tree.append({
                        'name': name,
                        'type': 'file',
                        'path': os.path.relpath(full_path, self.profiles_dir)
                    })
            return tree
        return walk(self.profiles_dir)

    def read_profile(self, rel_path):
        path = self._get_abs_path(rel_path)
        if not os.path.exists(path):
            return None
        with open(path, 'r') as f:
            return f.read()

    def save_profile(self, rel_path, data):
        path = self._get_abs_path(rel_path)
        
        sections = {
            'output': {},
            'video': {},
            'audio': {}
        }

        for key, value in data.items():
            if key.startswith('output_'):
                sections['output'][key.replace('output_', '')] = value
            elif key.startswith('video_'):
                sections['video'][key.replace('video_', '')] = value
            elif key.startswith('audio_'):
                sections['audio'][key.replace('audio_', '')] = value

        lines = []
        for section, keys in sections.items():
            if not keys: continue
            lines.append(f'[{section}]')
            for k, v in keys.items():
                if isinstance(v, str):
                    lines.append(f'{k} = "{v}"')
                else:
                    lines.append(f'{k} = {v}')
            lines.append('')
        
        with open(path, 'w') as f:
            f.write('\n'.join(lines))
        return True

    def create_dir(self, parent, name):
        path = self._get_abs_path(os.path.join(parent, name))
        os.makedirs(path, exist_ok=True)
        return True

    def create_file(self, parent, name):
        if not name.endswith(('.toml', '.ebrake')):
            name += '.ebrake'
        path = self._get_abs_path(os.path.join(parent, name))
        with open(path, 'w') as f:
            f.write('')
        return True

    def delete_path(self, rel_path):
        path = self._get_abs_path(rel_path)
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
        return True

    def move_path(self, src_rel, dest_rel):
        src_path = self._get_abs_path(src_rel)
        filename = os.path.basename(src_path)
        dest_path = self._get_abs_path(os.path.join(dest_rel, filename))
        
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        os.rename(src_path, dest_path)
        return True

    def get_settings(self):
        if not os.path.exists(self.settings_path):
            return {}
        settings = {}
        with open(self.settings_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                parts = line.split('=', 1)
                key = parts[0].strip()
                val = parts[1].strip().strip('"')
                settings[key] = val
        return settings

    def save_settings(self, settings):
        lines = []
        for k, v in settings.items():
            lines.append(f'{k} = "{v}"')
        with open(self.settings_path, 'w') as f:
            f.write('\n'.join(lines))
        return True
