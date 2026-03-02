import re
from pathlib import Path
from typing import Iterator, TypedDict, cast

import matplotlib.pyplot as plt
import pandas as pd
import typer

from ai_assistant.commands import default_invoke_without_command

helptext = """
Get usage of Cursor.
"""

cmd = typer.Typer(help=helptext)


class UserStats(TypedDict):
    user: str
    daily_tokens: list["DailyTokensRow"]
    model_tokens: list["ModelTokensRow"]
    model_cost: list["ModelCostRow"]
    daily_cost: list["DailyCostRow"]


class PreparedData(TypedDict):
    rows: list["PreparedUsageRow"]


class PreparedUsageRow(TypedDict):
    user: str
    day: str
    model: str
    total_tokens: int
    cost: float


class DailyTokensRow(TypedDict):
    day: str
    tokens: int


class ModelTokensRow(TypedDict):
    model: str
    tokens: int


class ModelCostRow(TypedDict):
    model: str
    cost: float


class DailyCostRow(TypedDict):
    day: str
    cost: float


class UsageStatsService:
    def __init__(self, data: pd.DataFrame):
        self.data = data

    @classmethod
    def from_csv(cls, csv_path: Path) -> "UsageStatsService":
        data = pd.read_csv(csv_path)
        prepared = cls._prepare_data(data)
        return cls(
            pd.DataFrame(
                [
                    {
                        "User": row["user"],
                        "Day": row["day"],
                        "Model": row["model"],
                        "Total Tokens": row["total_tokens"],
                        "Cost": row["cost"],
                    }
                    for row in prepared["rows"]
                ],
                columns=["User", "Day", "Model", "Total Tokens", "Cost"],
            )
        )

    @staticmethod
    def _prepare_data(data: pd.DataFrame) -> PreparedData:
        # 过滤 Kind 为 On-Demand 的数据
        data = data[data["Kind"] == "On-Demand"].copy()

        # 统一类型，避免字符串导致聚合异常
        data["Total Tokens"] = pd.to_numeric(data["Total Tokens"], errors="coerce").fillna(0)
        data["Cost"] = pd.to_numeric(data["Cost"], errors="coerce").fillna(0)

        # Date 示例: "Mar 2, 02:13 PM"
        # 若解析失败则使用原始值，保证按天分组仍可进行
        parsed_date = pd.to_datetime(data["Date"], errors="coerce")
        data["Day"] = parsed_date.dt.strftime("%Y-%m-%d")
        data.loc[data["Day"].isna(), "Day"] = data.loc[data["Day"].isna(), "Date"]
        normalized = (
            data[["User", "Day", "Model", "Total Tokens", "Cost"]]
            .copy()
            .rename(
                columns={
                    "User": "user",
                    "Day": "day",
                    "Model": "model",
                    "Total Tokens": "total_tokens",
                    "Cost": "cost",
                }
            )
        )
        normalized["user"] = normalized["user"].astype(str)
        normalized["day"] = normalized["day"].astype(str)
        normalized["model"] = normalized["model"].astype(str)
        normalized["total_tokens"] = pd.to_numeric(normalized["total_tokens"], errors="coerce").fillna(0).astype(int)
        normalized["cost"] = pd.to_numeric(normalized["cost"], errors="coerce").fillna(0.0)
        return {"rows": cast(list[PreparedUsageRow], normalized.to_dict(orient="records"))}

    def iter_user_stats(self) -> Iterator[UserStats]:
        for user, user_df in self.data.groupby("User", sort=True):
            daily_tokens_df = user_df.groupby("Day", as_index=False)[["Total Tokens"]].sum().sort_values(by="Day").rename(columns={"Total Tokens": "Tokens"})
            model_tokens_df = user_df.groupby("Model", as_index=False)[["Total Tokens"]].sum().sort_values(by="Total Tokens", ascending=False).rename(columns={"Total Tokens": "Tokens"})
            model_cost_df = user_df.groupby("Model", as_index=False)[["Cost"]].sum().sort_values(by="Cost", ascending=False)
            daily_cost_df = user_df.groupby("Day", as_index=False)[["Cost"]].sum().sort_values(by="Day")
            yield {
                "user": str(user),
                "daily_tokens": [{"day": str(row.Day), "tokens": int(row.Tokens)} for row in daily_tokens_df.itertuples(index=False)],  # type: ignore[arg-type]
                "model_tokens": [{"model": str(row.Model), "tokens": int(row.Tokens)} for row in model_tokens_df.itertuples(index=False)],  # type: ignore[arg-type]
                "model_cost": [{"model": str(row.Model), "cost": float(row.Cost)} for row in model_cost_df.itertuples(index=False)],  # type: ignore[arg-type]
                "daily_cost": [{"day": str(row.Day), "cost": float(row.Cost)} for row in daily_cost_df.itertuples(index=False)],  # type: ignore[arg-type]
            }


