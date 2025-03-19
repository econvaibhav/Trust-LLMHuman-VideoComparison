"""Start three isolated demo servers and run real browser checks; no paid APIs."""
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from videotrust.__main__ import init_demo
from videotrust.server import create_server

ROOT = Path(__file__).resolve().parents[1]


def main():
    for mode in ("direct", "interview", "paired"):
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "study"
            init_demo(workspace, interview=mode=="interview", paired=mode=="paired")
            if mode == "paired":
                from videotrust.media import prepare
                good, errors = prepare(workspace, frames=2)
                if errors: raise RuntimeError(errors)
            token = "local-browser-verification-token"
            server = create_server(workspace, port=0, admin_token=token)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            env = {**os.environ, "VIDEOTRUST_TEST_URL": f"http://127.0.0.1:{server.server_port}",
                   "VIDEOTRUST_TEST_TOKEN": token}
            try:
                script = {"direct":"browser_smoke.cjs", "interview":"browser_interview.cjs", "paired":"browser_paired.cjs"}[mode]
                subprocess.run(["node", str(ROOT / "tests" / script)], env=env, check=True, timeout=120)
            finally:
                server.shutdown(); server.server_close(); thread.join()


if __name__ == "__main__":
    main()
