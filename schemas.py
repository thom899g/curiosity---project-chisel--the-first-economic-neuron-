"""
Pydantic schemas for data validation and type safety.
Atomic schemas enforce temporal consistency and confidence scoring.
"""
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum

from pydantic import BaseModel, Field, validator, ConfigDict
import numpy as np


class AssetRiskClass(str, Enum):
    """Standardized risk classification."""
    STABLE = "stable"
    BLUE_CHIP = "blue_chip"
    ALT = "alt"
    MEME = "meme"
    DERIVATIVE = "derivative"
    ILLIQUID = "illiquid"


class AssetSnapshot(BaseModel):
    """
    Atomic asset observation with confidence metrics.
    Each snapshot is immutable and self-contained.
    """
    model_config = ConfigDict(validate_assignment=True)
    
    # Core Identity
    timestamp: datetime = Field(
        default_factory=lambda: datetime.utcnow().replace(microsecond=0),
        description="UTC timestamp of observation (second precision)"
    )
    source: str = Field(
        ..., 
        description="Data source identifier",
        pattern=r"^[a-z_]+$"  # snake_case validation
    )
    asset_id: str = Field(
        ...,
        description="Asset symbol in uppercase",
        pattern=r"^[A-Z0-9]+$"
    )
    
    # Quantitative Metrics
    quantity: float = Field(
        ..., 
        ge=0,
        description="Raw quantity held (no decimals)"
    )
    value_usd: float = Field(
        ...,
        ge=0,
        description="USD value at observation time"
    )
    
    # Quality Metrics
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Data quality score (1.0 = perfect)"
    )
    latency_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="Source response time in milliseconds"
    )
    
    # Classification
    risk_class: AssetRiskClass
    volatility_24h: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=10.0,  # 1000% max volatility
        description="Historical 24h volatility (0-1 = 0-100%)"
    )
    oracle_source: str = Field(
        default="coingecko",
        description="Price oracle used"
    )
    
    # Audit Trail
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Raw API response for verification"
    )
    
    @validator('timestamp')
    def validate_timestamp(cls, v):
        """Ensure timestamp is timezone-aware UTC."""
        if v.tzinfo is not None:
            raise ValueError("Timestamp must be naive UTC")
        return v
    
    @validator('confidence_score')
    def adjust_confidence_by_latency(cls, v, values):
        """Penalize confidence based on latency."""
        if 'latency_ms' in values and values['latency_ms'] > 1000:
            # Severe penalty for >1s latency
            return max(0.1, v * 0.5)
        return v
    
    def calculate_weighted_value(self) -> float:
        """Confidence-weighted USD value for aggregation."""
        return self.value_usd * self.confidence_score


class AtomicSnapshot(BaseModel):
    """
    Bundle of AssetSnapshots with shared timestamp and integrity metrics.
    Represents a complete cross-source observation moment.
    """
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    assets: List[AssetSnapshot] = Field(default_factory=list)
    
    # Integrity Metrics
    temporal_integrity_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="How close in time all sources were (1.0 = perfect)"
    )
    source_coverage: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Percentage of configured sources that responded"
    )
    
    @validator('assets')
    def validate_unique_assets(cls, v):
        """Ensure no duplicate asset-source combinations."""
        keys = [(a.source, a.asset_id) for a in v]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate asset-source combination")
        return v
    
    def calculate_total_value(self) -> float:
        """Sum of confidence-weighted values across all assets."""
        return sum(asset.calculate_weighted_value() for asset in self.assets)
    
    def calculate_risk_exposure(self) -> Dict[str, float]:
        """Percentage allocation by risk class."""
        if not self.assets:
            return {}
        
        total = self.calculate_total_value()
        exposure = {}
        for risk_class in AssetRiskClass:
            class_assets = [a for a in self.assets if a.risk_class == risk_class]
            class_value = sum(a.calculate_weighted_value() for a in class_assets)
            exposure[risk_class.value] = class_value / total if total > 0 else 0.0
        
        return exposure


class CapitalState(BaseModel):
    """
    Derived economic perception with momentum and anomaly detection.
    This is the 'neuron's output' - not raw data, but processed intelligence.
    """
    # Core Metrics
    timestamp: datetime
    total_net_worth_usd: float = Field(..., ge=0)
    
    # Momentum & Acceleration
    worth_momentum_1h: float = Field(
        default=0.0,
        description="USD/hour change (positive = growing)"
    )
    worth_acceleration_24h: float = Field(
        default=0.0,
        description="USD/hour² change (positive = accelerating)"
    )
    
    # Risk Analysis
    risk_exposure: Dict[str, float] = Field(
        default_factory=dict,
        description="Percentage allocation by risk class"
    )
    
    # Anomaly Detection
    anomaly_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="0-100 anomaly detection score"
    )
    anomaly_reasons: List[str] = Field(
        default_factory=list,
        description="Specific triggers for anomaly score"
    )
    
    # Quality Metrics
    confidence_weighted_value: float = Field(..., ge=0)
    data_quality_index: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Aggregate confidence of all sources"
    )
    
    # Volatility Profile
    volatility_profile: Dict[str, float] = Field(
        default_factory=dict,
        description="Rolling volatility by risk class (0-1)"
    )
    
    model_config = ConfigDict(validate_assignment=True)
    
    @validator('risk_exposure')
    def validate_risk_exposure_sum(cls, v):
        """Ensure risk exposures sum to ~1.0 (allow floating point error)."""
        if v:
            total = sum(v.values())
            if abs(total - 1.0) > 0.01:  # 1% tolerance
                raise ValueError(f"Risk exposures sum to {total:.4f}, not 1.0")
        return v