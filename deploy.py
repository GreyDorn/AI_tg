"""Deploy script: uploads tg_AI project to VPS and restarts the service."""
import os
import paramiko

VPS_HOST = "151.243.180.58"
VPS_USER = "root"
VPS_PASS = "YDm_gGE7B+"
REMOTE_DIR = "/root/tg_AI"

LOCAL_DIR = r"d:\tg_AI"

UPLOAD_FILES = [
    ".env",
    ".env.example",
    "requirements.txt",
    "config.py",
    "main.py",
    "llm/__init__.py",
    "llm/base.py",
    "llm/gemini.py",
    "llm/groq_llm.py",
    "llm/openrouter.py",
    "llm/deepseek.py",
    "db/models.py",
    "db/repository.py",
    "bot/keyboards/main.py",
    "bot/handlers/start.py",
    "bot/handlers/chat.py",
    "bot/handlers/models.py",
    "bot/handlers/balance.py",
    "bot/handlers/payment.py",
    "bot/handlers/admin.py",
    "bot/middlewares/user.py",
    "bot/middlewares/ratelimit.py",
    "bot/middlewares/processing_lock.py",
]


def mkdir_p(sftp: paramiko.SFTPClient, remote_dir: str) -> None:
    parts = remote_dir.strip("/").split("/")
    path = ""
    for part in parts:
        path = f"/{path}/{part}".replace("//", "/")
        try:
            sftp.mkdir(path)
        except OSError:
            pass


def upload_files(sftp: paramiko.SFTPClient) -> None:
    for rel_path in UPLOAD_FILES:
        local_path = os.path.join(LOCAL_DIR, rel_path.replace("/", os.sep))
        remote_path = f"{REMOTE_DIR}/{rel_path}"
        remote_dir = remote_path.rsplit("/", 1)[0]
        mkdir_p(sftp, remote_dir)
        print(f"  uploading {rel_path} ...")
        sftp.put(local_path, remote_path)


def run_remote(ssh: paramiko.SSHClient, cmd: str) -> str:
    print(f"  $ {cmd}")
    _, stdout, stderr = ssh.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out:
        print(out.strip())
    if err:
        print("  STDERR:", err.strip())
    return out


def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"Connecting to {VPS_HOST} ...")
    ssh.connect(VPS_HOST, username=VPS_USER, password=VPS_PASS)

    sftp = ssh.open_sftp()
    print("Uploading files ...")
    upload_files(sftp)
    sftp.close()

    print("Installing dependencies ...")
    run_remote(ssh, f"cd {REMOTE_DIR} && python3 -m venv venv && venv/bin/pip install -q -r requirements.txt")

    print("Restarting service ...")
    run_remote(ssh, "systemctl restart tg_ai_bot")
    run_remote(ssh, "sleep 3 && systemctl status tg_ai_bot --no-pager | head -20")

    ssh.close()
    print("Done!")


if __name__ == "__main__":
    main()
