# backend/app/models/event.py

# Why Pydantic? It validates data at runtime AND gives us auto-documentation.
# If an event comes in missing 'source', Pydantic raises an error immediately.
# Without this, bugs hide in your database for weeks.
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid


class EventType(str):
    """
    An enum of all event types we'll ever ingest.
    Keeping them as constants prevents typos: 
    "pr_merge" vs "pr_merged" would be a silent bug.
    """
    PR_MERGED = "pr_merged"
    ISSUE_CREATED = "issue_created"
    ISSUE_CLOSED = "issue_closed"
    COMMENT_ADDED = "comment_added"
    DOC_UPDATED = "doc_updated"
    MESSAGE_SENT = "message_sent"


class PermissionLevel(str):
    """
    Four tiers of sensitivity — matches what real companies use.
    We'll use these to hard-filter before any embedding search.
    """
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class Event(BaseModel):
    """
    The unified schema that EVERY source must conform to.
    
    Why a unified schema? Because if GitHub events look different from
    Jira events, your downstream code needs 10 if-statements everywhere.
    By normalizing at ingestion, the knowledge graph only speaks one language.
    
    This is the same principle as a power adapter: 
    different plugs (GitHub, Jira, Slack) → same voltage out (Event).
    """
    
    # Auto-generated unique ID — we use uuid4 (random, not time-based)
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    
    # Which system did this come from?
    source: str  # "github", "jira", "slack", "markdown"
    
    # What kind of thing happened?
    event_type: str  # "pr_merged", "issue_closed", etc.
    
    # Who did it? (GitHub username, Jira user, Slack user ID)
    actor: str
    
    # CRITICAL: two timestamps, not one.
    # timestamp_event = when it happened in the real world
    # timestamp_ingested = when OUR system received it
    # These can be minutes apart. We sort by timestamp_event,
    # not by when we got it. This prevents the "wrong causal story" bug
    # described in your document.
    timestamp_event: datetime
    timestamp_ingested: datetime = Field(default_factory=datetime.utcnow)
    
    # A stable ID for the thing this event is about.
    # Same PR can have multiple events (opened, reviewed, merged).
    # artifact_id stays the same across all of them.
    artifact_id: str
    
    # The actual text content — normalized to plain text
    content: str
    
    # Title for display purposes
    title: str = ""
    
    # URL to the original source
    url: str = ""
    
    # === PERMISSION FIELDS — non-negotiable ===
    # These travel with the event FOREVER.
    # An event never loses its permission context.
    allowed_users: List[str] = Field(default_factory=list)
    allowed_groups: List[str] = Field(default_factory=list)
    sensitivity_level: str = PermissionLevel.INTERNAL
    tenant_id: str = "default"  # For multi-tenant: separates Company A from Company B
    
    # Related entities extracted from the content
    linked_artifact_ids: List[str] = Field(default_factory=list)
    mentioned_users: List[str] = Field(default_factory=list)
    
    # Extra data that's source-specific (GitHub PR number, Jira ticket key, etc.)
    metadata: dict = Field(default_factory=dict)

    class Config:
        # Allow extra fields from subclasses
        extra = "allow"


class Artifact(BaseModel):
    """
    An Artifact is the 'current state' of something.
    
    The difference from Event:
    - Event = "PR #47 was merged on Tuesday" (a thing that happened)
    - Artifact = "PR #47" (the thing itself, with its current state)
    
    Multiple Events update one Artifact.
    The Artifact is what lives in the knowledge graph.
    The Event log is how it got to that state.
    
    Think of it like Git:
    - Commits = Events
    - Working tree = Artifact
    """
    artifact_id: str
    source: str
    artifact_type: str  # "pull_request", "issue", "document", "message"
    title: str
    content: str
    url: str = ""
    
    # === THERMODYNAMIC SCORES — the magic of Company Brain ===
    # These are what makes us different from plain RAG.
    
    # Temperature: how recently/actively used is this? Decays over time.
    # Fresh PR merged today = 1.0. Wiki page from 2022 = 0.1
    temperature: float = 1.0
    
    # Authority: how trustworthy is this source?
    # Merged PR code = 0.9. Slack message = 0.4.
    authority_score: float = 0.5
    
    # Usage: how often has this been retrieved/referenced?
    usage_count: int = 0
    
    # Contradiction: does this conflict with newer sources?
    contradiction_risk: float = 0.0
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_accessed_at: Optional[datetime] = None
    
    # Permissions (same fields as Event — permission is inherited)
    allowed_users: List[str] = Field(default_factory=list)
    allowed_groups: List[str] = Field(default_factory=list)
    sensitivity_level: str = PermissionLevel.INTERNAL
    tenant_id: str = "default"
    
    # Graph relationships (populated by entity extractor)
    linked_artifact_ids: List[str] = Field(default_factory=list)
    
    metadata: dict = Field(default_factory=dict)