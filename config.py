"""
Configuration manager for Module 0. Centralizes environment variables,
API keys, and system constants with validation.
"""
import os
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

import structlog
from pydantic import BaseSettings, Field, validator

logger = structlog.get_logger()


class RiskClass(str, Enum):
    """Asset risk classification for portfolio analysis."""
    STABLE = "stable"  # USDC, USDT, DAI
    BLUE_CHIP = "blue_chip"  # BTC, ETH
    ALT = "alt"  # Top 100 tokens
    MEME = "meme"  # Meme/shitcoins
    DERIVATIVE = "derivative"  # Leveraged positions, options
    ILLIQUID = "illiquid"  # Locked/staked assets


class OracleSource(str, Enum):
    """Price oracle sources with reliability rankings."""
    COINGECKO = "coingecko"
    CHAINLINK = "chainlink"
    UNISWAP_V3 = "uniswap_v3"
    BINANCE = "binance"
    MANUAL = "manual"  # Fallback with manual verification


class SystemConfig(BaseSettings):
    """Validated system configuration from environment variables."""
    
    # Firebase Configuration (CRITICAL - Active Memory)
    FIREBASE_CREDENTIALS_PATH: str = Field(
        default="credentials/firebase-service-account.json",
        description="Path to Firebase service account JSON"
    )
    FIRESTORE_COLLECTION_RAW: str = "raw_snapshots"
    FIRESTORE_COLLECTION_STATES: str = "capital_states"
    FIRESTORE_COLLECTION_BASELINES: str = "baselines"
    
    # Snapshot Configuration
    SNAPSHOT_INTERVAL_SECONDS: int = Field(
        default=300,  # 5 minutes
        ge=30,  # Minimum 30 seconds to avoid rate limits
        le=3600  # Maximum 1 hour
    )
    MAX_SNAPSHOT_LATENCY_MS: int = 1000  # Discard sources >1s latency
    MIN_CONFIDENCE_THRESHOLD: float = 0.3  # Discard low-confidence data
    
    # Wallet & Exchange Configuration
    EVM_RPC_ENDPOINTS: List[str] = Field(
        default=[
            "https://eth-mainnet.g.alchemy.com/v2/demo",
            "https://rpc.ankr.com/eth"
        ]
    )
    SOLANA_RPC_ENDPOINT: str = "https://api.mainnet-beta.solana.com"
    
    # API Keys (loaded from .env)
    COINGECKO_API_KEY: Optional[str] = None
    ALCHAMY_API_KEY: Optional[str] = None
    BINANCE_API_KEY: Optional[str] = None
    BINANCE_SECRET_KEY: Optional[str] = None
    
    # Risk Management
    VOLATILITY_WINDOW_HOURS: int = 24
    ANOMALY_DETECTION_WINDOW: int = 168  # 7 days in hours
    MOMENTUM_CALCULATION_WINDOW: int = 12  # Data points for 1H momentum
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@dataclass
class SourceConfig:
    """Per-source configuration with reliability scoring."""
    name: str
    weight: float  # 0-1 importance in total calculation
    timeout_seconds: int
    retry_attempts: int
    reliability_score: float  # Historical success rate
    oracle_priority: List[OracleSource]  # Price source fallback chain


# Source configurations
SOURCE_CONFIGS: Dict[str, SourceConfig] = {
    "binance_api": SourceConfig(
        name="binance_api",
        weight=0.9,
        timeout_seconds=5,
        retry_attempts=2,
        reliability_score=0.95,
        oracle_priority=[OracleSource.BINANCE, OracleSource.COINGECKO]
    ),
    "ethereum_wallet": SourceConfig(
        name="ethereum_wallet",
        weight=0.8,
        timeout_seconds=10,
        retry_attempts=3,
        reliability_score=0.85,
        oracle_priority=[OracleSource.CHAINLINK, OracleSource.UNISWAP_V3, OracleSource.COINGECKO]
    ),
    "solana_wallet": SourceConfig(
        name="solana_wallet",
        weight=0.7,
        timeout_seconds=8,
        retry_attempts=3,
        reliability_score=0.75,
        oracle_priority=[OracleSource.COINGECKO, OracleSource.MANUAL]
    )
}


def load_config() -> SystemConfig:
    """Load and validate system configuration."""
    try:
        config = SystemConfig()
        logger.info(
            "config_loaded",
            snapshot_interval=config.SNAPSHOT_INTERVAL_SECONDS,
            firebase_collection=config.FIRESTORE_COLLECTION_RAW,
            sources_configured=list(SOURCE_CONFIGS.keys())
        )
        return config
    except Exception as e:
        logger.error("config_load_failed", error=str(e))
        # Fallback to defaults for resilience
        return SystemConfig()