"""Run commands on Tencent Cloud server via SSH password auth"""
import subprocess, sys, os

HOST = "124.223.6.242"
USER = "ubuntu"
PASS = "JZup=458c*K!|ws7"
CMD = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "whoami && uname -a"

# Use a temporary askpass script
askpass = os.path.join(os.environ.get("TEMP", "/tmp"), "askpass.sh")
with open(askpass, "w") as f:
    f.write("#!/bin/bash\necho '" + PASS + "'\n")
os.chmod(askpass, 0o700)

env = {
    **os.environ,
    "SSH_ASKPASS": askpass,
    "SSH_ASKPASS_REQUIRE": "force",
    "DISPLAY": ":0",
}

result = subprocess.run(
    ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10",
     f"{USER}@{HOST}", f"bash -lc '{CMD}'"],
    capture_output=True, text=True, timeout=120, env=env
)
print(result.stdout)
if result.stderr:
    print(result.stderr, file=sys.stderr)
os.unlink(askpass)