class UsageChartRenderer:
    def __init__(self, chart_dir: Path):
        self.chart_dir = chart_dir

    @staticmethod
    def _safe_user(user: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", user).strip("._") or "user"

    def render_user_summary(self, user: str, stats: UserStats) -> Path:
        daily_cost = stats["daily_cost"]
        model_cost = stats["model_cost"]
        model_tokens = stats["model_tokens"]

        summary_path = self.chart_dir / f"{self._safe_user(user)}_usage_summary.png"

        fig, axes = plt.subplots(3, 1, figsize=(12, 14), height_ratios=[1.2, 1, 1])
        fig.suptitle(f"Usage Summary - {user}")
        ax_daily, ax_model_cost, ax_model_tokens = axes

        ax_daily.plot([row["day"] for row in daily_cost], [row["cost"] for row in daily_cost], marker="o")
        ax_daily.set_title("Daily Cost")
        ax_daily.set_xlabel("Day")
        ax_daily.set_ylabel("Cost")
        ax_daily.tick_params(axis="x", rotation=45)
        ax_daily.grid(alpha=0.25)

        ax_model_cost.barh([row["model"] for row in model_cost], [row["cost"] for row in model_cost])
        ax_model_cost.invert_yaxis()
        ax_model_cost.set_title("Cost by Model")
        ax_model_cost.set_xlabel("Cost")
        ax_model_cost.set_ylabel("Model")
        for i, row in enumerate(model_cost):
            cost = row["cost"]
            ax_model_cost.text(cost, i, f" {cost:.2f}", va="center")

        ax_model_tokens.barh([row["model"] for row in model_tokens], [row["tokens"] for row in model_tokens])
        ax_model_tokens.invert_yaxis()
        ax_model_tokens.set_title("Tokens by Model")
        ax_model_tokens.set_xlabel("Tokens")
        ax_model_tokens.set_ylabel("Model")
        for i, token_row in enumerate(model_tokens):
            tokens = token_row["tokens"]
            ax_model_tokens.text(tokens, i, f" {int(tokens):,}", va="center")

        plt.tight_layout(rect=(0, 0, 1, 0.97))
        plt.savefig(summary_path, dpi=150)
        plt.close()
        return summary_path


def add_default_invoke():
    for _cmd in (cmd,):
        _cmd.callback(invoke_without_command=True)(default_invoke_without_command)


add_default_invoke()


@cmd.command()
def get_usage(
    csv_path: Path = typer.Argument(..., help="CSV 文件路径"),
):
    """
    Excel 结构:
        Date: Mar 2, 02:13 PM
        User: abc@example.com
        Kind: On-Demand
        Model: claude-4.6-opus-high-thinking
        Total Tokens: Tokens
        Cost: 0.15
    """
    csv_path = csv_path.expanduser()
    chart_dir = csv_path.parent / "usage_charts"
    chart_dir.mkdir(parents=True, exist_ok=True)
    stats_service = UsageStatsService.from_csv(csv_path)
    chart_renderer = UsageChartRenderer(chart_dir)

    for stats in stats_service.iter_user_stats():
        user = stats["user"]
        summary_path = chart_renderer.render_user_summary(user, stats)
        typer.echo(f"\n[图表已保存] {summary_path}")

    typer.echo(f"\n所有图表目录: {chart_dir}")


if __name__ == "__main__":
    cmd()
