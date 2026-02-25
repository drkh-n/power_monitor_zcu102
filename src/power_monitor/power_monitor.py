import logging
from pathlib import Path
import time
import threading
import csv

class PowerMonitor:
    """
    Reads ZCU102 INA226 power rails via hwmon.
    Values returned in Watts.
    """

    # Component designator to rail name mapping
    RAIL_MAPPING = {
        # PS_PMBUS
        "ina226_u76": "VCCPSINTFP",
        "ina226_u77": "VCCPSINTLP",
        "ina226_u78": "VCCPSAUX",     # NOTE: Table shows u78 as VCCPSAUX, but old code had u78 as VCCINT. Going with Table.
        "ina226_u87": "VCCPSPLL",
        "ina226_u85": "MGTRAVCC",
        "ina226_u86": "MGTRAVTT",
        "ina226_u93": "VCCPSDDR",
        "ina226_u88": "VCCOPS",
        "ina226_u15": "VCCOPS3",
        "ina226_u92": "VCCPSDDRPL", # NOTE: ending in PL based on table
        
        # PL_PMBUS
        "ina226_u79": "VCCINT",
        "ina226_u81": "VCCBRAM",
        "ina226_u80": "VCCAUX",
        "ina226_u84": "VCC1V2",
        "ina226_u16": "VCC3V3",
        "ina226_u65": "VADJ_FMC",
        "ina226_u74": "MGTAVCC",
        "ina226_u75": "MGTAVTT",
    }

    def __init__(self, interval=1.0):
        self.interval = interval
        self.samples = []
        self._stop = False
        self.thread = None
        self.rails = self._find_rails()
        
        if len(self.rails) == 0:
            logging.error("No power rails found!")

    def _find_rails(self):
        """Find power rails by INA226 component designator."""
        rails = {}
        hwmon_base = Path("/sys/class/hwmon")
        
        if not hwmon_base.exists():
            logging.error("hwmon directory not found!")
            return rails
        
        for hwmon_dir in hwmon_base.iterdir():
            name_file = hwmon_dir / "name"
            voltage_file = hwmon_dir / "in1_input"
            current_file = hwmon_dir / "curr1_input"
            
            if not (name_file.exists() and voltage_file.exists() and current_file.exists()):
                continue
            
            try:
                sensor_name = name_file.read_text().strip()
                
                # Check if this sensor matches our mapping
                if sensor_name in self.RAIL_MAPPING:
                    rail_key = self.RAIL_MAPPING[sensor_name]
                    rails[rail_key] = {
                        "voltage_path": str(voltage_file),
                        "current_path": str(current_file),
                        "hwmon_dir": hwmon_dir.name,
                        "sensor_name": sensor_name
                    }
                    
            except Exception as e:
                logging.debug(f"Error reading {hwmon_dir.name}: {e}")
                continue
        
        return rails

    def list_hwmon_interfaces(self):
        """-l lists out the hwmon interfaces"""
        print("=== Available INA226 Power Sensors ===")
        hwmon_base = Path("/sys/class/hwmon")
        
        if not hwmon_base.exists():
            print("hwmon directory not found!")
            return

        for hwmon_dir in sorted(hwmon_base.iterdir()):
            name_file = hwmon_dir / "name"
            voltage_file = hwmon_dir / "in1_input"
            current_file = hwmon_dir / "curr1_input"
            
            if not (name_file.exists() and voltage_file.exists() and current_file.exists()):
                continue
            
            try:
                name = name_file.read_text().strip()
                if not name.startswith("ina226"):
                    continue
                    
                mapped = self.RAIL_MAPPING.get(name, "UNMAPPED")
                
                # Try to read voltage and current
                voltage_mv = float(voltage_file.read_text())
                current_ma = float(current_file.read_text())
                power_w = (voltage_mv * current_ma) / 1e6
                
                print(f"  {hwmon_dir.name}: {name:15s} -> {mapped:10s} ({power_w:.3f}W, {voltage_mv:.0f}mV, {current_ma:.0f}mA)")
                
            except Exception as e:
                print(f"Error reading {hwmon_dir.name}: {e}")

    def _read_rail_power(self, rail_name):
        """Helper to read voltage and current for a specific rail and compute power in Watts."""
        if rail_name not in self.rails:
            return 0.0
        try:
            with open(self.rails[rail_name]["voltage_path"]) as f:
                voltage_mv = float(f.read().strip())
            with open(self.rails[rail_name]["current_path"]) as f:
                current_ma = float(f.read().strip())
            return (voltage_mv * current_ma) / 1000000.0
        except (IOError, ValueError):
            return 0.0

    def _read_once(self, verbose=False):
        """Read power values for all domains."""
        ps_power = 0.0
        pl_power = 0.0
        mgt_power = 0.0

        # Read all rails power
        powers = {rail: self._read_rail_power(rail) for rail in self.RAIL_MAPPING.values()}

        if verbose:
            print("--- Rail Powers ---")
            for r, p in powers.items():
                print(f"  {r}: {p:.3f}W")

        # PS = VCCPSINTFP+VCCPSINTLP+VCCPSAUX+VCCPSPLL+ VCCPSDDR+VCCOPS+ VCCOPS3+ VCCPSDDRPL
        ps_power = (powers.get("VCCPSINTFP", 0) + powers.get("VCCPSINTLP", 0) + 
                    powers.get("VCCPSAUX", 0) + powers.get("VCCPSPLL", 0) + 
                    powers.get("VCCPSDDR", 0) + powers.get("VCCOPS", 0) + 
                    powers.get("VCCOPS3", 0) + powers.get("VCCPSDDRPL", 0))

        # PL = VCCINT+ VCCBRAM+ VCCAUX+ VCC1V2VCC3V3
        # NOTE: VCC3V3 is shared or listed in MGT in C code, but adding to PL as per formula:
        pl_power = (powers.get("VCCINT", 0) + powers.get("VCCBRAM", 0) + 
                    powers.get("VCCAUX", 0) + powers.get("VCC1V2", 0) + 
                    powers.get("VCC3V3", 0))

        # MGT = MGTRAVCC+MGTRAVTT+ MGTAVCC+ MGTAVTT 
        mgt_power = (powers.get("MGTRAVCC", 0) + powers.get("MGTRAVTT", 0) + 
                     powers.get("MGTAVCC", 0) + powers.get("MGTAVTT", 0))
        
        # Based on C code, they also added VCC3V3 to MGT, but I am following the explicit formula
        # Total Power = PS + PL + MGT
        total_power = ps_power + pl_power + mgt_power

        return ps_power, pl_power, mgt_power, total_power

    def run_measurements(self, interval=1.0, n_times=None, output_file=None, verbose=False, display=False):
        """
        Run continuous or bounded power measurements.
        
        Args:
            interval (float): -t, frequency measurements are made in seconds. Default is 1.0.
            n_times (int): -n, number of times to log a value. If None, loops indefinitely until stopped.
            output_file (str): -o, allows the user to specify the name of an output csv file.
            verbose (bool): -v, enables a verbose mode (prints individual rails).
            display (bool): -d, enables a mode that displays the aggregated power values to the terminal.
        """
        self.interval = interval
        self.samples = []
        
        csv_file = None
        writer = None
        if output_file:
            csv_file = open(output_file, 'w', newline='')
            writer = csv.writer(csv_file)
            writer.writerow(['Timestamp', 'PS_Power', 'PL_Power', 'MGT_Power', 'Total_Power'])

        if display:
            print("PS Power, PL Power, MGT Power, Total Power")

        count = 0
        try:
            while n_times is None or count < n_times:
                if self._stop:
                    break

                ts = time.time()
                ps, pl, mgt, total = self._read_once(verbose=verbose)
                self.samples.append((ts, ps, pl, mgt, total))

                if display:
                    print(f"{ps:.3f}, {pl:.3f}, {mgt:.3f}, {total:.3f}")

                if writer:
                    writer.writerow([ts, ps, pl, mgt, total])

                count += 1
                if n_times is None or count < n_times:
                    time.sleep(self.interval)

        except KeyboardInterrupt:
            print("Measurement stopped by user.")
        finally:
            if csv_file:
                csv_file.close()

    def _run(self):
        """Sampling thread compatibility for original background monitoring."""
        while not self._stop:
            ts = time.time()
            ps, pl, mgt, total = self._read_once()
            self.samples.append((ts, ps, pl, mgt, total))
            time.sleep(self.interval)

    def start(self):
        """Start power monitoring in a background thread."""
        self.samples = []
        self._stop = False
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        return True

    def stop(self):
        """Stop power monitoring."""
        self._stop = True
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.0)

    def save_samples(self, filepath: str):
        """
        Export all collected power samples during the last run to a CSV or TXT file.
        
        Args:
            filepath (str): The destination file path (.csv or .txt).
        """
        if not self.samples:
            logging.warning("No power samples to save.")
            return

        delimiter = ',' if filepath.lower().endswith('.csv') else '\t'
        
        try:
            with open(filepath, 'w', newline='') as f:
                writer = csv.writer(f, delimiter=delimiter)
                writer.writerow(['Timestamp', 'PS_Power_W', 'PL_Power_W', 'MGT_Power_W', 'Total_Power_W'])
                for s in self.samples:
                    # s is (ts, ps, pl, mgt, total)
                    writer.writerow([f"{s[0]:.4f}", f"{s[1]:.3f}", f"{s[2]:.3f}", f"{s[3]:.3f}", f"{s[4]:.3f}"])
            logging.info(f"Successfully saved {len(self.samples)} power samples to {filepath}")
        except Exception as e:
            logging.error(f"Failed to save power samples to {filepath}: {e}")

    def average(self):
        """Calculate average power consumption for all domains."""
        if not self.samples:
            return 0.0, 0.0, 0.0, 0.0
        total_samples = self.get_sample_count()
        ps_avg = sum(s[1] for s in self.samples) / total_samples
        pl_avg = sum(s[2] for s in self.samples) / total_samples
        mgt_avg = sum(s[3] for s in self.samples) / total_samples
        total_avg = sum(s[4] for s in self.samples) / total_samples
        return ps_avg, pl_avg, mgt_avg, total_avg
    
    def get_sample_count(self):
        """Return number of samples collected."""
        return len(self.samples)
