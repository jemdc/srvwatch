"""Tests for agent/main.py metric collection."""
import sys
from unittest.mock import MagicMock, patch
import pytest

# Ensure we can import the module (it's in the parent directory)
sys.path.insert(0, '..')
from main import collect_cpu, collect_memory, collect_gpus


class TestCollectCPU:
    @patch('main.psutil')
    def test_collect_cpu_returns_valid_data(self, mock_psutil):
        # Arrange
        mock_psutil.cpu_percent.return_value = 45.5
        mock_psutil.cpu_count.return_value = 8
        mock_psutil.cpu_freq.return_value = MagicMock(current=3.5)

        # Act
        result = collect_cpu()

        # Assert
        assert result.utilization_pct == 45.5
        assert result.core_count_logical == 8
        assert result.core_count_physical == 8
        assert result.frequency_mhz == 3.5


class TestCollectMemory:
    @patch('main.psutil')
    def test_collect_memory_returns_valid_data(self, mock_psutil):
        # Arrange
        mock_mem = MagicMock()
        mock_mem.total = 16 * 1024**3
        mock_mem.available = 8 * 1024**3
        mock_mem.percent = 50.0
        mock_psutil.virtual_memory.return_value = mock_mem

        mock_swap = MagicMock()
        mock_swap.total = 0
        mock_swap.used = 0
        mock_psutil.swap_memory.return_value = mock_swap

        # Act
        result = collect_memory()

        # Assert
        assert result.total_mb == 16 * 1024
        assert result.used_pct == 50.0
        assert result.swap_used_mb == 0
        assert result.swap_total_mb == 0


class TestCollectGPUs:
    @patch('main._collect_nvidia_gpus')
    @patch('main._collect_amd_gpus')
    def test_collect_gpus_sorts_by_pci(self, mock_amd, mock_nvidia):
        # Arrange
        class FakeGPU:
            def __init__(self, idx, pci):
                self.index = idx
                self.pci_bus_id = pci
                self.name = f"GPU {idx}"
                self.vram_total_mb = 8000
                self.vram_used_mb = 100
                self.vram_pct = 1.25
                self.power_draw_w = 50
                self.temperature_c = 40
                self.gpu_utilization_pct = 10.0
                self.vendor = "nvidia"
                self.power_limit_w = None

        mock_nvidia.return_value = [FakeGPU(0, "0000:01:00.0")]
        mock_amd.return_value = [FakeGPU(1, "0000:02:00.0")]

        # Act
        result = collect_gpus()

        # Assert
        assert len(result) == 2
        assert result[0].pci_bus_id == "0000:01:00.0"
        assert result[1].pci_bus_id == "0000:02:00.0"
        assert result[0].index == 0
        assert result[1].index == 1
