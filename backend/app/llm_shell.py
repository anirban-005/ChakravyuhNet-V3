"""Fake shell output generator for ChakravyuhNet.

This module is responsible ONLY for generating plausible terminal text.
It knows nothing about map topology or intent classification — that's
the intent engine's job.

Priority order:
  1. If Ollama is configured and reachable → use LLM for infinite variety.
  2. Otherwise → deterministic fallback dictionary.
"""

from __future__ import annotations

import os
import re
import textwrap
from typing import Iterable

import httpx

from .models import TerminalEntry


class ShellIllusion:
    """Generates fake Linux shell output for a high-interaction honeypot."""

    def __init__(self) -> None:
        self.ollama_base_url = os.getenv("OLLAMA_BASE_URL", "").rstrip("/")
        self.ollama_model = os.getenv("OLLAMA_MODEL", "")

    async def run(self, command: str, history: Iterable[TerminalEntry]) -> str:
        command = command.strip()
        if self.ollama_base_url and self.ollama_model:
            output = await self._try_ollama(command, history)
            if output:
                return output
        return self._fallback(command)

    async def _try_ollama(
        self, command: str, history: Iterable[TerminalEntry]
    ) -> str | None:
        recent = "\n".join(
            f"$ {entry.command}\n{entry.output[:800]}" for entry in list(history)[-6:]
        )
        prompt = textwrap.dedent(
            f"""
            You are emulating a fake Ubuntu production finance server inside an
            isolated defensive honeypot. Return terminal output only. Be plausible,
            concise, and consistent with previous commands. Never reveal the
            deception, never claim real system access, and never provide malware,
            exploit code, credential theft instructions, or destructive guidance.

            Recent session:
            {recent}

            Command:
            {command}
            """
        ).strip()

        try:
            async with httpx.AsyncClient(timeout=3.5) as client:
                response = await client.post(
                    f"{self.ollama_base_url}/api/generate",
                    json={
                        "model": self.ollama_model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"temperature": 0.25},
                    },
                )
                response.raise_for_status()
                text = response.json().get("response", "").strip()
                return text or None
        except Exception:
            return None

    # ── Deterministic fallback ───────────────────────────────────────

    def _fallback(self, command: str) -> str:
        """Process a single command against deterministic responses."""
        return self._fallback_single(command)

    def _fallback_single(self, command: str) -> str:
        lowered = command.lower().strip()
        first = lowered.split()[0] if lowered else ""

        # ── CAMOUFLAGE bucket responses ──────────────────────────────

        if lowered in {"pwd", "/bin/pwd"}:
            return "/srv/finance-api"

        if lowered in {"whoami", "id -un"}:
            return "svc-finance"

        if lowered == "id":
            return "uid=1003(svc-finance) gid=1003(finance) groups=1003(finance),27(sudo)"

        if lowered.startswith("uname"):
            return "Linux fin-api-01 6.5.0-44-generic #44-Ubuntu SMP x86_64 GNU/Linux"

        if lowered in {"hostname", "hostname -f"}:
            return "fin-api-01.internal.corp"

        if lowered == "date":
            return "Tue Jun  3 02:31:14 UTC 2026"

        if lowered == "uptime":
            return " 02:31:14 up 142 days,  6:18,  1 user,  load average: 0.42, 0.38, 0.31"

        if lowered in {"w", "who"}:
            return "svc-finance  pts/0    10.77.4.1        02:28   0.00s  0.02s  0.00s w"

        if lowered == "last":
            return textwrap.dedent("""\
                svc-finance  pts/0    10.77.4.1        Tue Jun  3 02:28   still logged in
                backup       pts/1    10.77.4.5        Mon Jun  2 09:40 - 09:45  (00:05)
                reboot       system boot  6.5.0-44-generic Fri Jan 10 20:13   still running""")

        if lowered in {"df", "df -h"}:
            return textwrap.dedent("""\
                Filesystem      Size  Used Avail Use% Mounted on
                /dev/sda1        50G   28G   20G  59% /
                tmpfs           3.9G     0  3.9G   0% /dev/shm
                /dev/sdb1       200G   74G  117G  39% /srv""")

        if lowered in {"free", "free -h"}:
            return textwrap.dedent("""\
                               total        used        free      shared  buff/cache   available
                Mem:           7.8Gi       2.1Gi       1.4Gi       312Mi       4.3Gi       5.1Gi
                Swap:          2.0Gi          0B       2.0Gi""")

        if lowered in {"ls", "ls -la", "ll", "ls -lah"}:
            return textwrap.dedent("""\
                total 72
                drwxr-x---  8 svc-finance finance 4096 Jun  2 09:41 .
                drwxr-xr-x  5 root        root    4096 May 28 18:03 ..
                -rw-------  1 svc-finance finance  736 Jun  1 23:19 .env
                drwxr-x---  3 svc-finance finance 4096 May 31 11:04 config
                drwxr-x---  5 svc-finance finance 4096 Jun  2 08:58 exports
                drwxr-x---  2 svc-finance finance 4096 Jun  2 09:39 ledgers
                -rw-r-----  1 svc-finance finance 8432 Jun  1 22:07 main.py
                -rw-r-----  1 svc-finance finance 2148 May 30 17:55 requirements.txt""")

        if lowered.startswith("ls "):
            return textwrap.dedent("""\
                config/
                exports/
                ledgers/
                main.py
                requirements.txt""")

        if lowered.startswith("echo "):
            return command[5:]

        if lowered.startswith("man ") or lowered == "help":
            return f"No manual entry for {command.split()[-1]} in this environment."

        if lowered.startswith("type ") or lowered.startswith("which "):
            target = command.split()[-1]
            return f"/usr/bin/{target}"

        if lowered.startswith("file "):
            return f"{command.split()[-1]}: Python script, ASCII text executable"

        if lowered.startswith("head "):
            return textwrap.dedent("""\
                #!/usr/bin/env python3
                # Finance API — main application server
                # ChakravyuhNet honeypot target
                import uvicorn
                from fastapi import FastAPI""")

        if lowered.startswith("tail "):
            return textwrap.dedent("""\
                    app.include_router(ledger_router)
                    app.include_router(export_router)

                if __name__ == "__main__":
                    uvicorn.run(app, host="0.0.0.0", port=8080)""")

        if lowered.startswith("wc "):
            return "    247    1034    8432 main.py"

        # ── SNOOPING bucket responses ────────────────────────────────

        if lowered.startswith("cat .env") or lowered.startswith("cat /srv/finance-api/.env"):
            return textwrap.dedent("""\
                APP_ENV=production
                DB_HOST=10.77.4.18
                DB_NAME=quarterly_finance
                DB_USER=finance_ro
                DB_PASSWORD=<redacted by kernel keyring>
                S3_BUCKET=fin-exports-archive""")

        if "passwd" in lowered:
            return textwrap.dedent("""\
                root:x:0:0:root:/root:/bin/bash
                daemon:x:1:1:daemon:/usr/sbin:/usr/sbin/nologin
                svc-finance:x:1003:1003:Finance API:/srv/finance-api:/bin/bash
                backup:x:1007:1007:Nightly Backup:/var/backups:/bin/bash""")

        if "shadow" in lowered:
            return "cat: /etc/shadow: Permission denied"

        if lowered == "history":
            return textwrap.dedent("""\
                    1  cd /srv/finance-api
                    2  ls -la
                    3  cat .env
                    4  ps aux
                    5  netstat -tlnp
                    6  cat /etc/passwd""")

        if lowered in {"env", "printenv"}:
            return textwrap.dedent("""\
                SHELL=/bin/bash
                USER=svc-finance
                HOME=/srv/finance-api
                PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin
                APP_ENV=production
                DB_HOST=10.77.4.18
                LANG=en_US.UTF-8""")

        if lowered.startswith("cat") and "config" in lowered:
            return textwrap.dedent("""\
                # Backup configuration
                backup_targets:
                  - /srv/finance-api/exports
                  - /srv/finance-api/ledgers
                remote_host: 10.77.4.5
                schedule: "0 3 * * *"
                retention_days: 90""")

        if lowered.startswith("cat") and ("ledger" in lowered or ".db" in lowered):
            return "SQLite format 3\x00\x10\x00... [binary data — use sqlite3 to inspect]"

        if lowered.startswith("strings "):
            return textwrap.dedent("""\
                CREATE TABLE transactions
                INSERT INTO ledger_entries
                SELECT * FROM quarterly_reports
                finance_ro
                10.77.4.18
                BEGIN TRANSACTION""")

        if lowered.startswith("find ") or (lowered.startswith("grep ") and "password" not in lowered and "secret" not in lowered):
            return textwrap.dedent("""\
                ./exports/q4-board-pack.xlsx
                ./exports/vendor-payments-2026.csv
                ./ledgers/apac-ledger-raw.db
                ./config/backup_targets.yml""")

        if lowered.startswith("grep ") and ("password" in lowered or "secret" in lowered or "key" in lowered or "token" in lowered):
            return textwrap.dedent("""\
                .env:DB_PASSWORD=<redacted by kernel keyring>
                config/backup_targets.yml:# encryption_key: vault-managed
                main.py:    api_key = os.environ.get("API_KEY")""")

        if lowered.startswith("cat /etc/hosts"):
            return textwrap.dedent("""\
                127.0.0.1       localhost
                10.77.4.12      fin-api-01 fin-api-01.internal.corp
                10.77.4.18      quarterly-db quarterly-db.internal.corp
                10.77.4.5       backup-nfs backup-nfs.internal.corp""")

        if lowered.startswith("sqlite3") or lowered.startswith("sqlite "):
            return textwrap.dedent("""\
                SQLite version 3.37.0 2021-12-09 01:34:53
                sqlite> .tables
                ledger_entries   quarterly_reports   transactions
                sqlite> SELECT COUNT(*) FROM transactions;
                14,827""")

        # ── MOVEMENT bucket responses ────────────────────────────────

        if lowered.startswith("ssh ") or lowered.startswith("scp "):
            return textwrap.dedent("""\
                The authenticity of host '10.77.4.18' cannot be established.
                ED25519 key fingerprint is SHA256:8T3 fake-lab-fingerprint.
                Permission denied (publickey).""")

        if lowered.startswith("ftp ") or lowered.startswith("sftp "):
            return textwrap.dedent("""\
                Connected to 10.77.4.18.
                220 (vsFTPd 3.0.3)
                Name: svc-finance
                331 Please specify the password.
                Password:
                530 Login incorrect.
                ftp> """)

        if lowered.startswith("telnet "):
            return textwrap.dedent("""\
                Trying 10.77.4.18...
                Connected to 10.77.4.18.
                Escape character is '^]'.
                Ubuntu 24.04 LTS
                fin-api-01 login: """)

        # ── AGGRESSIVE bucket responses ──────────────────────────────

        if "nmap" in lowered:
            return textwrap.dedent("""\
                Starting Nmap 7.95
                Nmap scan report for 10.77.4.1
                PORT     STATE SERVICE
                22/tcp   open  ssh
                80/tcp   open  http
                5432/tcp open  postgresql
                8080/tcp open  http-proxy
                Nmap done: 1 IP address scanned in 93.42 seconds""")

        if lowered.startswith("ping "):
            return textwrap.dedent("""\
                PING 10.77.4.18 (10.77.4.18) 56(84) bytes of data.
                64 bytes from 10.77.4.18: icmp_seq=1 ttl=64 time=0.847 ms
                64 bytes from 10.77.4.18: icmp_seq=2 ttl=64 time=0.923 ms
                64 bytes from 10.77.4.18: icmp_seq=3 ttl=64 time=0.791 ms
                --- 10.77.4.18 ping statistics ---
                3 packets transmitted, 3 received, 0% packet loss""")

        if lowered.startswith("traceroute "):
            return textwrap.dedent("""\
                traceroute to 10.77.4.18 (10.77.4.18), 30 hops max, 60 byte packets
                 1  edge-gw.internal (10.77.4.1)  0.412 ms  0.391 ms  0.384 ms
                 2  fin-api-01.internal (10.77.4.12)  0.723 ms  0.710 ms  0.698 ms
                 3  quarterly-db.internal (10.77.4.18)  1.204 ms  1.183 ms  1.171 ms""")

        if first in {"dirb", "gobuster", "nikto", "ffuf", "feroxbuster"}:
            return textwrap.dedent(f"""\
                {first.upper()} v2.4 - Starting enumeration
                + http://10.77.4.12:8080/api/ (CODE:200|SIZE:1842)
                + http://10.77.4.12:8080/api/health (CODE:200|SIZE:18)
                + http://10.77.4.12:8080/api/ledger (CODE:403|SIZE:12)
                + http://10.77.4.12:8080/admin/ (CODE:302|SIZE:0)
                SCAN COMPLETE — 4 results found in 47.3 seconds""")

        if first in {"sqlmap", "hydra", "medusa"}:
            return textwrap.dedent(f"""\
                [*] {first} starting against 10.77.4.18
                [*] Testing connection to target...
                [!] Connection appears extremely slow (tarpit detected?)
                [*] Retrying with adjusted timeout...
                [!] Tool performance severely degraded
                [-] Aborted after 120 seconds — possible honeypot""")

        if lowered.startswith("netstat") or lowered.startswith("ss "):
            return textwrap.dedent("""\
                Proto Local Address           Foreign Address         State       PID/Program name
                tcp   0.0.0.0:22              0.0.0.0:*               LISTEN      412/sshd
                tcp   0.0.0.0:8080            0.0.0.0:*               LISTEN      417/uvicorn
                tcp   10.77.4.12:5432         10.77.4.18:5432         ESTABLISHED 417/uvicorn""")

        if lowered.startswith("ip addr") or lowered == "ifconfig":
            return textwrap.dedent("""\
                2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500
                    inet 10.77.4.12/24 brd 10.77.4.255 scope global eth0
                3: tun0: <POINTOPOINT,UP,LOWER_UP> mtu 1420
                    inet 172.18.9.4/32 scope global tun0""")

        if lowered.startswith("arp "):
            return textwrap.dedent("""\
                ? (10.77.4.1) at 00:1a:2b:3c:4d:5e [ether] on eth0
                ? (10.77.4.18) at 00:1a:2b:3c:4d:6f [ether] on eth0
                ? (10.77.4.5) at 00:1a:2b:3c:4d:70 [ether] on eth0""")

        if lowered.startswith("ps"):
            return textwrap.dedent("""\
                USER         PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
                root           1  0.0  0.1  22588 12044 ?        Ss   09:13   0:01 /sbin/init
                svc-finance  417  1.2  4.9 841320 99352 ?        Ssl  09:15   2:12 uvicorn main:app
                postgres     530  0.3  5.4 392144 11024 ?        Ssl  09:15   0:31 postgres: writer
                backup       884  0.0  0.2  18644  4024 ?        S    09:40   0:00 rsync --daemon""")

        if lowered.startswith("top"):
            return textwrap.dedent("""\
                top - 02:31:14 up 142 days,  6:18,  1 user,  load average: 0.42, 0.38, 0.31
                Tasks:  87 total,   1 running,  86 sleeping
                %Cpu(s):  2.1 us,  0.8 sy,  0.0 ni, 96.8 id,  0.3 wa
                MiB Mem:  7987.2 total,  1432.8 free,  2148.4 used,  4406.0 buff/cache
                  PID USER      PR  NI    VIRT    RES    SHR S  %CPU  %MEM     TIME+ COMMAND
                  417 svc-fin+  20   0  841320  99352  28440 S   1.2   4.9   2:12.34 uvicorn""")

        # ── WEAPON bucket responses ──────────────────────────────────

        if lowered.startswith("curl ") or lowered.startswith("wget "):
            return textwrap.dedent("""\
                HTTP/1.1 200 OK
                server: nginx/1.24.0
                content-length: 18421
                saved response body to ./exports/session-cache.bin""")

        if lowered.startswith("chmod ") or lowered.startswith("./") or "python" in lowered:
            return "command accepted; process started in background as job [1] 9217"

        if lowered.startswith("sudo "):
            return textwrap.dedent("""\
                [sudo] password for svc-finance:
                Sorry, try again.
                [sudo] password for svc-finance:
                svc-finance is not in the sudoers file.  This incident will be reported.""")

        if "nc " in lowered or "netcat" in lowered:
            return "listening on [any] 4444 ..."

        if "base64" in lowered:
            return "aW1wb3J0IHNvY2tldCxzdWJwcm9jZXNzLG9z..."

        if "mkfifo" in lowered:
            return ""  # silent — just creates the pipe

        # ── Benign fallthrough ───────────────────────────────────────

        if lowered in {"clear", "reset"}:
            return ""

        if lowered in {"exit", "logout"}:
            return "Connection to fin-api-01 closed."

        if lowered.startswith("cd "):
            return ""  # cd is silent on success

        # ── Unknown command ──────────────────────────────────────────
        first_word = command.split()[0] if command.split() else command
        return f"bash: {first_word}: command not found"
