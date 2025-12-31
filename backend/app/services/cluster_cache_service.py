from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.models import Cluster, ClusterStatusCache
import os

# Default TTL: 5 minutes (configurable via env)
DEFAULT_TTL_SECONDS = int(os.getenv("CLUSTER_CACHE_TTL", "300"))

def get_cached_status(db: Session, cluster_id: int, force_refresh: bool = False) -> dict:
    """
    Get cached cluster status or None if expired/missing

    Args:
        db: Database session
        cluster_id: Cluster ID
        force_refresh: If True, ignore cache and return None

    Returns:
        Cached data dict or None
    """
    if force_refresh:
        return None

    cache = db.query(ClusterStatusCache).filter(
        ClusterStatusCache.cluster_id == cluster_id
    ).first()

    if not cache:
        return None

    # Check if cache is expired
    if datetime.utcnow() > cache.expires_at:
        return None

    # Return cached data with metadata
    return {
        **cache.cached_data,
        "_cache_metadata": {
            "collected_at": cache.collected_at.isoformat(),
            "expires_at": cache.expires_at.isoformat(),
            "collection_duration_seconds": cache.collection_duration_seconds,
            "is_cached": True
        }
    }

def save_cache(db: Session, cluster_id: int, data: dict, collection_duration: int):
    """
    Save or update cluster status cache

    Args:
        db: Database session
        cluster_id: Cluster ID
        data: Aggregated cluster status data
        collection_duration: How long collection took in seconds
    """
    now = datetime.utcnow()
    expires_at = now + timedelta(seconds=DEFAULT_TTL_SECONDS)

    cache = db.query(ClusterStatusCache).filter(
        ClusterStatusCache.cluster_id == cluster_id
    ).first()

    if cache:
        # Update existing cache
        cache.cached_data = data
        cache.collected_at = now
        cache.expires_at = expires_at
        cache.collection_duration_seconds = collection_duration
    else:
        # Create new cache entry
        cache = ClusterStatusCache(
            cluster_id=cluster_id,
            cached_data=data,
            collected_at=now,
            expires_at=expires_at,
            collection_duration_seconds=collection_duration
        )
        db.add(cache)

    db.commit()

def invalidate_cache(db: Session, cluster_id: int):
    """
    Invalidate (delete) cache for a cluster

    Args:
        db: Database session
        cluster_id: Cluster ID
    """
    db.query(ClusterStatusCache).filter(
        ClusterStatusCache.cluster_id == cluster_id
    ).delete()
    db.commit()
