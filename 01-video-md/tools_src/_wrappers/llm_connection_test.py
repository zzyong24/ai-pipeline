#!/usr/bin/env python3
"""n8n wrapper: llm-connection-test"""
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from llm_connection_tester import test_connection

result = test_connection()
print(json.dumps(result, ensure_ascii=False))
