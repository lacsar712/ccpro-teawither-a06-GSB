from django.core.exceptions import ValidationError
from django.db import models


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


class WitherDutyCard(models.Model):
    """值班卡：限定同一时段同园在岗（萎凋中）槽数上限。"""

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
                name="uniq_duty_card_per_garden_date_shift",
            ),
        ]

    def __str__(self):
        return (
            f"{self.garden.name} {self.dutyDate:%Y-%m-%d} "
            f"{self.shiftName} 上限{self.maxOnDuty}"
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
        self._check_wither_capacity_rule()

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

    def _check_wither_capacity_rule(self):
        """改入萎凋中（装叶中→萎凋中、可下槽→萎凋中、新建即萎凋中）受当日值班卡上限约束。"""
        if self.status != self.STATUS_WITHERING or not self.garden_id:
            return
        previous = None
        if self.pk:
            previous = (
                Trough.objects.filter(pk=self.pk)
                .values_list("status", flat=True)
                .first()
            )
        if previous == self.STATUS_WITHERING:
            return  # 原本就是萎凋中，非新改入，不重复占额
        from .services import wither_capacity_error

        error = wither_capacity_error(self.garden)
        if error:
            raise ValidationError({"status": error})

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
