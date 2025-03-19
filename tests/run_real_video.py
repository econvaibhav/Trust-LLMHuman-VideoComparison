"""Opt-in browser check using a local video; synthetic responses stay in a temporary study."""
import argparse
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from videotrust.__main__ import register
from videotrust.common import read_json, write_json
from videotrust.server import create_server


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video',required=True,type=Path)
    parser.add_argument('--prepared-workspace',type=Path)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)/'study';register(root,args.video)
        cfg=read_json(root/'study.json');cfg.update(title='Local playback test',consent_text='Automated local test. Responses are synthetic and discarded.',consent_version='qa-v1')
        write_json(root/'study.json',cfg)
        if args.prepared_workspace:
            for folder in ('evidence','frames'):
                shutil.copytree(args.prepared_workspace/folder,root/folder)
        server=create_server(root,port=0,admin_token='real-video-local-test-token')
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        env={**os.environ,'VIDEOTRUST_TEST_URL':f'http://127.0.0.1:{server.server_port}',
             'VIDEOTRUST_TEST_TOKEN':'real-video-local-test-token',
             'VIDEOTRUST_EXPECT_EVIDENCE':'1' if args.prepared_workspace else '0'}
        try:subprocess.run(['node',str(Path(__file__).with_name('browser_real.cjs'))],env=env,check=True,timeout=120)
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':main()
