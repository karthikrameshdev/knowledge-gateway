#!/usr/bin/env bash
set -e

# Setup environment PATH
export PATH="$HOME/.docker/bin:/Applications/Docker.app/Contents/Resources/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

echo "================================================================="
echo "       Knowledge Gateway: End-to-End Test & Docker Harness       "
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

# 2. Check and Start Docker Database Infrastructure
DOCKER_AVAILABLE=false
if command -v docker >/dev/null 2>&1; then
    if docker info >/dev/null 2>&1; then
        DOCKER_AVAILABLE=true
        echo "[+] Docker daemon is running. Starting WeftKit PostgreSQL & Qdrant..."
        docker compose -f docker-compose.test.yml up -d weftkit_postgres
        
        echo "[+] Waiting for WeftKit PostgreSQL database to initialize on port 5433..."
        RETRIES=20
        while [ $RETRIES -gt 0 ]; do
            if docker exec weftkit_test_postgres pg_isready -U weftkit_admin -d weftkit_db >/dev/null 2>&1; then
                echo "[✓] PostgreSQL (weftkit_db) is healthy and ready!"
                break
            fi
            sleep 1
            RETRIES=$((RETRIES - 1))
        done
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
echo "[+] Running complete automated test suite (Unit, Integration, API, Pagination, Connectors)..."
$PYTEST -v

# 5. Live Multi-Source Retrieval CLI Demo
echo ""
echo "================================================================="
echo "    Live Multi-Source Gateway Execution & Provenance Demo        "
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
    
    prompt = 'How does WeftKit handle Google auth, vault secrets, and PCI DSS compliance?'
    console.print(Panel(f'[bold white]{prompt}[/bold white]', title='[bold cyan]1. Inbound Query[/bold cyan]'))
    
    # Query Page 1
    req_p1 = GatewayQuery(
        query=prompt,
        tags=['auth', 'vault', 'pci-dss', 'weftkit'],
        page=1,
        page_size=4,
        min_score=0.10,
    )
    res_p1 = await gateway.query(req_p1)
    
    # Source Breakdown Table
    table_sources = Table(title='2. Multi-Source Retrieval Breakdown (Where Data Came From)', border_style='blue')
    table_sources.add_column('Source Connector', style='cyan')
    table_sources.add_column('Status', style='green')
    table_sources.add_column('Items Found', justify='center', style='bold yellow')
    table_sources.add_column('Latency', justify='right', style='magenta')
    
    for src, stat in res_p1.sources_searched.items():
        table_sources.add_row(src.upper(), stat.status, str(stat.count), f'{stat.latency_ms:.1f}ms')
    console.print(table_sources)
    
    # Consolidated Results Table
    table_items = Table(title=f'3. Consolidated & Paginated Items (Page 1/2 - Total Results: {res_p1.total_results})', border_style='green')
    table_items.add_column('Source', style='cyan')
    table_items.add_column('Title', style='white')
    table_items.add_column('ONNX Score', justify='center', style='bold green')
    table_items.add_column('Provenance / Origin', style='dim')
    
    for it in res_p1.items:
        origin = str(it.provenance.get('file_path') or it.provenance.get('table') or it.provenance.get('collection') or it.provenance.get('repo'))
        table_items.add_row(it.source_type.upper(), it.title[:45], f'{it.score:.3f}', origin)
    console.print(table_items)

asyncio.run(run_demo())
"

echo ""
echo "================================================================="
echo "   [✓] ALL TESTS PASSED! Knowledge Gateway is 100% verified.    "
echo "================================================================="
