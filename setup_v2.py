"""自动配置腾讯云服务器：Python 3.11 + 依赖 + crontab"""
import paramiko

HOST = "124.223.6.242"
USER = "ubuntu"
PASS = "JZup=458c*K!|ws7"

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(HOST, username=USER, password=PASS, timeout=15)
print("✅ SSH 已连接")

def run(cmd, timeout=120):
    stdin, stdout, stderr = client.exec_command(f"bash -lc '{cmd}'", timeout=timeout)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out: print(out)
    if err: print(err)
    return out + err

# Step 1: Install Python 3.11
print("=== 安装 Python 3.11 ===")
run("sudo add-apt-repository -y ppa:deadsnakes/ppa")
run("sudo apt-get update -qq")
run("sudo apt-get install -y -qq python3.11 python3.11-pip python3.11-venv")
run("python3.11 --version")

# Step 2: Install akshare et al with Python 3.11
print("=== 安装 Python 依赖 ===")
run("cd ~/kdj-scanner && python3.11 -m pip install -r requirements.txt")

# Step 3: Test AKShare works
print("=== 测试 AKShare ===")
out = run("cd ~/kdj-scanner && python3.11 -c \"import akshare as ak; df=ak.stock_zh_a_spot_em(); print(f'获取到 {len(df)} 只股票')\"", timeout=60)

if "获取到" in out:
    print("✅ AKShare 正常工作！")
else:
    print("❌ AKShare 仍有问题，继续排查")

# Step 4: Set up crontab (use python3.11)
print("=== 设置定时任务 ===")
run("crontab -l 2>/dev/null | grep -v kdj > /tmp/cron_new")
run("echo '30 7 * * 1-5 cd ~/kdj-scanner && python3.11 scanner.py >> ~/kdj-scan.log 2>&1' >> /tmp/cron_new")
run("crontab /tmp/cron_new")
run("crontab -l")

# Step 5: Run scanner
print("=== 运行首次扫描 ===")
run("cd ~/kdj-scanner && python3.11 scanner.py", timeout=1800)

client.close()
print("✅ 配置完成！")
