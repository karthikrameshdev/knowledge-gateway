"""Small reproducible local HTTP benchmark; never asserts an environment-independent SLA."""
import asyncio
import json
import os
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
import httpx


async def main():
    url = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8088'
    headers = {'X-API-Key': os.environ.get('KNOWLEDGE_GATEWAY_API_KEY', '')}
    async with httpx.AsyncClient(base_url=url, timeout=15, headers=headers) as client:
        async def query(text):
            start = time.perf_counter()
            result = await client.post('/api/v1/query', json={'query': text, 'sources': ['okf', 'filesystem'], 'page_size': 3})
            result.raise_for_status()
            data = result.json()
            assert data['items'] and not data['degraded']
            return (time.perf_counter() - start) * 1000, data
        cold = [await query('vault security benchmark ' + str(i) + '-' + str(time.time_ns())) for i in range(30)]
        text = 'vault secrets warm benchmark ' + str(time.time_ns())
        await query(text)
        warm = [await query(text) for _ in range(100)]
        assert all(d['cached'] for _, d in warm)
        parallel = await asyncio.gather(*(query(text) for _ in range(20)))
        def stats(values):
            values = sorted(values)
            return {'median_ms': round(statistics.median(values), 3), 'p95_ms': round(values[int((len(values)-1)*0.95)], 3)}
        print(json.dumps({'measured_at': datetime.now(timezone.utc).isoformat(), 'python': platform.python_version(),
                          'scope': 'Local HTTP; OKF + filesystem demo fixtures; 30 cold, 100 warm, 20 concurrent warm requests',
                          'cold_http': stats([t for t, _ in cold]), 'warm_http': stats([t for t, _ in warm]),
                          'warm_service': stats([d['latency_ms'] for _, d in warm]),
                          'concurrent_successes': len(parallel)}, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
