"""Reserved interface for a future portfolio analysis service.

V0.1 intentionally contains no model calls and generates no investment advice.
"""

from typing import Any


class AIPortfolioService:
    def analyze(self, portfolio_context: dict[str, Any]) -> None:
        raise NotImplementedError("AI 投资组合分析即将推出")
