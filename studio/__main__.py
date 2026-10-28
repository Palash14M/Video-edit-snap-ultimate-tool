import os
import uvicorn

if __name__ == '__main__':
    uvicorn.run('studio.app:create_app', factory=True,
                host=os.environ.get('STUDIO_HOST', '127.0.0.1'),
                port=int(os.environ.get('PORT', '8000')), proxy_headers=False)
