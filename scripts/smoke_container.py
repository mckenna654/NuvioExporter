"""Exercise a running release container with neutral data and no provider calls."""
import json
import http.client
import sys
import time
import urllib.error
import urllib.request


def check(base):
    def request(path, data=None):
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(base + path, data=body,
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=3) as response:
            return json.load(response)

    deadline = time.monotonic() + 45
    while True:
        try:
            health = request('/api/health')
            break
        except (OSError, http.client.HTTPException):
            if time.monotonic() >= deadline:
                raise RuntimeError('Container did not become ready within 45 seconds.') from None
            time.sleep(1)
    assert health['status'] == 'ok' and health['app'] == 'NuvioExporter'
    original = request('/api/presets/nuvio')['rawData']
    result = request('/api/fusion/convert', {'export_data': original})
    assert result['report']['canExport']
    assert result['report']['counts']['preserved'] > 0
    assert result['report']['counts']['unsupported'] == 0
    assert result['fusionConfig']['requiredAddons']
    with urllib.request.urlopen(base + '/', timeout=3) as response:
        assert b'NuvioExporter' in response.read()
    print(f"Container smoke test passed: version {health['version']}; "
          f"{result['report']['counts']['preserved']} example sources converted.")


if __name__ == '__main__':
    check(sys.argv[1].rstrip('/') if len(sys.argv) > 1 else 'http://127.0.0.1:7088')
