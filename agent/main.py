"""
SRVWatch Agent — lightweight metrics endpoint for Ubuntu servers.
Exposes CPU, memory, and GPU (NVIDIA + AMD) metrics over HTTP.

Endpoints:
  GET /         → service info
  GET /health   → liveness probe (no auth)
  GET /metrics  → full metrics snapshot
  GET /docs     → Swagger UI
"""

import os
import time
import platform
import subprocess
import warnings
from typing import Optional

import psutil
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Config (env vars) ─────────────────────────────────────────────────────────
AGENT_SECRET  = os.getenv("SRVWATCH_SECRET", "")
AGENT_LABEL   = os.getenv("SRVWATCH_LABEL", platform.node())
AGENT_VERSION = "1.0.0"

# ── Pydantic models ───────────────────────────────────────────────────────────

class GpuMetrics(BaseModel):
    index: int
    name: str
    vendor: str                     # "nvidia" | "amd"
    vram_used_mb: float
    vram_total_mb: float
    vram_pct: float
    power_draw_w: Optional[float]
    power_limit_w: Optional[float]
    temperature_c: Optional[float]
    gpu_utilization_pct: Optional[float]

class CpuMetrics(BaseModel):
    utilization_pct: float
    core_count_logical: int
    core_count_physical: int
    frequency_mhz: Optional[float]
    temperature_c: Optional[float]

class MemoryMetrics(BaseModel):
    used_mb: float
    total_mb: float
    used_pct: float
    swap_used_mb: float
    swap_total_mb: float

class MetricsResponse(BaseModel):
    agent_label: str
    agent_version: str
    timestamp: float
    uptime_seconds: float
    cpu: CpuMetrics
    memory: MemoryMetrics
    gpus: list[GpuMetrics]

# ── NVIDIA GPU collection ─────────────────────────────────────────────────────

