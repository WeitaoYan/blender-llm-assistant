"""
Blender Addon Packaging Script
打包 Blender 插件为 .zip 文件，并可选安装和启动
"""
import os
import sys
import zipfile
import shutil
import re
import subprocess
import json
from pathlib import Path

# 脚本所在目录
SCRIPT_DIR = Path(__file__).parent.resolve()
# addon 目录
ADDON_DIR = SCRIPT_DIR / "addon"
# 输出目录
OUTPUT_DIR = SCRIPT_DIR / "dist"


def load_manifest_version():
    """从 blender_manifest.toml 提取版本信息"""
    manifest_path = ADDON_DIR / "blender_manifest.toml"
    with open(manifest_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 解析 id
    id_match = re.search(r'^id\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    # 解析 version
    version_match = re.search(r'^version\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    
    addon_id = id_match.group(1) if id_match else "unknown"
    version = version_match.group(1) if version_match else "0.0.0"
    
    return addon_id, version


def clean_pycache(directory: Path):
    """删除 __pycache__ 目录"""
    for item in directory.rglob("__pycache__"):
        if item.is_dir():
            shutil.rmtree(item)
            print(f"  Removed: {item.relative_to(SCRIPT_DIR)}")


def clean_pyc_files(directory: Path):
    """删除 .pyc 文件"""
    for item in directory.rglob("*.pyc"):
        item.unlink()
        print(f"  Removed: {item.relative_to(SCRIPT_DIR)}")


def clean_dist():
    """清理 dist 目录"""
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
        print(f"Cleaned: {OUTPUT_DIR}")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def package_addon(clean: bool = True):
    """打包插件"""
    if clean:
        print("\n[1/4] Cleaning build artifacts...")
        clean_pycache(ADDON_DIR)
        clean_pyc_files(ADDON_DIR)

    print("\n[2/4] Loading manifest...")
    addon_id, version = load_manifest_version()
    print(f"  ID: {addon_id}")
    print(f"  Version: {version}")

    print("\n[3/4] Cleaning output directory...")
    clean_dist()

    print("\n[4/4] Creating zip package...")
    zip_name = f"{addon_id}-{version}.zip"
    zip_path = OUTPUT_DIR / zip_name

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(ADDON_DIR):
            # 排除 __pycache__
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            
            for file in files:
                # 排除 .pyc 文件
                if file.endswith(".pyc"):
                    continue
                    
                file_path = Path(root) / file
                # 计算在 zip 中的路径（相对于 addon 目录）
                arcname = file_path.relative_to(ADDON_DIR)
                zf.write(file_path, arcname)
                print(f"  Added: {arcname}")

    print(f"\nPackage created: {zip_path}")
    print(f"Size: {zip_path.stat().st_size / 1024:.1f} KB")
    
    return zip_path


def find_blender_executable() -> Path | None:
    """查找 Blender 可执行文件"""
    # 常见安装路径
    common_paths = [
        Path("C:/Blender Foundation/Blender 4.5/blender.exe"),
        Path("C:/Blender Foundation/Blender 4.4/blender.exe"),
        Path("C:/Blender Foundation/Blender 4.3/blender.exe"),
        Path("C:/Program Files/Blender Foundation/Blender 4.5/blender.exe"),
        Path("C:/Program Files/Blender Foundation/Blender 4.4/blender.exe"),
    ]
    
    for path in common_paths:
        if path.exists():
            return path
    
    # 尝试从环境变量查找
    blender_path = shutil.which("blender")
    if blender_path:
        return Path(blender_path)
    
    return None


def get_blender_extensions_dir(blender_exe: Path) -> Path | None:
    """获取 Blender 扩展目录"""
    # 通过 Blender 命令行获取用户配置目录
    try:
        result = subprocess.run(
            [str(blender_exe), "--python-expr", "import bpy; print(bpy.utils.user_resource('EXTENSIONS'))"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            # 输出可能包含多行，取最后一行路径
            lines = result.stdout.strip().split('\n')
            for line in reversed(lines):
                line = line.strip()
                if line and (Path(line).exists() or '\\' in line or '/' in line):
                    return Path(line)
    except Exception:
        pass
    
    # 回退：使用默认路径
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        return Path(appdata) / "Blender Foundation" / "Blender" / "4.5" / "extensions" / "local"
    
    return None


def install_addon(blender_exe: Path, addon_id: str):
    """安装插件到 Blender 扩展目录"""
    extensions_dir = get_blender_extensions_dir(blender_exe)
    if not extensions_dir:
        raise RuntimeError("Cannot determine Blender extensions directory")
    
    print(f"\nExtensions directory: {extensions_dir}")
    
    # 创建目录
    extensions_dir.mkdir(parents=True, exist_ok=True)
    
    # 目标目录
    target_dir = extensions_dir / addon_id
    
    # 如果目标目录已存在，先删除
    if target_dir.exists():
        shutil.rmtree(target_dir)
        print(f"  Removed existing: {target_dir}")
    
    # 复制 addon 目录
    shutil.copytree(ADDON_DIR, target_dir)
    print(f"  Installed to: {target_dir}")
    
    return target_dir


def create_startup_script(addon_dir: Path, port: int = 15800) -> Path:
    """创建 Blender 启动脚本，自动启用插件并启动服务器"""
    startup_script = addon_dir.parent / "auto_start_server.py"
    
    script_content = f'''"""
Auto-start script for Blender LLM Assistant
自动启用插件并启动 HTTP 服务器
"""
import bpy
import sys
import time
import logging
import traceback

# 设置日志
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("LLM Assistant AutoStart")


def enable_addon():
    """启用插件"""
    addon_name = "{addon_dir.name}"
    
    logger.info(f"Attempting to enable addon: {{addon_name}}")
    
    # 检查是否已启用
    if addon_name in bpy.context.preferences.addons:
        logger.info(f"Addon '{{addon_name}}' is already enabled")
        return True
    
    # 尝试启用
    try:
        bpy.ops.preferences.addon_enable(module=addon_name)
        logger.info(f"Enabled addon: {{addon_name}}")
        return True
    except Exception as e:
        logger.error(f"Failed to enable addon: {{e}}")
        logger.error(traceback.format_exc())
        return False


def start_server():
    """启动 HTTP 服务器"""
    try:
        from blender_llm_assistant.server import start_server
        import threading
        import uuid
        
        port = {port}
        secret = uuid.uuid4().hex
        
        logger.info(f"Starting HTTP server on port {{port}}...")
        
        thread = threading.Thread(
            target=start_server,
            args=(port, secret),
            daemon=True,
        )
        thread.start()
        
        # 保存 token 到文件
        token_file = addon_dir.parent / "server_token.txt"
        with open(token_file, "w") as f:
            f.write(secret)
        
        logger.info(f"HTTP Server started on port {{port}}")
        logger.info(f"Token saved to: {{token_file}}")
        logger.info(f"Token: {{secret}}")
        logger.info(f"API Endpoint: http://127.0.0.1:{{port}}")
        
        print(f"\\nHTTP Server started on port {{port}}")
        print(f"Token saved to: {{token_file}}")
        print(f"Token: {{secret}}")
        print(f"\\nAPI Endpoint: http://127.0.0.1:{{port}}")
        
        return True
    except Exception as e:
        logger.error(f"Failed to start server: {{e}}")
        logger.error(traceback.format_exc())
        print(f"Failed to start server: {{e}}")
        return False


# 等待 Blender 完全加载
logger.info("Waiting for Blender to fully load...")
time.sleep(3.0)

# 执行
logger.info("Starting auto-enable and server...")
enable_addon()
start_server()

# 保持脚本运行
bpy.app.timers.register(lambda: None, first_interval=1.0)

logger.info("Auto-start script completed")
'''
    
    with open(startup_script, "w", encoding="utf-8") as f:
        f.write(script_content)
    
    print(f"Created startup script: {startup_script}")
    return startup_script


def find_crash_logs() -> list[Path]:
    """查找 Blender 崩溃日志"""
    crash_logs = []
    
    # 临时目录
    temp_dir = Path(os.environ.get("TEMP", os.environ.get("TMP", "/tmp")))
    
    # 查找 .crash.txt 文件
    for log_file in temp_dir.glob("*.crash.txt"):
        crash_logs.append(log_file)
    
    # Blender 安装目录的 blender.crash.txt
    blender_exe = find_blender_executable()
    if blender_exe:
        install_dir = blender_exe.parent
        blender_crash = install_dir / "blender.crash.txt"
        if blender_crash.exists():
            crash_logs.append(blender_crash)
    
    # Blender debug 输出文件
    debug_output = Path("blender_debug_out.txt")
    if debug_output.exists():
        crash_logs.append(debug_output)
    
    return sorted(crash_logs, key=lambda x: x.stat().st_mtime, reverse=True)


def print_crash_logs(max_logs: int = 3):
    """打印最近的崩溃日志"""
    logs = find_crash_logs()
    if not logs:
        print("\nNo crash logs found.")
        print("\nTip: Use --debug flag to enable debug logging when launching Blender.")
        print("     Crash logs are typically saved in the system temp directory.")
        return
    
    print(f"\nFound {len(logs)} crash log(s):")
    for log in logs[:max_logs]:
        print(f"\n{'='*60}")
        print(f"Log: {log}")
        try:
            mtime = log.stat().st_mtime
            print(f"Modified: {mtime}")
        except:
            pass
        print('='*60)
        try:
            with open(log, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read(8000)  # 限制读取大小
                print(content)
                if len(content) >= 8000:
                    print("\n... (truncated, showing first 8000 chars)")
        except Exception as e:
            print(f"Error reading log: {e}")


def run_blender_debug(blender_exe: Path, startup_script: Path | None = None):
    """使用 Blender 的内置调试脚本运行"""
    # 查找 Blender 安装目录中的调试脚本
    debug_scripts = {
        "debug_log": blender_exe.parent / "blender_debug_log.cmd",
        "debug_gpu": blender_exe.parent / "blender_debug_gpu.cmd",
        "factory_startup": blender_exe.parent / "blender_factory_startup.cmd",
    }
    
    print("\nAvailable debug scripts in Blender installation:")
    for name, path in debug_scripts.items():
        if path.exists():
            print(f"  {name}: {path}")
        else:
            print(f"  {name}: not found")
    
    return debug_scripts


def launch_blender(blender_exe: Path, startup_script: Path | None = None, 
                   debug: bool = False, debug_gpu: bool = False):
    """启动 Blender GUI"""
    cmd = [str(blender_exe)]
    
    # 调试选项
    if debug:
        cmd.extend(["--debug-all"])
        print("  Debug mode: enabled (--debug-all)")
    
    if debug_gpu:
        cmd.extend(["--debug-gpu", "--debug-gpu-workarounds"])
        print("  GPU debugging: enabled")
    
    # 工厂模式启动（可选，禁用所有插件和用户设置）
    # cmd.append("--factory-startup")
    
    if startup_script and startup_script.exists():
        # 使用 Python 执行启动脚本
        cmd.extend(["--python", str(startup_script)])
    
    print(f"\nLaunching Blender: {' '.join(cmd)}")
    
    # 启动 Blender（不等待）
    process = subprocess.Popen(cmd)
    return process


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Package and install Blender addon")
    parser.add_argument(
        "--no-clean", 
        action="store_true", 
        help="Skip cleaning pycache and pyc files"
    )
    parser.add_argument(
        "--install", 
        action="store_true", 
        help="Install addon to Blender extensions directory"
    )
    parser.add_argument(
        "--launch", 
        action="store_true", 
        help="Launch Blender after installation"
    )
    parser.add_argument(
        "--auto-server", 
        action="store_true", 
        help="Auto-start HTTP server when Blender launches"
    )
    parser.add_argument(
        "--port", 
        type=int, 
        default=15800,
        help="HTTP server port (default: 15800)"
    )
    parser.add_argument(
        "--blender", 
        type=str, 
        help="Path to Blender executable"
    )
    parser.add_argument(
        "--debug", 
        action="store_true", 
        help="Launch Blender with debug logging enabled"
    )
    parser.add_argument(
        "--debug-gpu", 
        action="store_true", 
        help="Launch Blender with GPU debugging enabled"
    )
    parser.add_argument(
        "--show-crash-logs", 
        action="store_true", 
        help="Show recent crash logs and exit"
    )
    args = parser.parse_args()
    
    # 显示崩溃日志
    if args.show_crash_logs:
        print_crash_logs()
        return
    
    clean = not args.no_clean
    
    try:
        # 打包
        zip_path = package_addon(clean=clean)
        
        # 获取 addon id
        addon_id, version = load_manifest_version()
        
        # 安装
        if args.install:
            blender_exe = Path(args.blender) if args.blender else find_blender_executable()
            if not blender_exe:
                raise RuntimeError("Blender executable not found. Use --blender to specify path.")
            
            print(f"\nUsing Blender: {blender_exe}")
            install_addon(blender_exe, addon_id)
        
        # 启动
        if args.launch:
            blender_exe = Path(args.blender) if args.blender else find_blender_executable()
            if not blender_exe:
                raise RuntimeError("Blender executable not found. Use --blender to specify path.")
            
            startup_script = None
            if args.auto_server:
                extensions_dir = get_blender_extensions_dir(blender_exe)
                if extensions_dir:
                    addon_dir = extensions_dir / addon_id
                    startup_script = create_startup_script(addon_dir, args.port)
            
            launch_blender(blender_exe, startup_script, debug=args.debug, debug_gpu=args.debug_gpu)
        
        print("\nDone!")
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
