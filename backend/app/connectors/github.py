# backend/app/connectors/github.py

"""
The GitHub Connector

What it does: Talks to the GitHub REST API and converts
GitHub's data format into our unified Event schema.

Why GitHub first? Because:
1. Public repos = we can demo without needing a real company
2. Pull Requests + Issues are RICH data (discussions, decisions, code changes)
3. GitHub's API is the best documented in the industry
"""

import requests
import os
from datetime import datetime
from typing import List, Optional
from ..models.event import Event, Artifact


class GitHubConnector:
    """
    Pulls events from a GitHub repository.
    
    Authentication: GitHub Personal Access Token
    Rate limits: 5,000 requests/hour with token (plenty for us)
    """
    
    def __init__(self, token: str, owner: str, repo: str):
        """
        token: GitHub Personal Access Token (from github.com/settings/tokens)
        owner: GitHub username or org ("facebook")
        repo: Repository name ("react")
        """
        self.token = token
        self.owner = owner
        self.repo = repo
        self.base_url = "https://api.github.com"
        
        # Every request needs these headers
        # Authorization: how we prove we're allowed to read the repo
        # Accept: tells GitHub which API version to use
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            self.headers["Authorization"] = f"token {token}"
    
    def _get(self, endpoint: str, params: dict = None) -> dict:
        """
        Internal helper: make a GET request to GitHub API.
        
        Why a helper method? Because every API call needs:
        - The same headers
        - Error handling
        - Rate limit checking
        
        DRY principle: Don't Repeat Yourself.
        """
        url = f"{self.base_url}{endpoint}"
        response = requests.get(url, headers=self.headers, params=params)
        
        # Check rate limit — GitHub tells us in headers
        remaining = int(response.headers.get("X-RateLimit-Remaining", 999))
        if remaining < 10:
            print(f"WARNING: Only {remaining} GitHub API calls remaining this hour")
        
        # Raise an exception for 4xx/5xx errors
        # This is better than silently returning empty data
        response.raise_for_status()
        
        return response.json()
    
    def get_pull_requests(
        self, 
        state: str = "all",  # "open", "closed", "all"
        limit: int = 50
    ) -> List[Event]:
        """
        Fetches pull requests and converts them to Events.
        
        Why PRs? They contain:
        - What code changed (the actual knowledge)
        - Who reviewed it (authority signal)  
        - Discussions about WHY (the most valuable context)
        - Link to the Jira ticket it fixes (graph edge!)
        """
        events = []
        page = 1
        fetched = 0
        
        while fetched < limit:
            # GitHub paginates results — we fetch 30 at a time
            prs = self._get(
                f"/repos/{self.owner}/{self.repo}/pulls",
                params={
                    "state": state,
                    "per_page": min(30, limit - fetched),
                    "page": page,
                    "sort": "updated",
                    "direction": "desc"
                }
            )
            
            if not prs:  # No more pages
                break
            
            for pr in prs:
                event = self._pr_to_event(pr)
                events.append(event)
                fetched += 1
            
            page += 1
        
        print(f"Fetched {len(events)} pull requests from {self.owner}/{self.repo}")
        return events
    
    def _pr_to_event(self, pr: dict) -> Event:
        """
        Converts a raw GitHub PR dict → our unified Event schema.
        
        This is the "translation layer" — the most important part
        of any connector. The key decisions:
        
        1. artifact_id: We use "github_pr_{number}" so if the same
           PR gets updated, we update the same artifact (not create a new one)
        
        2. event_type: "pr_merged" vs "pr_opened" vs "pr_closed"
           These mean different things for knowledge authority.
           A merged PR = ground truth of what shipped.
           An abandoned PR = less authoritative.
        
        3. content: We combine title + body + labels.
           More text = better semantic search.
        
        4. authority_score: Merged PRs start at 0.85.
           Why not 1.0? Because even merged code can be
           superseded by a newer PR.
        """
        
        # Determine event type from PR state
        if pr.get("merged_at"):
            event_type = "pr_merged"
            authority = 0.85  # Merged = ground truth
        elif pr.get("state") == "closed":
            event_type = "pr_closed"
            authority = 0.4   # Closed without merge = abandoned
        else:
            event_type = "pr_opened"
            authority = 0.6   # Open = proposal, not confirmed
        
        # Build rich text content for embedding
        # More context = better retrieval
        content_parts = [
            f"PR #{pr['number']}: {pr['title']}",
            "",
            pr.get("body") or "(no description provided)",
            "",
            f"Author: {pr['user']['login']}",
            f"State: {pr['state']}",
        ]
        
        # Add labels (e.g., "bug", "enhancement", "breaking-change")
        labels = [l["name"] for l in pr.get("labels", [])]
        if labels:
            content_parts.append(f"Labels: {', '.join(labels)}")
        
        # Look for Jira ticket references in title/body
        # Pattern: "PROJ-123" or "Fixes PROJ-456"
        import re
        text_to_search = f"{pr['title']} {pr.get('body', '')}"
        jira_refs = re.findall(r'[A-Z]+-\d+', text_to_search)
        linked_ids = [f"jira_issue_{ref}" for ref in jira_refs]
        
        # Parse timestamps — GitHub uses ISO 8601 format
        created_at = datetime.fromisoformat(
            pr["created_at"].replace("Z", "+00:00")
        )
        
        # Use merged_at if available, else updated_at, else created_at
        event_time = created_at
        if pr.get("merged_at"):
            event_time = datetime.fromisoformat(
                pr["merged_at"].replace("Z", "+00:00")
            )
        elif pr.get("updated_at"):
            event_time = datetime.fromisoformat(
                pr["updated_at"].replace("Z", "+00:00")
            )
        
        return Event(
            source="github",
            event_type=event_type,
            actor=pr["user"]["login"],
            timestamp_event=event_time,
            artifact_id=f"github_pr_{self.owner}_{self.repo}_{pr['number']}",
            title=pr["title"],
            content="\n".join(content_parts),
            url=pr["html_url"],
            # For public repos, anyone can read
            # In production this would be your org's GitHub teams
            allowed_groups=["engineering"],
            sensitivity_level="internal",
            linked_artifact_ids=linked_ids,
            mentioned_users=[pr["user"]["login"]],
            metadata={
                "pr_number": pr["number"],
                "base_branch": pr.get("base", {}).get("ref", ""),
                "head_branch": pr.get("head", {}).get("ref", ""),
                "additions": pr.get("additions", 0),
                "deletions": pr.get("deletions", 0),
                "authority_score": authority,
                "jira_refs": jira_refs,
                "labels": labels
            }
        )
    
    def get_issues(self, limit: int = 50) -> List[Event]:
        """
        Fetches GitHub Issues and converts them to Events.
        
        Issues are different from PRs:
        - They're problems, requests, discussions
        - Closed issues = problems that were SOLVED (valuable knowledge)
        - Issue comments contain the actual diagnosis/solution
        """
        events = []
        
        issues_data = self._get(
            f"/repos/{self.owner}/{self.repo}/issues",
            params={
                "state": "all",
                "per_page": min(limit, 50),
                "sort": "updated",
                "direction": "desc"
            }
        )
        
        for issue in issues_data:
            # GitHub returns PRs in the /issues endpoint too
            # Filter them out — we handle PRs separately
            if "pull_request" in issue:
                continue
            
            content_parts = [
                f"Issue #{issue['number']}: {issue['title']}",
                "",
                issue.get("body") or "(no description)",
                "",
                f"State: {issue['state']}",
                f"Author: {issue['user']['login']}",
            ]
            
            labels = [l["name"] for l in issue.get("labels", [])]
            if labels:
                content_parts.append(f"Labels: {', '.join(labels)}")
            
            event_type = "issue_closed" if issue["state"] == "closed" else "issue_created"
            
            # Closed issues are more authoritative — the problem was understood
            authority = 0.7 if issue["state"] == "closed" else 0.5
            
            events.append(Event(
                source="github",
                event_type=event_type,
                actor=issue["user"]["login"],
                timestamp_event=datetime.fromisoformat(
                    issue["updated_at"].replace("Z", "+00:00")
                ),
                artifact_id=f"github_issue_{self.owner}_{self.repo}_{issue['number']}",
                title=issue["title"],
                content="\n".join(content_parts),
                url=issue["html_url"],
                allowed_groups=["engineering"],
                sensitivity_level="internal",
                metadata={
                    "issue_number": issue["number"],
                    "authority_score": authority,
                    "labels": labels
                }
            ))
        
        print(f"Fetched {len(events)} issues from {self.owner}/{self.repo}")
        return events
        