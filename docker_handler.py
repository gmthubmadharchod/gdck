import os
import subprocess
import shutil
import zipfile
import asyncio

class DockerExtractor:
    async def extract_image(self, image_name, status_msg=None):
        safe_name = image_name.replace('/', '_').replace(':', '_')
        temp_dir = f"/tmp/docker_extract/{safe_name}"
        
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)
        
        try:
            if status_msg:
                await status_msg.edit_text(f"🔄 Pulling {image_name}...")
            
            # Pull image
            process = await asyncio.create_subprocess_shell(
                f"docker pull {image_name}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            
            if status_msg:
                await status_msg.edit_text(f"📦 Creating container...")
            
            # Create container
            result = await asyncio.create_subprocess_shell(
                f"docker create {image_name}",
                stdout=asyncio.subprocess.PIPE,
                text=True
            )
            stdout, _ = await result.communicate()
            container_id = stdout.strip()
            
            if status_msg:
                await status_msg.edit_text(f"📂 Exporting filesystem...")
            
            # Export
            export_tar = f"{temp_dir}/export.tar"
            await asyncio.create_subprocess_shell(
                f"docker export {container_id} -o {export_tar}",
                stdout=asyncio.subprocess.PIPE
            )
            
            if status_msg:
                await status_msg.edit_text(f"📁 Extracting files...")
            
            # Extract
            files_dir = f"{temp_dir}/files"
            os.makedirs(files_dir, exist_ok=True)
            await asyncio.create_subprocess_shell(
                f"tar -xf {export_tar} -C {files_dir} 2>/dev/null",
                stdout=asyncio.subprocess.PIPE
            )
            
            # Remove container
            await asyncio.create_subprocess_shell(f"docker rm {container_id}")
            
            # Count files
            total = 0
            for _, _, files in os.walk(files_dir):
                total += len(files)
            
            return files_dir, temp_dir, total
            
        except Exception as e:
            print(f"Error: {e}")
            return None
    
    def get_all_files(self, directory):
        all_files = []
        for root, _, files in os.walk(directory):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, directory)
                size = os.path.getsize(full_path)
                all_files.append({'name': rel_path, 'size': size, 'path': full_path})
        return all_files
    
    async def create_zip(self, source_dir, zip_path):
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(source_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, source_dir)
                    zipf.write(file_path, arcname)
    
    async def get_folder_tree(self, directory, total_files):
        tree_lines = ["📁 **Complete Folder Structure**\n"]
        
        def build_tree(path="", prefix=""):
            lines = []
            items = sorted(os.listdir(os.path.join(directory, path)) if path else os.listdir(directory))
            
            for i, item in enumerate(items):
                item_path = os.path.join(path, item) if path else item
                full_path = os.path.join(directory, item_path)
                is_last = (i == len(items) - 1)
                
                if os.path.isdir(full_path):
                    lines.append(f"{prefix}{'└── ' if is_last else '├── '}📁 {item}/")
                    lines.extend(build_tree(item_path, prefix + ('    ' if is_last else '│   ')))
                else:
                    size = os.path.getsize(full_path)
                    size_str = self._format_size(size)
                    lines.append(f"{prefix}{'└── ' if is_last else '├── '}📄 {item} ({size_str})")
            
            return lines
        
        tree_lines.extend(build_tree())
        tree_lines.append(f"\n📊 **Total:** {total_files} files")
        
        tree_text = "\n".join(tree_lines)
        if len(tree_text) > 4096:
            tree_text = tree_text[:4000] + "\n\n... (truncated)"
        
        return tree_text
    
    def _format_size(self, size):
        if size < 1024:
            return f"{size} B"
        elif size < 1024*1024:
            return f"{size/1024:.2f} KB"
        else:
            return f"{size/(1024*1024):.2f} MB"
    
    async def cleanup(self, temp_dir, zip_path=None):
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        if zip_path and os.path.exists(zip_path):
            os.remove(zip_path)
