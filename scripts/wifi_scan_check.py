"""Check before the next walks: can a scan name the router's networks, and can the Mac read Bluetooth signals?

    python scripts/wifi_scan_check.py          # about a minute; asks for the password once

Walk 1 found the compiled CoreWLAN helper's scan returning no network names or BSSIDs, so the router's beacons
could not be told from the neighbours'. The wireless probe had seen names through the Swift interpreter, so both
are compared here, against the link's BSSID from wdutil. Then a 10-second Bluetooth Low Energy scan
(CoreBluetooth) lists the advertising devices it hears, with their signal: the speaker gave no signal through
system_profiler. Names are shown shortened (first 4 characters) and nothing is saved.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.device.sources import bluetooth, wifi  # noqa: E402

BLE = r"""
import CoreBluetooth
import Foundation
class Scanner: NSObject, CBCentralManagerDelegate {
    var manager: CBCentralManager!
    override init() { super.init(); manager = CBCentralManager(delegate: self, queue: nil) }
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        print("state=\(central.state.rawValue)")
        if central.state == .poweredOn { central.scanForPeripherals(withServices: nil, options: [CBCentralManagerScanOptionAllowDuplicatesKey: true]) }
    }
    func centralManager(_ central: CBCentralManager, didDiscover p: CBPeripheral, advertisementData: [String: Any], rssi: NSNumber) {
        let name = (advertisementData[CBAdvertisementDataLocalNameKey] as? String) ?? p.name ?? ""
        print("ble id=\(p.identifier.uuidString.prefix(8)) rssi=\(rssi) name=\(name)")
    }
}
let s = Scanner()
RunLoop.main.run(until: Date().addingTimeInterval(10))
"""


def short(name: str) -> str:
    return (name[:4] + "…") if name else "(no name)"


def main() -> None:
    home = ""                                # the home's network-name prefix, from the private floor plan if present
    plan = ROOT / "logs" / "home" / "plan.json"
    if plan.exists():
        home = json.loads(plan.read_text()).get("home_prefix", "").lower()
    subprocess.run(["sudo", "-v"], check=True)
    drv = subprocess.run(["sudo", "-n", "wdutil", "info"], capture_output=True, text=True).stdout
    bssid = re.search(r"^\s*BSSID\s*:\s*(\S+)", drv, re.M)
    print(f"Link (wdutil): BSSID {'read' if bssid else 'not read'}; {wifi.parse_wdutil(drv)}")

    print("\n1. Compiled helper scan (13 s) ...", flush=True)
    compiled = wifi.scan(ROOT)
    print("2. Swift interpreter scan (about 25 s) ...", flush=True)
    out = subprocess.run(["swift", str(wifi.HELPER_SOURCE), "scan"], capture_output=True, text=True, timeout=120)
    interpreted = [r for r in wifi.parse_lines(out.stdout) if "error" not in r]
    for name, nets in (("compiled", compiled), ("interpreter", interpreted)):
        named = sum(bool(n.get("ssid")) for n in nets)
        with_bssid = sum(bool(n.get("bssid")) for n in nets)
        match = bssid and any(n.get("bssid", "").lower() == bssid.group(1).lower() for n in nets)
        print(f"   {name}: {len(nets)} networks, {named} with a name, {with_bssid} with a BSSID, link's BSSID found: {bool(match)}")
    best = interpreted if sum(bool(n.get("ssid")) for n in interpreted) > sum(bool(n.get("ssid")) for n in compiled) else compiled
    print("\n   Strongest networks (name shortened):")
    for n in sorted(best, key=lambda n: -n["rssi_dbm"])[:12]:
        name = n.get("ssid", "")
        shown = name if home and name.lower().startswith(home) else short(name)   # the home's own networks in full
        print(f"   {n['rssi_dbm']:>4} dBm  {n.get('band_ghz'):>3} GHz ch {n.get('channel'):>3} {n.get('width_mhz')} MHz  {shown}")

    print("\n3. Connected Bluetooth devices (system_profiler):")
    for dev in bluetooth.connected():
        print(f"   {dev['kind'] or 'device'} '{dev['name']}': signal {dev['rssi_dbm'] if dev['rssi_dbm'] is not None else 'not given'}")
    print("\n4. Bluetooth LE scan, 10 s (macOS may ask to allow Terminal to use Bluetooth: allow it) ...", flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "ble.swift"
        src.write_text(BLE, encoding="utf-8")
        ble = subprocess.run(["swift", str(src)], capture_output=True, text=True, timeout=120)
    state = re.search(r"state=(\d+)", ble.stdout)
    devices = {}
    for ident, rssi, name in re.findall(r"ble id=(\S+) rssi=(-?\d+) name=(.*)", ble.stdout):
        devices.setdefault(ident, (name, []))[1].append(int(rssi))
    print(f"   Bluetooth state {state.group(1) if state else '?'} (5 = on); {len(devices)} devices heard")
    for ident, (name, values) in sorted(devices.items(), key=lambda kv: -max(kv[1][1]))[:12]:
        print(f"   {max(values):>4} dBm (median {sorted(values)[len(values) // 2]}, {len(values)} packets)  {name or '(no name)'}")
    if ble.returncode != 0:
        print("   error:", ble.stderr.strip()[:300])


if __name__ == "__main__":
    main()
