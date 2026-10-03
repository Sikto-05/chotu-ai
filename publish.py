"""
CHOTU AI — Packaging & GitHub Publisher
Initializes git repo, generates GitHub release, and creates shareable archive.
"""
import os
import sys
import json
import shutil
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).parent


def run(cmd: str, cwd: str = None, capture: bool = False):
    """Run a shell command."""
    result = subprocess.run(
        cmd, shell=True, cwd=cwd or str(BASE_DIR),
        capture_output=capture, text=True
    )
    if not capture:
        pass
    return result


def init_git_repo():
    """Initialize git repository if not already done."""
    git_dir = BASE_DIR / ".git"
    if not git_dir.exists():
        print("[git] Initializing repository...")
        run("git init")
        run('git config user.email "chotu-ai@localhost"')
        run('git config user.name "CHOTU AI"')
    else:
        print("[git] Repository already initialized.")


def create_gitignore():
    gitignore = BASE_DIR / ".gitignore"
    content = """# CHOTU AI — gitignore
# Environment & secrets
.env
*.env

# User data (personal)
data/config.json
data/chotu_memory.db
data/voice_samples/
data/*.log
memory/

# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
venv/
env/
.venv/
*.egg-info/
dist/
build/
.eggs/

# IDE
.vscode/
.idea/
*.swp

# OS
.DS_Store
Thumbs.db
desktop.ini

# Compiled
*.exe
*.spec
"""
    gitignore.write_text(content)
    print("[git] .gitignore created.")


def create_github_actions():
    """Create GitHub Actions CI workflow."""
    workflows_dir = BASE_DIR / ".github" / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)

    ci_content = """name: CHOTU AI CI

on:
  push:
    branches: [ main, master ]
  pull_request:
    branches: [ main, master ]

jobs:
  lint:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install flake8
      - name: Lint with flake8
        run: |
          flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics --exclude=venv,data
  
  test:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install core dependencies
        run: |
          python -m pip install --upgrade pip
          pip install psutil requests beautifulsoup4 python-dotenv numpy
      - name: Syntax check
        run: |
          python -m py_compile main.py
          python -m py_compile setup_wizard.py
          python -m py_compile core/chotu_brain.py
          python -m py_compile core/tool_executor.py
          python -m py_compile core/memory_bank.py
          python -m py_compile core/startup_manager.py
          python -m py_compile skills/file_navigator.py
          python -m py_compile skills/system_monitor.py
          python -m py_compile skills/web_intel.py
          python -m py_compile skills/app_controller.py
          echo All syntax checks passed.
"""
    (workflows_dir / "ci.yml").write_text(ci_content)
    print("[github] CI workflow created.")


def create_release_archive():
    """Create a distributable ZIP archive."""
    print("[package] Creating release archive...")
    
    # Files/dirs to include
    include = [
        "main.py",
        "setup_wizard.py",
        "requirements.txt",
        "README.md",
        "install.bat",
        ".env.example",
        "core/",
        "skills/",
        "assets/",
    ]
    
    archive_name = BASE_DIR.parent / "CHOTU-AI-v1.0.0"
    tmp_dir = BASE_DIR.parent / "CHOTU-AI-v1.0.0-tmp"
    
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir()
    
    for item in include:
        src = BASE_DIR / item
        dst = tmp_dir / item
        if src.is_dir():
            if src.exists():
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns(
                    "__pycache__", "*.pyc", "*.pyo"
                ))
        elif src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    
    # Create data directory placeholder
    (tmp_dir / "data" / ".gitkeep").parent.mkdir(exist_ok=True)
    (tmp_dir / "data" / ".gitkeep").touch()
    
    shutil.make_archive(str(archive_name), "zip", str(tmp_dir.parent), tmp_dir.name)
    shutil.rmtree(tmp_dir)
    
    archive_path = str(archive_name) + ".zip"
    size = os.path.getsize(archive_path) / 1024
    print(f"[package] Archive created: {archive_path} ({size:.1f} KB)")
    return archive_path


def push_to_github(github_username: str = None, repo_name: str = "chotu-ai"):
    """Commit all files and push to GitHub."""
    print("\n[github] Preparing to push to GitHub...")

    # Stage all files
    run("git add -A")
    
    result = run("git status --short", capture=True)
    if not result.stdout.strip():
        print("[github] Nothing to commit.")
    else:
        run('git commit -m "feat: CHOTU AI v1.0.0 — Elite Personal Assistant"')
        print("[github] Committed.")

    if github_username:
        remote_url = f"https://github.com/{github_username}/{repo_name}.git"
        
        # Check if remote exists
        check = run("git remote get-url origin", capture=True)
        if check.returncode != 0:
            run(f"git remote add origin {remote_url}")
        
        # Ensure main branch
        run("git branch -M main")
        
        print(f"[github] Pushing to: {remote_url}")
        result = run("git push -u origin main", capture=True)
        
        if result.returncode == 0:
            print(f"[github] ✅ Successfully pushed to GitHub!")
            print(f"[github] Repository URL: https://github.com/{github_username}/{repo_name}")
            print(f"[github] Download URL: https://github.com/{github_username}/{repo_name}/archive/refs/heads/main.zip")
            return True
        else:
            print(f"[github] Push failed: {result.stderr}")
            print("[github] Make sure you've created the repo on GitHub and have push access.")
            return False
    else:
        print("[github] No GitHub username provided. Skipping push.")
        print("[github] To push manually:")
        print("  1. Create repo on https://github.com/new")
        print("  2. Run: git remote add origin https://github.com/YOUR_USERNAME/chotu-ai.git")
        print("  3. Run: git push -u origin main")
        return False


def main():
    print("=" * 55)
    print("  ⚡  CHOTU AI — GitHub Publisher & Packager")
    print("=" * 55)
    print()

    init_git_repo()
    create_gitignore()
    create_github_actions()

    # Create archive
    archive = create_release_archive()

    # Get GitHub credentials
    print()
    github_user = input("Enter your GitHub username (or press Enter to skip push): ").strip()
    
    if github_user:
        repo = input("Repository name [chotu-ai]: ").strip() or "chotu-ai"
        push_to_github(github_user, repo)
    
    print()
    print("=" * 55)
    print("  Distribution Package Created!")
    print(f"  Archive: {archive}")
    print()
    print("  Share this file — anyone can download and run:")
    print("  1. Extract the ZIP")
    print("  2. Run install.bat")
    print("  3. Follow the setup wizard")
    print("=" * 55)


if __name__ == "__main__":
    main()
