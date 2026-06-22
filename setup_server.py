"""一次性配置脚本：通过 SSH 连接腾讯云服务器，安装环境并设置定时任务"""
import subprocess, pathlib, tempfile, os

HOST = "124.223.6.242"
USER = "ubuntu"
PASS = "JZup=458c*K!|ws7"
REPO = "https://github.com/MgcCtheMan/kdj-scanner.git"

# Write a temporary askpass helper
tmp_pass = pathlib.Path(tempfile.gettempdir()) / "ssh_pass.sh"
tmp_pass.write_text(f"#!/bin/bash\necho '{PASS}'\n")
tmp_pass.chmod(0o700)

env = {**os.environ, "SSH_ASKPASS": str(tmp_pass), "SSH_ASKPASS_REQUIRE": "force", "DISPLAY": "dummy"}

def ssh(cmd: str, timeout: int = 120):
    """Run a command on the remote server via SSH (password auth via askpass)"""
    args = [
        "ssh", "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        f"{USER}@{HOST}",
        f"bash -lc '{cmd}'",
    ]
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if result.returncode != 0:
        print(f"[exit {result.returncode}]")
    return result

# Step 1: Basic setup
ssh("echo '=== 连接成功 ===' && whoami && uname -a")

# Step 2: Update system + install Python & git
ssh("sudo apt-get update -qq && sudo apt-get install -y -qq python3-pip git 2>&1 | tail -3")

# Step 3: Clone repo
ssh(f"git clone {REPO} ~/kdj-scanner 2>&1 || echo 'Repo exists, pulling...' && cd ~/kdj-scanner && git pull")

# Step 4: Install Python dependencies
ssh("cd ~/kdj-scanner && pip3 install --break-system-packages -r requirements.txt 2>&1 | tail -5")

# Step 5: Set up cron job (daily at 15:30 CST = 07:30 UTC)
ssh(f"""crontab -l 2>/dev/null | grep -v kdj-scanner > /tmp/cron_new
echo '30 7 * * 1-5 cd ~/kdj-scanner && python3 scanner.py >> ~/kdj-scan.log 2>&1' >> /tmp/cron_new
crontab /tmp/cron_new
echo "=== Crontab ==="
crontab -l""")

# Step 6: Run first test
print("\n=== 首测运行（约15-30分钟）===")
ssh("cd ~/kdj-scanner && python3 scanner.py 2>&1 | tail -30", timeout=1800)

# Cleanup
tmp_pass.unlink()
print("\n✅ 配置完成！")
