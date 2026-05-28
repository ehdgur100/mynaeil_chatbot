import ssl
import os

# 1. Standard library
ssl._create_default_https_context = ssl._create_unverified_context
ssl.create_default_context = lambda *args, **kwargs: ssl._create_unverified_context()

# 2. Environment variables for requests
import certifi
os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

# 3. Patch httpx
try:
    import httpx
    _original_httpx_client_init = httpx.Client.__init__
    def _patched_httpx_client_init(self, *args, **kwargs):
        kwargs['verify'] = False
        _original_httpx_client_init(self, *args, **kwargs)
    httpx.Client.__init__ = _patched_httpx_client_init

    _original_httpx_async_client_init = httpx.AsyncClient.__init__
    def _patched_httpx_async_client_init(self, *args, **kwargs):
        kwargs['verify'] = False
        _original_httpx_async_client_init(self, *args, **kwargs)
    httpx.AsyncClient.__init__ = _patched_httpx_async_client_init
except ImportError:
    pass

# 4. Patch aiohttp
try:
    import aiohttp
    _original_tcp_connector = aiohttp.TCPConnector.__init__
    def _patched_tcp_connector(self, *args, **kwargs):
        kwargs['verify_ssl'] = False
        _original_tcp_connector(self, *args, **kwargs)
    aiohttp.TCPConnector.__init__ = _patched_tcp_connector
except ImportError:
    pass

# 5. Patch google-auth / grpc if needed (often handled by the env vars)
