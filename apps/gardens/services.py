"""萎凋在岗容量计数。

改态校验（Trough.clean）与茶园列表展示共用本模块的计数函数，
保证「上限」与「当前萎凋中数」全站同一口径：

- 计数：该园当前状态为「萎凋中」的槽数（装叶中、可下槽不计）。
- 上限：该园当日（服务器本地日期）最近更新的一张值班卡的 maxOnDuty；
  从未编辑过时即当日最新创建的一张。
"""

from dataclasses import dataclass
from datetime import date
from typing import Optional

from django.utils import timezone

from .models import Garden, Trough, WitherDutyCard


@dataclass(frozen=True)
class WitherCapacity:
    """某园某日的在岗容量快照。"""

    garden: Garden
    on_date: date
    card: Optional[WitherDutyCard]
    count: int

    @property
    def limit(self):
        """当日上限；无值班卡时为 None。"""
        return self.card.maxOnDuty if self.card else None

    @property
    def full(self):
        """有卡且当前萎凋中数已达上限。"""
        return self.card is not None and self.count >= self.card.maxOnDuty


def latest_duty_card(garden, on_date=None):
    """该园当日最近更新（其次最新创建）的一张值班卡。"""
    if on_date is None:
        on_date = timezone.localdate()
    return (
        WitherDutyCard.objects.filter(garden=garden, dutyDate=on_date)
        .order_by("-updatedAt", "-id")
        .first()
    )


def withering_count(garden):
    """该园当前状态为「萎凋中」的槽数。"""
    return Trough.objects.filter(
        garden=garden, status=Trough.STATUS_WITHERING
    ).count()


def wither_capacity(garden, on_date=None):
    """汇总某园某日容量：最新值班卡 + 当前萎凋中数。"""
    if on_date is None:
        on_date = timezone.localdate()
    return WitherCapacity(
        garden=garden,
        on_date=on_date,
        card=latest_duty_card(garden, on_date),
        count=withering_count(garden),
    )


def wither_capacity_error(garden, on_date=None):
    """改入萎凋中前的校验：无卡或已达上限时返回中文错误，否则 None。"""
    cap = wither_capacity(garden, on_date)
    if cap.card is None:
        return (
            f"当日无萎凋值班卡：请先在「萎凋值班」为 {cap.garden.name} "
            f"建立 {cap.on_date:%Y-%m-%d} 的值班卡，再改入萎凋中。"
        )
    if cap.full:
        return (
            f"已达当日在岗上限：{cap.garden.name} 当前萎凋中 {cap.count} 槽，"
            f"当日最新值班卡（{cap.card.shiftName}）上限 {cap.card.maxOnDuty} 槽，"
            "不能再改入萎凋中。"
        )
    return None
