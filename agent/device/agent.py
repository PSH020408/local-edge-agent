"""Device agent: question → route → measure → diagnose → answer.

battery:     a 2-second capture of the fast sources (no chip readings), the macOS battery profile,
             the usual battery power from the store when there is history.
performance: an n-second capture with powermetrics (default 10 s), the energy ranking (top),
             storage space and health; "can I run ...?" also gets an admission decision.

Every stage is timed, so the budgets (quick answer under 3 s, diagnosis n + 5 s) are measured.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import answer as writer
from .capture import Capture, capture
from .diagnosis import BUS_QUESTION, TRANSFER_QUESTION, Report, battery_report, job_from_question, performance_report, work_from_question
from .readings import by_name
from .router import Route, route
from .sources import battery, load, memory, models, storage
from . import network


@dataclass
class DeviceResult:
    question: str
    route: Route
    report: Report | None = None
    answer: str = ""
    method: str = ""
    unsupported: list[str] = field(default_factory=list)
    rejected: str = ""        # the model's first answer, when it was not used
    rejected_reason: str = ""
    timings: dict = field(default_factory=dict)
    readings: dict = field(default_factory=dict)  # name -> (value, unit, quality), for the run report


class DeviceAgent:
    def __init__(self, shell, writer_llm=None, router_llm=None, store=None, capture_seconds: int = 10,
                 battery_seconds: int = 2, sleep=time.sleep, on_event=None, bench_folder=None) -> None:
        self.shell, self.writer_llm, self.router_llm, self.store = shell, writer_llm, router_llm, store
        self.bench_folder = bench_folder  # where the transfer-speed check writes its test file and keeps the normal
        self.capture_seconds, self.battery_seconds, self.sleep = capture_seconds, battery_seconds, sleep
        self.on_event = on_event or (lambda message: None)

    def run(self, question: str) -> str | None:
        """Answer for a device question; None when the question is not about the device."""
        result = self.diagnose(question)
        return result.answer if result.route.topic else None

    def diagnose(self, question: str, topic: str | None = None) -> DeviceResult:
        started = time.perf_counter()
        chosen = Route(topic, "given", {}, 0.0) if topic else route(question, self.router_llm)
        result = DeviceResult(question, chosen, timings={"route": round(chosen.seconds, 4)})
        if not chosen.topic:
            return result
        self.on_event(f"device: {chosen.topic} ({chosen.method})")
        measure_started = time.perf_counter()
        if chosen.topic == "network":
            self.on_event("device: measuring the Wi-Fi link and the path to the internet")
            measured = network.measure(self.shell, self._wifi_helper(), question)
            result.report = network.report(measured, question, network.baseline_from_store(self.store))
            result.timings["measure"] = round(time.perf_counter() - measure_started, 3)
            result.readings = {"link samples": (len(measured.link), "", "ok"), "router": (measured.router, "", "ok"),
                               "internet": (measured.internet, "", "ok"), "awdl": (measured.awdl, "", "ok"),
                               "dns_ms": (measured.dns_ms, "", "ok"), "driver": (measured.driver, "", "ok"),
                               "throughput": (measured.throughput, "", "ok")}
            return self._write(result, question, started)
        if chosen.topic == "battery":
            view = capture(self.shell, seconds=self.battery_seconds, with_chip=False, sleep=self.sleep)
            profile = {r.name: r.value for r in battery.read_profile(self.shell) if r.ok}
            baseline = self._usual_battery_power()
            top = self._top() if view.value("power.source") == "Battery" else []
            result.report = battery_report(view, profile, baseline, top, question)
            extra = profile
        else:
            view = capture(self.shell, seconds=self.capture_seconds, with_chip=True, sleep=self.sleep)
            disk = {r.name: r.value for r in storage.read(self.shell) if r.ok}
            _, held = models.read(self.shell)
            measured = None
            if self.bench_folder is not None and re.search(TRANSFER_QUESTION, question, re.I):
                self.on_event("device: measuring transfer speeds (about 5 s)")
                from . import bench
                on_adapter = view.value("power.source") != "Battery"
                measured = bench.run(Path(self.bench_folder) / "bench", Path(self.bench_folder) / "bench_normal.json", on_adapter)
            processes = self.shell.run("ps_cpu")
            total = view.value("memory.total")
            apps = memory.parse_apps(processes.text, total) if processes.ok and total else []
            ports = storage.parse_ports(self.shell.run("buses").text) if re.search(BUS_QUESTION, question, re.I) else None
            work = work_from_question(question)  # "can I edit 4K video now?" before "can I run a model job?"
            job = None if work else job_from_question(question)
            result.report = performance_report(view, disk, self._top(), job, held, measured, question, apps, ports, work)
            extra = disk
        result.timings["measure"] = round(time.perf_counter() - measure_started, 3)
        result.readings = self._snapshot(view, extra)
        return self._write(result, question, started)

    def _write(self, result: DeviceResult, question: str, started: float) -> DeviceResult:
        self.on_event(f"device: findings {', '.join(result.report.codes())}")
        written = writer.write(result.report, question, self.writer_llm)
        result.answer, result.method, result.unsupported = written.text, written.method, written.unsupported
        result.rejected, result.rejected_reason = written.first, written.reason
        result.timings["answer"] = round(written.seconds, 3)
        result.timings["total"] = round(time.perf_counter() - started, 3)
        return result

    def _wifi_helper(self) -> str:
        """The compiled CoreWLAN helper (logs/bin/wifi_helper), built on first use; a fixture shell ignores the path."""
        if self.bench_folder is None:
            return "wifi_helper"
        try:
            from .sources import wifi
            return str(wifi.helper(Path(self.bench_folder).parent))
        except Exception as exc:  # noqa: BLE001 - no Swift compiler: the link readings stay empty
            self.on_event(f"device: Wi-Fi helper unavailable ({exc})")
            return "wifi_helper"

    def _top(self) -> list[tuple[str, float]]:
        values = by_name(load.read_top(self.shell))
        out = []
        for rank in (1, 2, 3):
            name, impact = values.get(f"process.energy{rank}_name"), values.get(f"process.energy{rank}_impact")
            if name and name.ok and impact and impact.ok:
                out.append((name.value, impact.value))
        return out

    def _usual_battery_power(self) -> float | None:
        """Mean battery power on battery over the last 7 days of the store, if there is enough history."""
        if self.store is None:
            return None
        volts = dict(self.store.series("battery.voltage", 7 * 24 * 60))
        amps = self.store.series("battery.current", 7 * 24 * 60)
        powers = [abs(volts[t] * a) for t, a in amps if a < -0.05 and t in volts]
        return sum(powers) / len(powers) if len(powers) >= 30 else None

    @staticmethod
    def _snapshot(view: Capture, extra: dict) -> dict:
        snap = {name: (r.value, r.unit, r.quality) for name, r in sorted(view.latest.items())}
        snap.update({name: (value, "", "ok") for name, value in extra.items()})
        return snap
