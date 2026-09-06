#!/usr/bin/env bash
echo "LUMEN ingestion (Go) + AI/ML pipeline (Python), CPU-only."
echo "No single run action - use the Shell tab and run these yourself:"
echo ""
echo "  go build -o lumen-backend ."
echo "  cp sites.example.json sites.json    # then edit with real coordinates"
echo "  ./lumen-backend all"
echo "  pip install -r ai-ml/requirements.txt --break-system-packages"
echo "  python3 ai-ml/run_lumen_inference.py"
