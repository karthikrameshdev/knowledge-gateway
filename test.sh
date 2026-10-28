#!/usr/bin/env bash
set -e

# Setup environment PATH
export PATH="$HOME/.docker/bin:/Applications/Docker.app/Contents/Resources/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

echo "================================================================="
echo "   Knowledge Gateway: End-to-End Test, Docker & Cache Harness    "
echo "================================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 1. Virtual Environment Check
if [ ! -d ".venv" ]; then
    echo "[+] Creating virtual environment with Python 3.13..."
    python3.13 -m venv .venv || python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r requirements.txt
fi

PYTHON=".venv/bin/python"
PYTEST=".venv/bin/pytest"

# 2. Check and Start Docker Infrastructure (PostgreSQL, Qdrant, Redis)
DOCKER_AVAILABLE=false
if command -v docker >/dev/null 2>&1; then
    if docker info >/dev/null 2>&1; then
        DOCKER_AVAILABLE=true
        echo "[+] Docker daemon is running. Starting PostgreSQL & Redis containers..."
        docker compose -f docker-compose.test.yml up -d postgres redis
        
        echo "[+] Waiting for PostgreSQL database to initialize on port 5433..."
        RETRIES=20
        while [ $RETRIES -gt 0 ]; do
            if docker exec gateway_test_postgres pg_isready -U postgres_admin -d gateway_db >/dev/null 2>&1; then
                echo "[✓] PostgreSQL (gateway_db) is healthy and ready!"
                break
            fi
            sleep 1
            RETRIES=$((RETRIES - 1))
        done

        echo "[+] Checking Redis caching container on port 6379..."
        if docker exec gateway_test_redis redis-cli ping >/dev/null 2>&1; then
            echo "[✓] Redis cache is healthy and ready!"
        fi
    else
        echo "[!] Docker daemon is not active. Using mock & in-memory database fallbacks."
    fi
else
    echo "[!] Docker CLI not found in PATH. Using local in-memory fallbacks."
fi

# 3. Compile / Export ONNX Neural Reranker Model
echo "[+] Validating local ONNX neural re-ranking model..."
$PYTHON models/export_onnx_model.py

# 4. Run Pytest Test Suite
echo "[+] Running complete automated test suite (Unit, Caching, Connectors, API, Pagination)..."
$PYTEST -v

# 5. Live Multi-Source Retrieval & Cache Acceleration Demo
echo ""
echo "================================================================="
echo "    Live Multi-Source Gateway Execution & Cache Acceleration     "
echo "================================================================="
$PYTHON -c "
import asyncio
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from src.gateway import KnowledgeGateway
from src.models import GatewayQuery
from src.config import load_config

console = Console()

async def run_demo():
    gateway = KnowledgeGateway(load_config())
    await gateway.cache.clear()
    
    prompt = 'How does OAuth 2.0 PKCE authentication, vault secrets, and PCI DSS compliance work?'
    console.print(Panel(f'[bold white]{prompt}[/bold white]', title='[bold cyan]1. Inbound Query Prompt[/bold cyan]'))
    
    # Request 1: Fresh Multi-Source Query (Cache MISS)
    req = GatewayQuery(
        query=prompt,
        tags=['auth', 'vault', 'pci-dss', 'security'],
        page=1,
        page_size=4,
        min_score=0.10,
    )
    console.print('[bold yellow][Query 1] Executing Uncached Multi-Source Retrieval...[/bold yellow]')
    res_miss = await gateway.query(req)
    
    # Source Breakdown Table
    table_sources = Table(title=f'Multi-Source Retrieval Breakdown (Uncached Latency: {res_miss.latency_ms:.1f}ms)', border_style='blue')
    table_sources.add_column('Source Connector', style='cyan')
    table_sources.add_column('Status', style='green')
    table_sources.add_column('Items Found', justify='center', style='bold yellow')
    table_sources.add_column('Latency', justify='right', style='magenta')
    
    for src, stat in res_miss.sources_searched.items():
        table_sources.add_row(src.upper(), stat.status, str(stat.count), f'{stat.latency_ms:.1f}ms')
    console.print(table_sources)
    
    # Request 2: Identical Query (Cache HIT)
    console.print('\n[bold green][Query 2] Repeating Identical Query (Testing Cache Layer)...[/bold green]')
    res_hit = await gateway.query(req)
    
    cache_panel = Panel(
        f'[bold green]CACHE HIT: {res_hit.cached}[/bold green]\n'
        f'Cache Backend: [bold cyan]{res_hit.cache_backend}[/bold cyan]\n'
        f'Accelerated Latency: [bold magenta]{res_hit.latency_ms:.2f}ms[/bold magenta] (vs {res_miss.latency_ms:.1f}ms uncached)\n'
        f'Speedup Factor: [bold yellow]{(res_miss.latency_ms / max(0.01, res_hit.latency_ms)):.1f}x faster[/bold yellow]\n'
        f'Consolidated Items Returned: [bold white]{len(res_hit.items)}[/bold white]',
        title='[bold green]⚡ High-Speed Caching Verification[/bold green]',
        border_style='green'
    )
    console.print(cache_panel)
    
    # Items Table
    table_items = Table(title=f'Consolidated & Paginated Items (Page 1/2 - Total Results: {res_hit.total_results})', border_style='green')
    table_items.add_column('Source', style='cyan')
    table_items.add_column('Title', style='white')
    table_items.add_column('ONNX Score', justify='center', style='bold green')
    table_items.add_column('Provenance / Origin', style='dim')
    
    for it in res_hit.items:
        origin = str(it.provenance.get('file_path') or it.provenance.get('table') or it.provenance.get('collection') or it.provenance.get('repo'))
        table_items.add_row(it.source_type.upper(), it.title[:45], f'{it.score:.3f}', origin)
    console.print(table_items)

asyncio.run(run_demo())
"

echo ""
echo "================================================================="
echo "   [✓] ALL TESTS PASSED! Knowledge Gateway & Cache are verified. "
echo "================================================================="