def _collect_nvidia_gpus() -> list[GpuMetrics]:
    """Query NVIDIA GPUs via pynvml (nvidia-ml-py package)."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import pynvml
        pynvml.nvmlInit()
    except Exception:
        return []

    gpus: list[GpuMetrics] = []
    try:
        count = pynvml.nvmlDeviceGetCount()
        for i in range(count):
            h    = pynvml.nvmlDeviceGetHandleByIndex(i)
            name = pynvml.nvmlDeviceGetName(h)
            if isinstance(name, bytes):
                name = name.decode()

            mem        = pynvml.nvmlDeviceGetMemoryInfo(h)
            vram_used  = mem.used  / 1024 / 1024
            vram_total = mem.total / 1024 / 1024
            vram_pct   = (vram_used / vram_total * 100) if vram_total else 0.0

            def nvml_get(fn, *args, default=None):
                try:
                    return fn(h, *args)
                except pynvml.NVMLError:
                    return default

            power_raw   = nvml_get(pynvml.nvmlDeviceGetPowerUsage)
            plimit_raw  = nvml_get(pynvml.nvmlDeviceGetEnforcedPowerLimit)
            temp        = nvml_get(pynvml.nvmlDeviceGetTemperature, pynvml.NVML_TEMPERATURE_GPU)
            util_obj    = nvml_get(pynvml.nvmlDeviceGetUtilizationRates)

            gpus.append(GpuMetrics(
                index=i,
                name=name,
                vendor="nvidia",
                vram_used_mb=round(vram_used, 1),
                vram_total_mb=round(vram_total, 1),
                vram_pct=round(vram_pct, 1),
                power_draw_w=round(power_raw / 1000, 1) if power_raw is not None else None,
                power_limit_w=round(plimit_raw / 1000, 1) if plimit_raw is not None else None,
                temperature_c=float(temp) if temp is not None else None,
                gpu_utilization_pct=float(util_obj.gpu) if util_obj is not None else None,
            ))
    finally:
        try:
            pynvml.nvmlShutdown()
        except Exception:
            pass

    return gpus

# ── AMD GPU collection ────────────────────────────────────────────────────────

def _rocm_smi(*args) -> Optional[str]:
    try:
        r = subprocess.run(["rocm-smi", *args], capture_output=True, text=True, timeout=5)
        return r.stdout if r.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _collect_amd_via_rocm() -> list[GpuMetrics]:
    """Query AMD GPUs via rocm-smi JSON (requires ROCm stack)."""
    out = _rocm_smi("--showmeminfo", "vram", "--showpower",
                    "--showtemp", "--showuse", "--json")
    if not out:
        return []
    try:
        import json
        data = json.loads(out)
        gpus = []
        for idx, (_, card) in enumerate(data.items()):
            if not isinstance(card, dict):
                continue

            name = card.get("Card Series") or card.get("Card Model") or f"AMD GPU {idx}"

            vram_used  = float(card.get("VRAM Total Used Memory (B)", 0)) / 1024 / 1024
            vram_total = float(card.get("VRAM Total Memory (B)", 1))      / 1024 / 1024
            vram_pct   = (vram_used / vram_total * 100) if vram_total else 0.0

            power_draw = None
            temp       = None
            util       = None

            for k, v in card.items():
                kl = k.lower()
                if power_draw is None and "power" in kl and "w" in kl:
                    try:
                        power_draw = float(v)
                    except (ValueError, TypeError):
                        pass
                if temp is None and "temperature" in kl and "edge" in kl:
                    try:
                        temp = float(str(v).replace("c", "").strip())
                    except (ValueError, TypeError):
                        pass
                if util is None and ("gpu use" in kl or "gpu activity" in kl):
                    try:
                        util = float(str(v).replace("%", "").strip())
                    except (ValueError, TypeError):
                        pass

            gpus.append(GpuMetrics(
                index=idx, name=name, vendor="amd",
                vram_used_mb=round(vram_used, 1),
                vram_total_mb=round(vram_total, 1),
                vram_pct=round(vram_pct, 1),
                power_draw_w=round(power_draw, 1) if power_draw is not None else None,
                power_limit_w=None,
                temperature_c=round(temp, 1) if temp is not None else None,
                gpu_utilization_pct=round(util, 1) if util is not None else None,
            ))
        return gpus
    except Exception:
        return []


def _collect_amd_via_sysfs() -> list[GpuMetrics]:
    """
    Query AMD GPUs via sysfs (no ROCm needed — works with amdgpu kernel driver).
    Reads /sys/class/drm/card*/device/ for vRAM, power, temperature, utilization.
    """
    drm_path = "/sys/class/drm"
    if not os.path.isdir(drm_path):
        return []

    gpus = []
    idx  = 0
    for card in sorted(os.listdir(drm_path)):
        if not card.startswith("card") or card.startswith("card-"):
            continue
        dev = os.path.join(drm_path, card, "device")
        vendor_f = os.path.join(dev, "vendor")
        if not os.path.isfile(vendor_f):
            continue
        try:
            if open(vendor_f).read().strip() != "0x1002":   # AMD PCI vendor
                continue
        except OSError:
            continue

        def read(rel, default=None):
            try:
                return open(os.path.join(dev, rel)).read().strip()
            except OSError:
                return default

        vram_used_b  = float(read("mem_info_vram_used",  "0"))
        vram_total_b = float(read("mem_info_vram_total", "0"))
        vram_used_mb  = vram_used_b  / 1024 / 1024
        vram_total_mb = vram_total_b / 1024 / 1024
        vram_pct = (vram_used_mb / vram_total_mb * 100) if vram_total_mb else 0.0

        # Power: hwmon/hwmon*/power1_average (µW → W)
        power_draw = None
        for hwmon in sorted(os.listdir(dev)) if os.path.isdir(dev) else []:
            if not hwmon.startswith("hwmon"):
                continue
            raw = read(f"{hwmon}/power1_average")
            if raw:
                try:
                    power_draw = float(raw) / 1_000_000
                    break
                except ValueError:
                    pass

        # Temperature: hwmon/hwmon*/temp1_input (m°C → °C)
        temp = None
        for hwmon in sorted(os.listdir(dev)) if os.path.isdir(dev) else []:
            if not hwmon.startswith("hwmon"):
                continue
            raw = read(f"{hwmon}/temp1_input")
            if raw:
                try:
                    temp = float(raw) / 1000
                    break
                except ValueError:
                    pass

        # GPU utilization
        util = None
        raw = read("gpu_busy_percent")
        if raw:
            try:
                util = float(raw)
            except ValueError:
                pass

        name = read("product_name") or f"AMD GPU {idx}"
        gpus.append(GpuMetrics(
            index=idx, name=name, vendor="amd",
            vram_used_mb=round(vram_used_mb, 1),
            vram_total_mb=round(vram_total_mb, 1),
            vram_pct=round(vram_pct, 1),
            power_draw_w=round(power_draw, 1) if power_draw is not None else None,
            power_limit_w=None,
            temperature_c=round(temp, 1) if temp is not None else None,
            gpu_utilization_pct=round(util, 1) if util is not None else None,
        ))
        idx += 1

    return gpus


def _collect_amd_gpus() -> list[GpuMetrics]:
    gpus = _collect_amd_via_rocm()
    return gpus if gpus else _collect_amd_via_sysfs()


def collect_gpus() -> list[GpuMetrics]:
    gpus = [*_collect_nvidia_gpus(), *_collect_amd_gpus()]
    for i, g in enumerate(gpus):
        g.index = i
    return gpus

# ── CPU / Memory ──────────────────────────────────────────────────────────────

def collect_cpu() -> CpuMetrics:
    freq = psutil.cpu_freq()
    temp = None
    try:
        for key in ("coretemp", "k10temp", "cpu_thermal", "acpitz"):
            s = psutil.sensors_temperatures().get(key, [])
            if s:
                temp = s[0].current
                break
    except (AttributeError, NotImplementedError):
        pass

    return CpuMetrics(
        utilization_pct=psutil.cpu_percent(interval=0.2),
        core_count_logical=psutil.cpu_count(logical=True),
        core_count_physical=psutil.cpu_count(logical=False) or 1,
        frequency_mhz=round(freq.current, 1) if freq else None,
        temperature_c=round(temp, 1) if temp is not None else None,
    )


def collect_memory() -> MemoryMetrics:
    vm   = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return MemoryMetrics(
        used_mb=round(vm.used    / 1024 / 1024, 1),
        total_mb=round(vm.total  / 1024 / 1024, 1),
        used_pct=vm.percent,
        swap_used_mb=round(swap.used  / 1024 / 1024, 1),
        swap_total_mb=round(swap.total / 1024 / 1024, 1),
    )

# ── FastAPI ───────────────────────────────────────────────────────────────────

app = FastAPI(title="SRVWatch Agent", version=AGENT_VERSION, redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])

_boot = time.time()


def _auth(secret: Optional[str]):
    if AGENT_SECRET and secret != AGENT_SECRET:
        raise HTTPException(401, "Invalid or missing X-SRVWatch-Secret header")


@app.get("/")
def root():
    return {"service": "srvwatch-agent", "version": AGENT_VERSION, "label": AGENT_LABEL}


@app.get("/health")
def health():
    return {"status": "ok", "uptime_seconds": round(time.time() - _boot, 1)}


@app.get("/metrics", response_model=MetricsResponse)
def metrics(x_srvwatch_secret: Optional[str] = Header(default=None)):
    _auth(x_srvwatch_secret)
    return MetricsResponse(
        agent_label=AGENT_LABEL,
        agent_version=AGENT_VERSION,
        timestamp=time.time(),
        uptime_seconds=round(time.time() - _boot, 1),
        cpu=collect_cpu(),
        memory=collect_memory(),
        gpus=collect_gpus(),
    )
