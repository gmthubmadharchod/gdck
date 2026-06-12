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
            proc = await asyncio.create_subprocess_shell(
                f"docker pull {image_name}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            
            if status_msg:
                await status_msg.edit_text(f"📦 Creating container...")
            
            # Create container
            proc = await asyncio.create_subprocess_shell(
                f"docker create {image_name}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                text=True
            )
            stdout, _ = await proc.communicate()
            container_id = stdout.strip()
            
            if not container_id:
                return None, None, 0
            
            if status_msg:
                await status_msg.edit_text(f"📂 Exporting filesystem...")
            
            # Export
            export_tar = f"{temp_dir}/export.tar"
            await asyncio.create_subprocess_shell(
                f"docker export {container_id} -o {export_tar}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            if status_msg:
                await status_msg.edit_text(f"📁 Extracting files...")
            
            # Extract files
            files_dir = f"{temp_dir}/files"
            os.makedirs(files_dir, exist_ok=True)
            await asyncio.create_subprocess_shell(
                f"tar -xf {export_tar} -C {files_dir} 2>/dev/null",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Remove container
            await asyncio.create_subprocess_shell(f"docker rm {container_id}")
            
            # Count files
            total = 0
            for _, _, files in os.walk(files_dir):
                total += len(files)
            
            return files_dir, temp_dir, total
            
        except Exception as e:
            print(f"Extract error: {e}")
            return None, None, 0
    
    async def create_zip(self, source_dir, zip_path):
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(source_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, source_dir)
                    zipf.write(file_path, arcname)
    
    def get_all_files(self, directory):
        files = []
        for root, _, filenames in os.walk(directory):
            for f in filenames:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, directory)
                size = os.path.getsize(full)
                files.append({"name": rel, "size": size, "path": full})
        return files
    
    async def cleanup(self, temp_dir, zip_path=None):
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        if zip_path and os.path.exists(zip_path):
            os.remove(zip_path)import os
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
            proc = await asyncio.create_subprocess_shell(
                f"docker pull {image_name}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await proc.communicate()
            
            if status_msg:
                await status_msg.edit_text(f"📦 Creating container...")
            
            # Create container
            proc = await asyncio.create_subprocess_shell(
                f"docker create {image_name}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                text=True
            )
            stdout, _ = await proc.communicate()
            container_id = stdout.strip()
            
            if not container_id:
                return None, None, 0
            
            if status_msg:
                await status_msg.edit_text(f"📂 Exporting filesystem...")
            
            # Export
            export_tar = f"{temp_dir}/export.tar"
            await asyncio.create_subprocess_shell(
                f"docker export {container_id} -o {export_tar}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            if status_msg:
                await status_msg.edit_text(f"📁 Extracting files...")
            
            # Extract files
            files_dir = f"{temp_dir}/files"
            os.makedirs(files_dir, exist_ok=True)
            await asyncio.create_subprocess_shell(
                f"tar -xf {export_tar} -C {files_dir} 2>/dev/null",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Remove container
            await asyncio.create_subprocess_shell(f"docker rm {container_id}")
            
            # Count files
            total = 0
            for _, _, files in os.walk(files_dir):
                total += len(files)
            
            return files_dir, temp_dir, total
            
        except Exception as e:
            print(f"Extract error: {e}")
            return None, None, 0
    
    async def create_zip(self, source_dir, zip_path):
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(source_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, source_dir)
                    zipf.write(file_path, arcname)
    
    def get_all_files(self, directory):
        files = []
        for root, _, filenames in os.walk(directory):
            for f in filenames:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, directory)
                size = os.path.getsize(full)
                files.append({"name": rel, "size": size, "path": full})
        return files
    
    async def cleanup(self, temp_dir, zip_path=None):
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        if zip_path and os.path.exists(zip_path):
            os.remove(zip_path)
