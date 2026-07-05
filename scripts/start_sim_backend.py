"""Playwright E2E 模拟后端启动脚本。

设置 CXHMS_SIMULATION=1 后启动 uvicorn，装配假实现而非真实外部客户端。
供 frontend/playwright.config.ts webServer 调用，避免在 TypeScript 中处理环境变量转义。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ['CXHMS_SIMULATION'] = '1'

import uvicorn


def main():
    host = os.environ.get('CXHMS_HOST', '127.0.0.1')
    port = int(os.environ.get('CXHMS_PORT', '8001'))
    uvicorn.run('backend.api.app:app', host=host, port=port)


if __name__ == '__main__':
    main()
