import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# boto3 raises NoRegionError at import time if no region is configured.
# Lambda always has AWS_REGION set; provide a fallback for local/CI environments.
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

# handler.py reads JIRA_PROJECT_KEY at module level; set a test default so
# importing the module during collection doesn't raise KeyError.
os.environ.setdefault("JIRA_PROJECT_KEY", "RC1")
os.environ.setdefault("STALE_DAYS", "7")
