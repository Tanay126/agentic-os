# backend/test_day1.py
"""
Run this to verify Day 1 is working.

Usage:
  python test_day1.py
  
What it does:
  1. Connects to GitHub (public repo, no token needed for public)
  2. Fetches 20 pull requests
  3. Ingests them into ChromaDB
  4. Runs 3 test queries
  5. Shows you the results with scores
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.connectors.github import GitHubConnector
from app.services.ingestion import IngestionService

def run_test():
    print("=" * 60)
    print("AGENTIC OS — DAY 1 TEST")
    print("=" * 60)
    
    # STEP 1: Connect to GitHub
    # We'll use a public repo so you don't need a token yet
    # Try your own repo or any public one
    token = os.getenv("GITHUB_TOKEN", "")  # Optional for public repos
    
    print("\n1. Connecting to GitHub...")
    connector = GitHubConnector(
        token=token,
        owner="fastapi",   # Public org
        repo="fastapi"      # Public repo with rich history
    )
    
    # STEP 2: Fetch events
    print("\n2. Fetching pull requests...")
    events = connector.get_pull_requests(limit=20)
    print(f"   Got {len(events)} events")
    
    # Show what one event looks like
    if events:
        e = events[0]
        print(f"\n   Sample event:")
        print(f"   artifact_id: {e.artifact_id}")
        print(f"   event_type:  {e.event_type}")
        print(f"   actor:       {e.actor}")
        print(f"   title:       {e.title[:60]}...")
        print(f"   authority:   {e.metadata.get('authority_score', '?')}")
    
    # STEP 3: Ingest
    print("\n3. Ingesting into knowledge base...")
    service = IngestionService(data_dir="./data")
    stats = service.ingest_events(events)
    print(f"   Stats: {stats}")
    
    # STEP 4: Query
    print("\n4. Running test queries...")
    test_queries = [
        "How do I add custom middleware?",
        "authentication and security",
        "bug fix in routing"
    ]
    
    for query in test_queries:
        print(f"\n   Query: '{query}'")
        results = service.collection.query(
            query_texts=[query],
            n_results=3,
            include=["documents", "metadatas", "distances"]
        )
        
        for i, (doc, meta, dist) in enumerate(zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0]
        )):
            # Distance in cosine = 0 means identical, 2 means opposite
            # We convert to similarity: 1 - (distance/2) → 0 to 1
            similarity = round(1 - (dist / 2), 3)
            print(f"\n   Result {i+1} (similarity: {similarity})")
            print(f"   Title: {meta['title'][:60]}")
            print(f"   Source: {meta['source']} | Authority: {meta['authority_score']}")
            print(f"   URL: {meta['url'][:60]}")
    
    print("\n" + "=" * 60)
    print("DAY 1 COMPLETE! Your knowledge base is alive.")
    print("=" * 60)

if __name__ == "__main__":
    run_test()