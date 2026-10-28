"""Disposable browser-test app, isolated from the owner's actual studio state."""
import os
from pathlib import Path
import sys
import tempfile

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from studio.app import create_app  # noqa: E402


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='short-studio-browser-server-') as directory:
        app = create_app(data_dir=Path(directory),
                         password=os.environ.get('STUDIO_TEST_PASSWORD', 'browser-test-password'))
        uvicorn.run(app, host='127.0.0.1', port=8765, log_level='warning', proxy_headers=False)
