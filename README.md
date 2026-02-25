# Power Monitor ZCU102

The `power_monitor` tool provides a Python interface to accurately read INA226 power rails via the `hwmon` subsystems on the Xilinx Zynq UltraScale+ ZCU102 development board.

The design for this tool leverages the approach in the Xilinx EDA365 article: [Accurate Design Power Measurement Made Easier](https://xilinx.eda365.com/xilinx-article-detail.html?detail=22) by Don Matson and Luis Bielich.

---

## Power Calculation Formulas

The total power of the board is divided into three major domains: Processing System (PS), Programmable Logic (PL), and Multi-Gigabit Transceivers (MGT). The formulas used to calculate total power are derived from the reference article:

*   **PS Power** = VCCPSINTFP + VCCPSINTLP + VCCPSAUX + VCCPSPLL + VCCPSDDR + VCCOPS + VCCOPS3 + VCCPSDDRPL
*   **PL Power** = VCCINT + VCCBRAM + VCCAUX + VCC1V2 + VCC3V3
*   **MGT Power** = MGTRAVCC + MGTRAVTT + MGTAVCC + MGTAVTT
*   **Total Power** = PS Power + PL Power + MGT Power

*Note: While some legacy implementations vary where VCC3V3 is categorized, this tool adds it to PL as indicated by the formula structure in the article text.*

---

## INA226 Power Rails for ZCU102

The ZCU102 has shunt resistors placed on specific power rails, monitored by TI INA226 chips. These are accessible via the I2C bus exported to `/sys/class/hwmon` on PetaLinux systems. 

Here is the table of the relevant rails (referenced from the article and board parameters):

| Sensor Name | Rail / Domain Name | Category |
| :--- | :--- | :--- |
| `ina226_u76` | VCCPSINTFP | PS |
| `ina226_u77` | VCCPSINTLP | PS |
| `ina226_u78` | VCCPSAUX | PS |
| `ina226_u87` | VCCPSPLL | PS |
| `ina226_u93` | VCCPSDDR | PS |
| `ina226_u88` | VCCOPS | PS |
| `ina226_u15` | VCCOPS3 | PS |
| `ina226_u92` | VCCPSDDRPL | PS |
| `ina226_u79` | VCCINT | PL |
| `ina226_u81` | VCCBRAM | PL |
| `ina226_u80` | VCCAUX | PL |
| `ina226_u84` | VCC1V2 | PL |
| `ina226_u16` | VCC3V3 | PL |
| `ina226_u65` | VADJ_FMC | PL |
| `ina226_u85` | MGTRAVCC | MGT |
| `ina226_u86` | MGTRAVTT | MGT |
| `ina226_u74` | MGTAVCC | MGT |
| `ina226_u75` | MGTAVTT | MGT |

---

## Installation 

### From source (PetaLinux 2022.2)

```bash
git clone <repository-url>
cd power_monitor
pip install .
```

---

## Running Automated Tests

The tests are specifically written to target the `hwmon` structures of the ZCU102 running PetaLinux. 

**Requirements:**
- A physical ZCU102 board running the PetaLinux 2022.2 image.
- `pytest` installed.

**To run the tests:**
1. Secure Shell (SSH) into the ZCU102 or use the serial terminal.
2. Navigate to the `power_monitor` project root.
3. Install pytest if needed: `pip install pytest`
4. Run the suite:
   ```bash
   python -m pytest tests/
   ```
