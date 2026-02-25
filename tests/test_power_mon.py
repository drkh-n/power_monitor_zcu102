import sys
import pytest
from pathlib import Path

# Add the 'src' directory to the Python path so pytest can find the package
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from power_monitor import PowerMonitor

# These tests are designed to be run directly on a ZCU102 board with PetaLinux 2022.2.
# They will fail on a standard PC because the /sys/class/hwmon paths will not exist
# or will not contain the expected INA226 sensor structures.

@pytest.fixture
def monitor():
    """Fixture to provide a clean PowerMonitor instance for each test."""
    return PowerMonitor(interval=0.1)

def test_initialization(monitor):
    """Test that PowerMonitor initializes correctly and finds rails."""
    assert monitor.interval == 0.1
    assert not monitor._stop
    assert len(monitor.samples) == 0
    
    # On a real ZCU102 board, there should be INA226 sensors discovered.
    # The exact number can vary depending on board configuration, but it should be > 0.
    assert len(monitor.rails) > 0, "No power rails found. Are you running this on a ZCU102 board?"

def test_sensor_paths(monitor):
    """Test that all discovered sensors have valid sysfs paths."""
    for rail_key, rail_info in monitor.rails.items():
        assert Path(rail_info["voltage_path"]).exists(), f"Voltage path missing for {rail_key}"
        assert Path(rail_info["current_path"]).exists(), f"Current path missing for {rail_key}"
        assert rail_key in PowerMonitor.RAIL_MAPPING.values(), f"Unknown rail found: {rail_key}"

def test_read_rail_power(monitor):
    """Test reading power from a single discovered rail."""
    if not monitor.rails:
        pytest.skip("No rails available to test.")
        
    # Get the first available rail
    rail_name = list(monitor.rails.keys())[0]
    power_w = monitor._read_rail_power(rail_name)
    
    assert isinstance(power_w, float)
    assert power_w >= 0.0, f"Power reading ({power_w}) cannot be negative"

def test_read_once(monitor):
    """Test aggregating power across all domains (PS, PL, MGT, Total)."""
    ps, pl, mgt, total = monitor._read_once(verbose=False)
    
    assert isinstance(ps, float)
    assert isinstance(pl, float)
    assert isinstance(mgt, float)
    assert isinstance(total, float)
    
    assert ps >= 0.0
    assert pl >= 0.0
    assert mgt >= 0.0
    assert total >= 0.0
    
    # Due to floating point math, we use pytest.approx for the sum check
    assert total == pytest.approx(ps + pl + mgt, rel=1e-5), "Total power does not match domain sums"

def test_background_monitoring(monitor):
    """Test starting, running, and stopping the background monitoring thread."""
    # Start thread
    assert monitor.start() is True
    assert monitor.thread.is_alive()
    
    # Let it run for a short duration
    import time
    time.sleep(0.5) 
    
    # Stop thread
    monitor.stop()
    assert not monitor.thread.is_alive()
    
    # Verify samples were collected (0.5s at 0.1s interval should yield ~4-5 samples)
    assert len(monitor.samples) > 0
    assert monitor.get_sample_count() == len(monitor.samples)
    
    # Validate sample structure (Timestamp, PS, PL, MGT, Total)
    sample = monitor.samples[0]
    assert len(sample) == 5
    assert all(isinstance(val, float) for val in sample)

def test_average_calculation(monitor):
    """Test the average power calculation logic over collected samples."""
    # Manually inject some known samples for consistent testing
    monitor.samples = [
        (100.0, 1.0, 2.0, 3.0, 6.0),
        (100.1, 1.5, 2.5, 3.5, 7.5),
        (100.2, 2.0, 3.0, 4.0, 9.0)
    ]
    
    avg_ps, avg_pl, avg_mgt, avg_total = monitor.average()
    
    assert avg_ps == 1.5
    assert avg_pl == 2.5
    assert avg_mgt == 3.5
    assert avg_total == 7.5

def test_save_samples(monitor, tmp_path):
    """Test saving collected samples to a CSV file."""
    # Inject samples
    monitor.samples = [(100.0, 1.1, 2.2, 3.3, 6.6)]
    
    output_file = tmp_path / "test_output.csv"
    monitor.save_samples(str(output_file))
    
    assert output_file.exists()
    content = output_file.read_text()
    
    # Check header
    assert "Timestamp,PS_Power_W,PL_Power_W,MGT_Power_W,Total_Power_W" in content
    # Check data row formatting (from the defined formatting rules in the module)
    assert "100.0000,1.100,2.200,3.300,6.600" in content
    
    # Test txt behavior too
    output_txt = tmp_path / "test_output.txt"
    monitor.save_samples(str(output_txt))
    assert output_txt.exists()
    content_txt = output_txt.read_text()
    assert "\t" in content_txt # TXT should use tab delimiter
