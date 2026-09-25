from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Garden(models.Model):
    name = models.CharField("茶园名称", max_length=120)
    altitudeBand = models.CharField("海拔带", max_length=60)
    notes = models.TextField("备注", blank=True, default="")

    class Meta:
        ordering = ["name"]
        verbose_name = "茶园"
        verbose_name_plural = "茶园"

    def __str__(self):
        return self.name

    def today_duty_card(self):
        """该园今日最新值班卡（可能为 None），与改态校验共用取卡口径。"""
        return latest_duty_card(self, timezone.localdate())

    def withering_now(self):
        """该园当前萎凋中槽数，与改态校验共用计数口径。"""
        return count_withering(self)


class WitherDutyCard(models.Model):
    """萎凋值班卡：同一茶园同日同班次唯一，限定当日在岗（萎凋中）槽数上限。"""

    garden = models.ForeignKey(
        Garden,
        on_delete=models.CASCADE,
        related_name="duty_cards",
        verbose_name="茶园",
    )
    dutyDate = models.DateField("值班日")
    shiftName = models.CharField("班次名", max_length=40)
    maxOnDuty = models.PositiveIntegerField("计划在岗槽数上限")
    supervisor = models.CharField("值班主管名", max_length=60)
    createdAt = models.DateTimeField("创建时间", auto_now_add=True)
    updatedAt = models.DateTimeField("更新时间", auto_now=True)

    class Meta:
        ordering = ["-dutyDate", "garden__name", "shiftName"]
        verbose_name = "萎凋值班卡"
        verbose_name_plural = "萎凋值班卡"
        constraints = [
            models.UniqueConstraint(
                fields=["garden", "dutyDate", "shiftName"],
                name="uniq_duty_card_per_garden_day_shift",
            ),
        ]

    def __str__(self):
        return f"{self.garden.name} {self.dutyDate:%Y-%m-%d} {self.shiftName}"

    def withering_now(self):
        """该卡茶园当前萎凋中槽数，与改态校验共用计数口径。"""
        return count_withering(self.garden)


# ---- 萎凋在岗计数口径（改态校验与列表展示共用） ----


def count_withering(garden):
    """计数口径：该园当前状态为「萎凋中」的槽数（实时状态，不分班次/批次）。"""
    return Trough.objects.filter(
        garden=garden, status=Trough.STATUS_WITHERING
    ).count()


def latest_duty_card(garden, on_date):
    """该园当日最新值班卡：同日多张班次卡时取最近更新的一张。"""
    return (
        WitherDutyCard.objects.filter(garden=garden, dutyDate=on_date)
        .order_by("-updatedAt", "-id")
        .first()
    )


class Trough(models.Model):
    STATUS_LOADING = "loading"
    STATUS_WITHERING = "withering"
    STATUS_READY = "ready"
    STATUS_CHOICES = [
        (STATUS_LOADING, "装叶中"),
        (STATUS_WITHERING, "萎凋中"),
        (STATUS_READY, "可下槽"),
    ]

    garden = models.ForeignKey(
        Garden,
        on_delete=models.CASCADE,
        related_name="troughs",
        verbose_name="茶园",
    )
    troughCode = models.CharField("槽位编号", max_length=40)
    cultivar = models.CharField("茶树品种", max_length=80)
    loadKg = models.DecimalField("装叶量(kg)", max_digits=10, decimal_places=2)
    status = models.CharField(
        "状态",
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_LOADING,
    )

    class Meta:
        ordering = ["garden__name", "troughCode"]
        verbose_name = "萎凋槽"
        verbose_name_plural = "萎凋槽"
        constraints = [
            models.UniqueConstraint(
                fields=["garden", "troughCode"],
                name="uniq_trough_code_per_garden",
            ),
        ]

    def __str__(self):
        return f"{self.garden.name}-{self.troughCode}"

    def latest_batch(self):
        return self.batches.order_by("-startedAt", "-id").first()

    def clean(self):
        super().clean()
        self._check_ready_rule()
        self._check_withering_capacity()

    def _check_ready_rule(self):
        if self.status != self.STATUS_READY:
            return
        latest = None
        if self.pk:
            latest = (
                WitherBatch.objects.filter(trough_id=self.pk)
                .order_by("-startedAt", "-id")
                .first()
            )
        if latest is None or latest.actualMoisture is None or latest.actualMoisture > 40:
            raise ValidationError(
                {
                    "status": "无法设为可下槽：最新萎凋批次的实测含水率为空或高于 40%。"
                }
            )

    def _check_withering_capacity(self):
        """改入「萎凋中」（装叶中→萎凋中、可下槽→萎凋中、新建即萎凋中）时，
        校验该园当日值班卡上限；已处萎凋中的槽重复保存不占新名额。"""
        if self.status != self.STATUS_WITHERING:
            return
        if not self.garden_id:
            return
        if self.pk:
            old_status = (
                Trough.objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )
            if old_status == self.STATUS_WITHERING:
                return
        today = timezone.localdate()
        card = latest_duty_card(self.garden, today)
        if card is None:
            raise ValidationError(
                {
                    "status": (
                        f"无法设为萎凋中：{self.garden.name} 今日"
                        f"（{today:%Y-%m-%d}）尚未建立萎凋值班卡，请先在「萎凋值班」中建卡。"
                    )
                }
            )
        current = count_withering(self.garden)
        if current >= card.maxOnDuty:
            raise ValidationError(
                {
                    "status": (
                        f"无法设为萎凋中：{self.garden.name} 当前萎凋中 {current} 槽，"
                        f"已达今日值班卡上限 {card.maxOnDuty}"
                        f"（{card.shiftName}·{card.supervisor}）。"
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class WitherBatch(models.Model):
    trough = models.ForeignKey(
        Trough,
        on_delete=models.CASCADE,
        related_name="batches",
        verbose_name="萎凋槽",
    )
    startedAt = models.DateTimeField("开始时间")
    targetMoisture = models.DecimalField(
        "目标含水率(%)", max_digits=5, decimal_places=2
    )
    actualMoisture = models.DecimalField(
        "实测含水率(%)",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    rollGrade = models.CharField("揉捻等级", max_length=40)

    class Meta:
        ordering = ["-startedAt", "-id"]
        verbose_name = "萎凋批次"
        verbose_name_plural = "萎凋批次"

    def __str__(self):
        return f"{self.trough} @ {self.startedAt:%Y-%m-%d %H:%M}"
